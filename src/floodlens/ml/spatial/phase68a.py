"""Phase 6.8A Target B observational transition diagnostic.

No model fitting. No invented 24–168 h GFM maps. Unknown is never dry.
Target B t0 is the earlier GFM scene clock, not valid_at − 192 h.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage

from floodlens.ml.leakage import hours_between, parse_ts
from floodlens.ml.spatial.events import EVENT_GAP_DAYS, inventory
from floodlens.ml.spatial.labels import GFM_DRY, GFM_FLOOD, GFM_NODATA
from floodlens.ml.spatial.phase67 import assert_frozen_splits
from floodlens.ml.spatial.precip_lattice import CACHE as PRECIP_CACHE
from floodlens.ml.spatial.precip_lattice import END as LATTICE_END
from floodlens.ml.spatial.precip_lattice import START as LATTICE_START
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import (
    HORIZON_HOURS,
    SPATIAL_DATASET_VERSION_V21,
    SPATIAL_DIR,
    UNKNOWN,
    SpatialForecastSample,
)

EXPERIMENT_ID = "phase6.8a-target-b-transition-v1"
LABEL_RESOLUTION_M = 20.0
WORKING_GRID = 64
RNG_SEED = 0
MIN_CENTROID_FLOOD = 10
MIN_EVENTS_DIAGNOSTIC = 8
MIN_PAIRS_B6 = 20
MIN_TURNOVER_B6 = 0.01
UNSUPPORTED_HORIZONS_H = (24, 48, 72, 96, 120, 144, 168)

CLASS_NEWLY_FLOODED = 1
CLASS_RECEDING = 2
CLASS_PERSISTENT_FLOOD = 3
CLASS_PERSISTENT_DRY = 4
CLASS_UNKNOWN = UNKNOWN

DELTA_T_BINS = (
    (0.0, 2.0, "0-2 days"),
    (2.0, 4.0, "2-4 days"),
    (4.0, 6.0, "4-6 days"),
    (6.0, 8.0, "6-8 days"),
    (8.0, 12.0, "8-12 days"),
    (12.0, None, "12+ days"),
)

OUT_DIR = SPATIAL_DIR / "phase68a"
REPORT_JSON = SPATIAL_DIR / "phase68a_eval.json"
DOCS_REPORT = Path("docs/PHASE_6_8A_TARGET_B_DIAGNOSTIC_REPORT.md")

# In-horizon rain is an observation of the transition interval, never a t0 feature.
IN_HORIZON_KIND = "POST-T0 OBSERVATION"
PRE_T0_KIND = "PRE-T0 AVAILABLE INPUT"


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return None
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if np.isfinite(val) else None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    return obj


def _finite(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    return num if np.isfinite(num) else None


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hour_key(value) -> str:
    stamp = str(value).replace("Z", "").replace("+00:00", "")
    if len(stamp) >= 16:
        return stamp[:16] + ":00"
    if len(stamp) >= 13:
        return stamp[:13] + ":00:00"
    return stamp


def hours_in_open_closed(t0: str, t1: str) -> List[datetime]:
    """Hourly stamps in (t0, t1], truncated to the hour after t0 through n≈Δt hours."""
    t0p = parse_ts(t0)
    t1p = parse_ts(t1)
    delta_h = (t1p - t0p).total_seconds() / 3600.0
    if delta_h <= 0:
        return []
    n = int(math.ceil(delta_h - 1e-9))
    base = t0p.replace(minute=0, second=0, microsecond=0)
    return [base + timedelta(hours=h) for h in range(1, n + 1)]


def delta_t_hours(earlier_valid_at: str, later_valid_at: str) -> float:
    return float(hours_between(later_valid_at, earlier_valid_at))


def delta_t_bucket(hours: float) -> str:
    days = float(hours) / 24.0
    for lo, hi, name in DELTA_T_BINS:
        if hi is None:
            if days >= lo:
                return name
        elif lo <= days < hi:
            return name
    return "12+ days"


def transition_map(y_earlier: np.ndarray, y_later: np.ndarray) -> np.ndarray:
    """Classify jointly valid pixels. Unknown at either endpoint → UNKNOWN."""
    a = np.asarray(y_earlier)
    b = np.asarray(y_later)
    if a.shape != b.shape:
        raise ValueError(f"transition maps must match shape: {a.shape} vs {b.shape}")
    out = np.full(a.shape, CLASS_UNKNOWN, dtype=np.uint8)
    joint = (a != UNKNOWN) & (b != UNKNOWN) & (a != GFM_NODATA) & (b != GFM_NODATA)
    out[joint & (a == GFM_DRY) & (b == GFM_FLOOD)] = CLASS_NEWLY_FLOODED
    out[joint & (a == GFM_FLOOD) & (b == GFM_DRY)] = CLASS_RECEDING
    out[joint & (a == GFM_FLOOD) & (b == GFM_FLOOD)] = CLASS_PERSISTENT_FLOOD
    out[joint & (a == GFM_DRY) & (b == GFM_DRY)] = CLASS_PERSISTENT_DRY
    return out


def iou_jointly_valid(y_earlier: np.ndarray, y_later: np.ndarray) -> Optional[float]:
    a = np.asarray(y_earlier)
    b = np.asarray(y_later)
    joint = (a != UNKNOWN) & (b != UNKNOWN)
    if not np.any(joint):
        return None
    inter = int(np.sum(joint & (a == GFM_FLOOD) & (b == GFM_FLOOD)))
    union = int(np.sum(joint & ((a == GFM_FLOOD) | (b == GFM_FLOOD))))
    if union == 0:
        return None
    return float(inter / union)


def adjacent_pairs(
    samples: Sequence[SpatialForecastSample],
) -> List[Tuple[SpatialForecastSample, SpatialForecastSample]]:
    """Same event_id, same AOI, chronological adjacent scenes only."""
    grouped: Dict[Tuple[str, str], List[SpatialForecastSample]] = defaultdict(list)
    for sample in samples:
        eid = (sample.extra or {}).get("event_id")
        if not eid or not sample.valid_at:
            continue
        grouped[(str(eid), sample.city_id)].append(sample)
    pairs: List[Tuple[SpatialForecastSample, SpatialForecastSample]] = []
    for key in sorted(grouped):
        members = sorted(grouped[key], key=lambda s: (parse_ts(s.valid_at), s.scene_id or ""))
        for i in range(len(members) - 1):
            earlier = members[i]
            later = members[i + 1]
            if (earlier.extra or {}).get("event_id") != (later.extra or {}).get("event_id"):
                continue
            if earlier.city_id != later.city_id:
                continue
            if parse_ts(later.valid_at) <= parse_ts(earlier.valid_at):
                continue
            pairs.append((earlier, later))
    return pairs


def reject_cross_event_pairs(samples: Sequence[SpatialForecastSample]) -> List[Tuple[str, str]]:
    """Pairs that would exist by calendar proximity but have different event_id (must be empty of Target B pairs)."""
    by_aoi: Dict[str, List[SpatialForecastSample]] = defaultdict(list)
    for sample in samples:
        by_aoi[sample.city_id].append(sample)
    bad = []
    for city, members in by_aoi.items():
        ordered = sorted(members, key=lambda s: parse_ts(s.valid_at))
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            ea = (a.extra or {}).get("event_id")
            eb = (b.extra or {}).get("event_id")
            if ea and eb and ea != eb:
                bad.append((a.scene_id or a.valid_at, b.scene_id or b.valid_at))
    return bad


class LatticeIndex:
    """Hourly presence and optional AOI-mean precipitation. No temporal interpolation."""

    def __init__(
        self,
        start: str,
        end: str,
        kind: str = "REANALYSIS",
        n_points: int = 9,
        temporal_resolution: str = "hourly",
        spatial_coverage: str = "3x3 ERA5-Land lattice ~11 km",
        values: Optional[Dict[str, Dict[str, float]]] = None,
        present: Optional[Dict[str, set]] = None,
        source: str = "open-meteo-archive",
        coverage_only: bool = False,
    ):
        self.start = start
        self.end = end
        self.kind = kind
        self.n_points = int(n_points)
        self.temporal_resolution = temporal_resolution
        self.spatial_coverage = spatial_coverage
        self.values = values or {}
        self.present = present or {}
        self.source = source
        self.coverage_only = coverage_only

    def _key(self, stamp: datetime) -> str:
        return hour_key(_iso(stamp))

    def hour_present(self, aoi_id: str, stamp: datetime) -> bool:
        key = self._key(stamp)
        hours = self.present.get(aoi_id)
        if hours is not None:
            return key in hours
        vals = self.values.get(aoi_id)
        if vals is not None:
            return key in vals
        if self.coverage_only:
            t0 = parse_ts(self.start if "T" in str(self.start) else self.start + "T00:00:00Z")
            t1 = parse_ts(self.end if "T" in str(self.end) else str(self.end) + "T23:00:00Z")
            return t0 <= stamp <= t1
        return False

    def hour_value(self, aoi_id: str, stamp: datetime) -> Optional[float]:
        vals = self.values.get(aoi_id) or {}
        key = self._key(stamp)
        if key not in vals:
            return None
        val = float(vals[key])
        return val if np.isfinite(val) else None


def build_lattice_index(lattice: Optional[dict] = None) -> Optional[LatticeIndex]:
    if lattice is None:
        if not PRECIP_CACHE.exists():
            return None
        lattice = json.loads(PRECIP_CACHE.read_text(encoding="utf-8"))
    aois = lattice.get("aois") or {}
    if not aois:
        start = lattice.get("start") or LATTICE_START
        end = lattice.get("end") or LATTICE_END
        return LatticeIndex(
            start=start,
            end=end,
            kind=lattice.get("kind") or "UNAVAILABLE",
            coverage_only=True,
        )
    values: Dict[str, Dict[str, float]] = {}
    present: Dict[str, set] = {}
    n_points = 0
    for aoi_id, pack in aois.items():
        points = pack.get("points") or []
        n_points = max(n_points, len(points))
        if not points:
            continue
        acc: Dict[str, float] = {}
        finite: Dict[str, int] = {}
        for pt in points:
            for t, v in zip(pt.get("time") or [], pt.get("precipitation_mm") or []):
                if v is None:
                    continue
                key = hour_key(t)
                acc[key] = acc.get(key, 0.0) + float(v)
                finite[key] = finite.get(key, 0) + 1
        thresh = max(1, int(math.ceil(0.5 * max(len(points), 1))))
        values[aoi_id] = {k: acc[k] / finite[k] for k in acc if finite[k] > 0}
        present[aoi_id] = {k for k, n in finite.items() if n >= thresh}
    start = lattice.get("start") or LATTICE_START
    end = lattice.get("end") or LATTICE_END
    return LatticeIndex(
        start=start,
        end=end,
        kind=lattice.get("kind") or "REANALYSIS",
        n_points=n_points or 9,
        values=values,
        present=present,
        source=lattice.get("source") or "open-meteo-archive",
    )


def audit_rainfall_interval(
    aoi_id: str,
    t0: str,
    t1: str,
    index: Optional[LatticeIndex],
    *,
    window: str = "in_horizon",
) -> dict:
    hours = hours_in_open_closed(t0, t1)
    n_req = len(hours)
    if index is None or n_req == 0:
        cls = "FORCING_MISSING"
        return {
            "window": window,
            "rain_required_start": t0,
            "rain_required_end": t1,
            "n_hours_required": n_req,
            "n_hours_present": 0,
            "n_hours_missing": n_req,
            "missing_fraction": 1.0 if n_req else None,
            "longest_missing_gap_hours": n_req,
            "rainfall_complete": False,
            "forcing_class": cls,
            "temporal_resolution": None if index is None else index.temporal_resolution,
            "spatial_coverage": None if index is None else index.spatial_coverage,
            "n_lattice_points": None if index is None else index.n_points,
            "precip_sum_mm": None,
            "precip_sum_kind": IN_HORIZON_KIND if window == "in_horizon" else PRE_T0_KIND,
            "filled": False,
            "causal_feature": False if window == "in_horizon" else True,
        }
    present_flags = [index.hour_present(aoi_id, h) for h in hours]
    n_present = int(sum(1 for f in present_flags if f))
    n_missing = n_req - n_present
    longest = 0
    run = 0
    for flag in present_flags:
        if not flag:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    if n_present == n_req:
        cls = "FORCING_COMPLETE"
    elif n_present == 0:
        cls = "FORCING_MISSING"
    else:
        cls = "FORCING_PARTIAL"
    precip_sum = 0.0
    n_sum = 0
    for h, flag in zip(hours, present_flags):
        if not flag:
            continue
        val = index.hour_value(aoi_id, h)
        if val is None:
            continue
        precip_sum += val
        n_sum += 1
    causal = window != "in_horizon"
    return {
        "window": window,
        "rain_required_start": t0,
        "rain_required_end": t1,
        "n_hours_required": n_req,
        "n_hours_present": n_present,
        "n_hours_missing": n_missing,
        "missing_fraction": (n_missing / n_req) if n_req else None,
        "longest_missing_gap_hours": int(longest),
        "rainfall_complete": n_missing == 0 and n_req > 0,
        "forcing_class": cls,
        "temporal_resolution": index.temporal_resolution,
        "spatial_coverage": index.spatial_coverage,
        "n_lattice_points": index.n_points,
        "lattice_kind": index.kind,
        "lattice_start": index.start,
        "lattice_end": index.end,
        "precip_sum_mm": float(precip_sum) if n_sum else None,
        "precip_sum_hours_used": n_sum,
        "precip_sum_kind": IN_HORIZON_KIND if window == "in_horizon" else PRE_T0_KIND,
        "filled": False,
        "causal_feature": causal,
    }


def _flood_centroid(y: np.ndarray, mask: np.ndarray) -> Optional[Tuple[float, float]]:
    rows, cols = np.where(mask & (np.asarray(y) == GFM_FLOOD))
    if rows.size < MIN_CENTROID_FLOOD:
        return None
    return float(np.mean(rows)), float(np.mean(cols))


def expansion_diagnostics(
    trans: np.ndarray,
    y0: np.ndarray,
    y1: np.ndarray,
    river_distance: Optional[np.ndarray],
) -> dict:
    new = trans == CLASS_NEWLY_FLOODED
    n_new = int(np.sum(new))
    components = 0
    largest_frac = None
    if n_new > 0:
        labeled, components = ndimage.label(new.astype(np.uint8))
        if components > 0:
            sizes = ndimage.sum(new, labeled, index=list(range(1, components + 1)))
            sizes = np.atleast_1d(np.asarray(sizes, dtype=np.float64))
            largest_frac = float(np.max(sizes) / n_new)
    joint = (np.asarray(y0) != UNKNOWN) & (np.asarray(y1) != UNKNOWN)
    c0 = _flood_centroid(y0, joint)
    c1 = _flood_centroid(y1, joint)
    centroid_shift = None
    if c0 is not None and c1 is not None:
        centroid_shift = float(math.hypot(c1[0] - c0[0], c1[1] - c0[1]))
    river_mean = None
    river_status = "UNAVAILABLE"
    if river_distance is not None and n_new > 0:
        rd = np.asarray(river_distance, dtype=np.float64)
        vals = rd[new]
        finite = vals[np.isfinite(vals)]
        if finite.size:
            river_mean = float(np.mean(finite))
            river_status = "AVAILABLE"
    return {
        "n_new_flood_components": int(components),
        "largest_new_flood_component_frac": largest_frac,
        "centroid_t0": None if c0 is None else [c0[0], c0[1]],
        "centroid_t1": None if c1 is None else [c1[0], c1[1]],
        "centroid_shift_cells": centroid_shift,
        "new_flood_mean_river_distance": river_mean,
        "river_distance_status": river_status,
    }


def _static_status(sample: SpatialForecastSample, key: str) -> str:
    extra = sample.extra or {}
    arr = extra.get(key)
    if key == "elevation":
        if sample.dem_present and sample.x_dem is not None and np.any(np.isfinite(sample.x_dem)):
            return "AVAILABLE"
        return "UNAVAILABLE"
    if arr is None:
        return "UNAVAILABLE"
    a = np.asarray(arr)
    if a.size and np.any(np.isfinite(a)):
        return "AVAILABLE"
    return "UNAVAILABLE"


def feature_availability(
    earlier: SpatialForecastSample,
    later: SpatialForecastSample,
    pre_t0: dict,
    in_horizon: dict,
) -> dict:
    """Distinguish PRE-T0 AVAILABLE INPUT from IN-HORIZON OBSERVATION."""
    q = earlier.x_glofas_q_lookback
    q_ok = q is not None and any(v is not None and np.isfinite(float(v)) for v in q if v is not None)
    # Cube Q is aligned to 192 h issue time, not Target B t0.
    discharge = "UNAVAILABLE"
    pre_class = pre_t0.get("forcing_class")
    pre_rain = {
        "status": (
            "AVAILABLE"
            if pre_class == "FORCING_COMPLETE"
            else ("PARTIAL" if pre_class == "FORCING_PARTIAL" else "UNAVAILABLE")
        ),
        "kind": PRE_T0_KIND,
        "causal_feature": True,
    }
    in_rain = {
        "status": (
            "AVAILABLE"
            if in_horizon.get("forcing_class") == "FORCING_COMPLETE"
            else ("PARTIAL" if in_horizon.get("forcing_class") == "FORCING_PARTIAL" else "UNAVAILABLE")
        ),
        "kind": IN_HORIZON_KIND,
        "causal_feature": False,
        "forecast_available": False,
    }
    prior = "AVAILABLE"
    return {
        "rainfall_history_before_t0": pre_rain,
        "rainfall_immediately_before_t0": pre_rain,
        "rainfall_during_horizon": in_rain,
        "elevation": {"status": _static_status(earlier, "elevation"), "kind": PRE_T0_KIND, "causal_feature": True},
        "slope": {"status": _static_status(earlier, "slope"), "kind": PRE_T0_KIND, "causal_feature": True},
        "river_distance": {
            "status": _static_status(earlier, "river_distance"),
            "kind": PRE_T0_KIND,
            "causal_feature": True,
        },
        "river_mask": {"status": _static_status(earlier, "river_mask"), "kind": PRE_T0_KIND, "causal_feature": True},
        "river_discharge": {
            "status": discharge,
            "kind": PRE_T0_KIND,
            "causal_feature": False,
            "note": "Cube GloFAS Q is aligned to valid_at−192 h, not Target B t0. Not re-fetched.",
            "cube_q_present_on_earlier_sample": bool(q_ok),
        },
        "river_level": {"status": "UNAVAILABLE", "kind": PRE_T0_KIND, "causal_feature": False},
        "prior_flood_map": {"status": prior, "kind": PRE_T0_KIND, "causal_feature": True, "source": "earlier GFM scene"},
        "later_flood_map": {"status": "AVAILABLE", "kind": "TARGET", "causal_feature": False},
    }


def pair_statistics(
    earlier: SpatialForecastSample,
    later: SpatialForecastSample,
    lattice: Optional[LatticeIndex] = None,
) -> dict:
    y0 = np.asarray(earlier.y_flood)
    y1 = np.asarray(later.y_flood)
    trans = transition_map(y0, y1)
    n_total = int(trans.size)
    n_unknown = int(np.sum(trans == CLASS_UNKNOWN))
    n_joint = n_total - n_unknown
    n_new = int(np.sum(trans == CLASS_NEWLY_FLOODED))
    n_rec = int(np.sum(trans == CLASS_RECEDING))
    n_pf = int(np.sum(trans == CLASS_PERSISTENT_FLOOD))
    n_pd = int(np.sum(trans == CLASS_PERSISTENT_DRY))
    n_flood0 = int(np.sum((y0 == GFM_FLOOD) & (y0 != UNKNOWN)))
    n_flood1 = int(np.sum((y1 == GFM_FLOOD) & (y1 != UNKNOWN)))
    n_unk0 = int(np.sum(y0 == UNKNOWN))
    n_unk1 = int(np.sum(y1 == UNKNOWN))
    dt_h = delta_t_hours(earlier.valid_at, later.valid_at)
    t0 = earlier.valid_at
    t1 = later.valid_at
    pre_end = t0
    pre_start = _iso(parse_ts(t0) - timedelta(hours=72))
    pre = audit_rainfall_interval(earlier.city_id, pre_start, pre_end, lattice, window="pre_t0")
    in_h = audit_rainfall_interval(earlier.city_id, t0, t1, lattice, window="in_horizon")
    feats = feature_availability(earlier, later, pre, in_h)
    river = (earlier.extra or {}).get("river_distance")
    exp = expansion_diagnostics(trans, y0, y1, None if river is None else np.asarray(river))
    split_a = earlier.split
    split_b = later.split
    leakage = []
    if split_a and split_b and split_a != split_b:
        leakage.append("same event_id assigned to two splits")
    if in_h.get("causal_feature"):
        leakage.append("in-horizon rain marked causal")
    if feats["rainfall_during_horizon"].get("causal_feature"):
        leakage.append("in-horizon rain treated as t0 feature")
    if feats["later_flood_map"].get("causal_feature"):
        leakage.append("later map used as feature")
    if int(round(dt_h)) in UNSUPPORTED_HORIZONS_H and abs(dt_h - round(dt_h)) < 1e-6:
        # Exact 24/48/… hours is allowed as a measured interval; relabeling is not.
        pass
    invented = False
    gates = pair_gates(
        earlier,
        later,
        n_joint=n_joint,
        n_new=n_new,
        n_rec=n_rec,
        leakage=leakage,
        in_horizon=in_h,
        invented=invented,
    )
    eid = (earlier.extra or {}).get("event_id")
    return {
        "pair_id": f"{eid}|{earlier.city_id}|{earlier.scene_id}|{later.scene_id}",
        "event_id": eid,
        "city_id": earlier.city_id,
        "region": earlier.city_id,
        "split": split_a,
        "flood_mechanism": (earlier.extra or {}).get("flood_mechanism"),
        "year": int(str(t1)[0:4]),
        "earlier_scene_id": earlier.scene_id,
        "later_scene_id": later.scene_id,
        "t0": t0,
        "t1": t1,
        "delta_t_hours": dt_h,
        "delta_t_days": dt_h / 24.0,
        "delta_t_bucket": delta_t_bucket(dt_h),
        "horizon_relabeled": False,
        "n_pixels": n_total,
        "n_jointly_valid": n_joint,
        "n_unknown_transition": n_unknown,
        "unknown_fraction": (n_unknown / n_total) if n_total else None,
        "joint_valid_fraction": (n_joint / n_total) if n_total else None,
        "n_newly_flooded": n_new,
        "n_receding": n_rec,
        "n_persistent_flood": n_pf,
        "n_persistent_dry": n_pd,
        "flood_area_t0": n_flood0,
        "flood_area_t1": n_flood1,
        "net_flood_change": n_flood1 - n_flood0,
        "unknown_pixels_t0": n_unk0,
        "unknown_pixels_t1": n_unk1,
        "fraction_newly_flooded": (n_new / n_joint) if n_joint else None,
        "fraction_receding": (n_rec / n_joint) if n_joint else None,
        "fraction_persistent_flood": (n_pf / n_joint) if n_joint else None,
        "fraction_persistent_dry": (n_pd / n_joint) if n_joint else None,
        "turnover_fraction": ((n_new + n_rec) / n_joint) if n_joint else None,
        "iou_t0_t1": iou_jointly_valid(y0, y1),
        "rainfall_pre_t0": pre,
        "rainfall_in_horizon": in_h,
        "forcing_class": in_h.get("forcing_class"),
        "rainfall_complete": in_h.get("rainfall_complete"),
        "features": feats,
        "expansion": exp,
        "pre_t0_input_coverage": pre.get("n_hours_present") / pre["n_hours_required"]
        if pre.get("n_hours_required")
        else 0.0,
        "in_horizon_rain_coverage": in_h.get("n_hours_present") / in_h["n_hours_required"]
        if in_h.get("n_hours_required")
        else 0.0,
        "label_valid_fraction": (n_joint / n_total) if n_total else None,
        "new_flood_fraction": (n_new / n_joint) if n_joint else None,
        "recession_fraction": (n_rec / n_joint) if n_joint else None,
        "in_horizon_as_causal_feature": False,
        "later_map_as_feature": False,
        "leakage_errors": leakage,
        "gates": gates,
    }


def pair_gates(
    earlier: SpatialForecastSample,
    later: SpatialForecastSample,
    *,
    n_joint: int,
    n_new: int,
    n_rec: int,
    leakage: Sequence[str],
    in_horizon: dict,
    invented: bool,
) -> dict:
    b1 = (
        earlier.city_id == later.city_id
        and parse_ts(later.valid_at) > parse_ts(earlier.valid_at)
        and earlier.scene_id != later.scene_id
        and earlier.y_flood is not None
        and later.y_flood is not None
        and np.asarray(earlier.y_flood).shape == np.asarray(later.y_flood).shape
    )
    b2 = (earlier.extra or {}).get("event_id") == (later.extra or {}).get("event_id") and bool(
        (earlier.extra or {}).get("event_id")
    )
    b3 = n_joint > 0
    b4 = (not leakage) and (not invented) and (not in_horizon.get("causal_feature"))
    b5 = in_horizon.get("forcing_class") in {"FORCING_COMPLETE", "FORCING_PARTIAL", "FORCING_MISSING"}
    return {
        "B1_valid_pair": bool(b1),
        "B2_same_event": bool(b2),
        "B3_valid_transition_mask": bool(b3),
        "B4_no_target_leakage": bool(b4),
        "B5_forcing_recorded": bool(b5),
        "pair_eligible": bool(b1 and b2 and b3 and b4 and b5),
        "n_newly_flooded": int(n_new),
        "n_receding": int(n_rec),
    }


def _quantile(arr: np.ndarray, q: float) -> Optional[float]:
    if arr.size == 0:
        return None
    return float(np.quantile(arr, q))


def summarize_numeric(values: Iterable[Optional[float]]) -> dict:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if arr.size == 0:
        return {"n": 0, "min": None, "median": None, "mean": None, "max": None, "q25": None, "q75": None}
    return {
        "n": int(arr.size),
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
        "q25": _quantile(arr, 0.25),
        "q75": _quantile(arr, 0.75),
    }


def aggregate_by(rows: Sequence[dict], key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    out = []
    for name in sorted(groups):
        g = groups[name]
        events = sorted({r.get("event_id") for r in g if r.get("event_id")})
        out.append(
            {
                key: name,
                "n_pairs": len(g),
                "n_independent_events": len(events),
                "event_ids": events,
                "delta_t_hours": summarize_numeric(r.get("delta_t_hours") for r in g),
                "iou": summarize_numeric(r.get("iou_t0_t1") for r in g),
                "new_flood_fraction": summarize_numeric(r.get("fraction_newly_flooded") for r in g),
                "recession_fraction": summarize_numeric(r.get("fraction_receding") for r in g),
                "turnover_fraction": summarize_numeric(r.get("turnover_fraction") for r in g),
                "unknown_fraction": summarize_numeric(r.get("unknown_fraction") for r in g),
                "forcing_complete_frac": (
                    float(np.mean([1.0 if r.get("rainfall_complete") else 0.0 for r in g])) if g else None
                ),
            }
        )
    return out


def event_level_summaries(rows: Sequence[dict], samples: Sequence[SpatialForecastSample]) -> List[dict]:
    by_event: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        if row.get("event_id"):
            by_event[str(row["event_id"])].append(row)
    sample_events: Dict[str, List[SpatialForecastSample]] = defaultdict(list)
    for sample in samples:
        eid = (sample.extra or {}).get("event_id")
        if eid:
            sample_events[str(eid)].append(sample)
    out = []
    for eid in sorted(by_event):
        g = by_event[eid]
        members = sample_events.get(eid) or []
        regions = sorted({r.get("city_id") for r in g})
        out.append(
            {
                "event_id": eid,
                "n_pairs": len(g),
                "n_maps": len(members),
                "n_regions": len(regions),
                "regions": regions,
                "split": g[0].get("split"),
                "flood_mechanism": g[0].get("flood_mechanism"),
                "year": g[0].get("year"),
                "independent_event": True,
                "delta_t_hours": summarize_numeric(r.get("delta_t_hours") for r in g),
                "iou": summarize_numeric(r.get("iou_t0_t1") for r in g),
                "new_flood_fraction": summarize_numeric(r.get("fraction_newly_flooded") for r in g),
                "recession_fraction": summarize_numeric(r.get("fraction_receding") for r in g),
                "forcing_complete_frac": float(np.mean([1.0 if r.get("rainfall_complete") else 0.0 for r in g])),
            }
        )
    return out


def pearson(x: Sequence[Optional[float]], y: Sequence[Optional[float]]) -> Optional[float]:
    xs = []
    ys = []
    for a, b in zip(x, y):
        if a is None or b is None:
            continue
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        xs.append(float(a))
        ys.append(float(b))
    if len(xs) < 5:
        return None
    xa = np.asarray(xs)
    ya = np.asarray(ys)
    if np.std(xa) == 0 or np.std(ya) == 0:
        return None
    return float(np.corrcoef(xa, ya)[0, 1])


def evaluate_gates_b(rows: Sequence[dict], n_events: int, n_events_with_pairs: int) -> dict:
    eligible = [r for r in rows if (r.get("gates") or {}).get("pair_eligible")]
    n_signal = [
        r
        for r in eligible
        if (r.get("n_newly_flooded") or 0) > 0
        or (r.get("n_receding") or 0) > 0
        or ((r.get("turnover_fraction") or 0) and r.get("turnover_fraction") > 0)
    ]
    mean_turn = float(
        np.mean([r["turnover_fraction"] for r in eligible if r.get("turnover_fraction") is not None])
    ) if any(r.get("turnover_fraction") is not None for r in eligible) else 0.0
    events_signal = sorted({r.get("event_id") for r in n_signal if r.get("event_id")})
    b1 = all((r.get("gates") or {}).get("B1_valid_pair") for r in rows) if rows else False
    b2 = all((r.get("gates") or {}).get("B2_same_event") for r in rows) if rows else False
    b3 = all((r.get("gates") or {}).get("B3_valid_transition_mask") for r in eligible) if eligible else False
    b4 = all((r.get("gates") or {}).get("B4_no_target_leakage") for r in rows) if rows else False
    b5 = all((r.get("gates") or {}).get("B5_forcing_recorded") for r in rows) if rows else False
    b6 = len(n_signal) >= MIN_PAIRS_B6 and mean_turn >= MIN_TURNOVER_B6 and len(events_signal) >= 5
    b7 = n_events_with_pairs >= MIN_EVENTS_DIAGNOSTIC
    gates = {
        "B1": {"pass": bool(b1), "rule": "valid earlier/later pair (same AOI, later after earlier, maps exist)"},
        "B2": {"pass": bool(b2), "rule": "same real-world event_id; calendar proximity is not sufficient"},
        "B3": {"pass": bool(b3), "rule": "jointly valid transition mask (unknown never inferred)"},
        "B4": {"pass": bool(b4), "rule": "no target leakage; in-horizon rain is POST-T0 OBSERVATION"},
        "B5": {"pass": bool(b5), "rule": "forcing completeness recorded (COMPLETE/PARTIAL/MISSING)"},
        "B6": {
            "pass": bool(b6),
            "rule": (
                f"transition signal: ≥{MIN_PAIRS_B6} pairs with new-flood or recession, "
                f"mean turnover ≥{MIN_TURNOVER_B6}, ≥5 events; pixel count alone is not enough"
            ),
            "n_pairs_with_change": len(n_signal),
            "mean_turnover_eligible": mean_turn,
            "n_events_with_change": len(events_signal),
        },
        "B7": {
            "pass": bool(b7),
            "rule": f"≥{MIN_EVENTS_DIAGNOSTIC} independent events represented by pairs (not pair count)",
            "n_independent_events": n_events,
            "n_events_with_pairs": n_events_with_pairs,
        },
    }
    return {
        "gates": gates,
        "n_pairs": len(rows),
        "n_eligible_pairs": len(eligible),
        "class": "FORECASTABILITY AUDIT",
        "validated": False,
        "all_pass": all(g["pass"] for g in gates.values()),
    }


def decide_letter(report: dict) -> str:
    """One of A–E. Do not choose E just because turnover looks better than 192 h IoU."""
    n_events = int((report.get("counts") or {}).get("n_independent_events") or 0)
    n_pairs = int((report.get("counts") or {}).get("n_observed_transition_pairs") or 0)
    n_eligible = int((report.get("counts") or {}).get("n_eligible_pairs") or 0)
    joint = (report.get("unknown") or {}).get("mean_joint_valid_fraction")
    turn = (report.get("change") or {}).get("mean_turnover_fraction")
    forcing_obs = (report.get("forcing") or {}).get("complete_pair_fraction")
    corr_in = (report.get("association") or {}).get("new_flood_vs_in_horizon_rain")
    corr_pre = (report.get("association") or {}).get("new_flood_vs_pre_t0_rain")
    forecast_in_horizon = bool((report.get("forcing") or {}).get("forecast_available_in_horizon"))
    if n_eligible < 10 or n_events < 5 or (joint is not None and joint < 0.05):
        return "A"
    in_horizon_drives = (
        corr_in is not None
        and (corr_pre is None or abs(corr_in) > abs(corr_pre) + 0.05)
        and corr_in > 0.1
    )
    labels_ok = n_pairs >= 10 and n_events >= MIN_EVENTS_DIAGNOSTIC and (turn or 0) >= MIN_TURNOVER_B6
    if labels_ok and not forecast_in_horizon and (in_horizon_drives or (forcing_obs or 0) < 0.5):
        return "B"
    if labels_ok and n_events < 20 and (turn or 0) >= MIN_TURNOVER_B6:
        # Promising observationally, but official event budget is still thin and
        # in-horizon rain is not a causal forecast input.
        if not forecast_in_horizon and (forcing_obs or 0) >= 0.5 and in_horizon_drives:
            return "B"
        if not forecast_in_horizon:
            return "B"
        return "D"
    if labels_ok and forecast_in_horizon:
        return "C"
    if labels_ok:
        return "B"
    return "A"


DECISION_TEXT = {
    "A": "TARGET B IS NOT FEASIBLE",
    "B": "TARGET B IS FEASIBLE BUT FORCING IS INSUFFICIENT",
    "C": "TARGET B IS SCIENTIFICALLY PROMISING — BASELINES JUSTIFIED",
    "D": "TARGET B IS PROMISING BUT MORE EVENTS ARE REQUIRED",
    "E": "TARGET B SHOULD BECOME THE PRIMARY TRACK-A TARGET",
}


def write_markdown_report(report: dict) -> str:
    c = report.get("counts") or {}
    d = report.get("delta_t") or {}
    ch = report.get("change") or {}
    unk = report.get("unknown") or {}
    fr = report.get("forcing") or {}
    gates = (report.get("gates") or {}).get("gates") or {}
    letter = report.get("decision_letter") or "?"
    assoc = report.get("association") or {}

    def _fmt(val, digits=3):
        if val is None:
            return "n/a"
        if isinstance(val, float):
            return f"{val:.{digits}f}"
        return str(val)

    def _gate(name):
        g = gates.get(name) or {}
        return "PASS" if g.get("pass") else "FAIL"

    lines = [
        "# Phase 6.8A — Target B observational transition diagnostic",
        "",
        "**Status:** FORECASTABILITY AUDIT. Not a training run. Not a VALIDATED claim. No invented 24–168 h GFM maps.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.",
        "",
        "**AOI GBDT:** VALIDATED status **unchanged** (separate registry, scalar AOI task).",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified.",
        "",
        f"**GFM dataset version (unchanged):** `{c.get('dataset_version') or SPATIAL_DATASET_VERSION_V21}`",
        "",
        f"**Experiment id:** `{EXPERIMENT_ID}`",
        "",
        f"**Decision:** **{letter}** — {DECISION_TEXT.get(letter, letter)}",
        "",
        "This phase does not train GBDT, RF, logistic, CNN, U-Net, transformer, or LSTM models.",
        "",
        "---",
        "",
        "## 1. Target B definition",
        "",
        "Primary target: **NEWLY_FLOODED** pixels between consecutive GFM scenes of the same independent event and same AOI.",
        "",
        "```",
        "t0 = earlier.valid_at     # GFM SAR clock of scene k",
        "t1 = later.valid_at       # GFM SAR clock of scene k+1",
        "delta_t = t1 - t0         # measured observation interval; not 24/48/72 h",
        "```",
        "",
        "On pixels valid in **both** maps:",
        "",
        "| Earlier | Later | Class |",
        "| --- | --- | --- |",
        "| DRY | FLOODED | NEWLY_FLOODED (primary) |",
        "| FLOODED | DRY | RECEDING |",
        "| FLOODED | FLOODED | PERSISTENT_FLOOD |",
        "| DRY | DRY | PERSISTENT_DRY |",
        "| any UNKNOWN | any | UNKNOWN |",
        "",
        "Do not infer a transition when either endpoint is unknown. Original GFM masks are preserved. "
        "Secondary diagnostics: RECEDING, PERSISTENT_FLOOD, FLOOD_AREA_CHANGE, NET_FLOOD_CHANGE. None of these were trained on.",
        "",
        "**SHORTER HORIZON NOT SUPPORTED BY CURRENT GFM LABEL TEMPORAL RESOLUTION.** "
        "Δt is reported as measured hours/days. A pair with Δt = 8 days is an 8-day pair, not a 72 h label.",
        "",
        "## 2. Consecutive-scene pairing methodology",
        "",
        "1. Use frozen Track A samples (`build_spatial_samples_v2`), event_id from the 45-day cluster (`EVENT_GAP_DAYS = 45`).",
        "2. Group by `(event_id, city_id)`. Sort by `valid_at`.",
        "3. Form adjacent pairs `(S_i, S_{i+1})` only. Do not pair `S_i` with `S_{i+2}`.",
        "4. Do not pair scenes from different `event_id`, even if calendar dates are close.",
        "5. Do not pair different AOIs. Maps are not co-registered across cities.",
        "6. Inherit the frozen event-level split. Do not create pixel-i.i.d. splits.",
        "",
        f"Independent events in the cube: **{c.get('n_independent_events')}**. "
        f"Observed transition pairs: **{c.get('n_observed_transition_pairs')}**. "
        f"Eligible (gates B1–B5): **{c.get('n_eligible_pairs')}**.",
        "",
        "## 3. Number of event pairs",
        "",
        f"| Quantity | Value |",
        f"| --- | --- |",
        f"| Independent events | {c.get('n_independent_events')} |",
        f"| Maps | {c.get('n_maps')} |",
        f"| (event, AOI) sequences | {c.get('n_event_aoi_sequences')} |",
        f"| Observed transition pairs | {c.get('n_observed_transition_pairs')} |",
        f"| Eligible pairs (B1–B5) | {c.get('n_eligible_pairs')} |",
        f"| Train / val / test pairs | {c.get('n_train_pairs')} / {c.get('n_val_pairs')} / {c.get('n_test_pairs')} |",
        "",
        "Ten pairs from one flood are **one** independent event.",
        "",
        "## 4. Number of independent events",
        "",
        f"**{c.get('n_independent_events')}** meteorological episodes (45-day rule unchanged). "
        f"Events with at least one pair: **{c.get('n_events_with_pairs')}**. "
        f"Events with maps but no consecutive same-AOI pair: "
        f"{', '.join('`'+e+'`' for e in (c.get('events_without_pairs') or [])) or 'none'}.",
        "",
        "## 5. Delta-t distribution",
        "",
        "The horizon is the measured scene gap. It is not recoded to a product hour.",
        "",
        f"| Statistic | Hours | Days |",
        f"| --- | --- | --- |",
        f"| min | {_fmt((d.get('hours') or {}).get('min'), 2)} | {_fmt((d.get('days') or {}).get('min'), 2)} |",
        f"| q25 | {_fmt((d.get('hours') or {}).get('q25'), 2)} | {_fmt((d.get('days') or {}).get('q25'), 2)} |",
        f"| median | {_fmt((d.get('hours') or {}).get('median'), 2)} | {_fmt((d.get('days') or {}).get('median'), 2)} |",
        f"| mean | {_fmt((d.get('hours') or {}).get('mean'), 2)} | {_fmt((d.get('days') or {}).get('mean'), 2)} |",
        f"| q75 | {_fmt((d.get('hours') or {}).get('q75'), 2)} | {_fmt((d.get('days') or {}).get('q75'), 2)} |",
        f"| max | {_fmt((d.get('hours') or {}).get('max'), 2)} | {_fmt((d.get('days') or {}).get('max'), 2)} |",
        "",
        "| Bucket | Pairs |",
        "| --- | --- |",
    ]
    for name, n in (d.get("buckets") or {}).items():
        lines.append(f"| {name} | {n} |")
    lines.extend(
        [
            "",
            "## 6. Unknown-mask statistics",
            "",
            "UNKNOWN=255 is never scored as dry. A transition is UNKNOWN if either endpoint is unknown.",
            "",
            f"| Quantity | Value |",
            f"| --- | --- |",
            f"| Mean unknown transition fraction | {_fmt(unk.get('mean_unknown_fraction'))} |",
            f"| Mean jointly valid fraction | {_fmt(unk.get('mean_joint_valid_fraction'))} |",
            f"| Mean unknown fraction at t0 maps | {_fmt(unk.get('mean_unknown_t0'))} |",
            f"| Mean unknown fraction at t1 maps | {_fmt(unk.get('mean_unknown_t1'))} |",
            "",
            "## 7. New-flood statistics",
            "",
            f"| Quantity | Value |",
            f"| --- | --- |",
            f"| Mean newly flooded fraction (joint pixels) | {_fmt(ch.get('mean_new_flood_fraction'))} |",
            f"| Median newly flooded fraction | {_fmt(ch.get('median_new_flood_fraction'))} |",
            f"| Pairs with ≥1 newly flooded pixel | {ch.get('n_pairs_with_new_flood')} |",
            f"| Mean n_newly_flooded | {_fmt(ch.get('mean_n_newly_flooded'), 1)} |",
            "",
            "## 8. Recession statistics",
            "",
            f"| Quantity | Value |",
            f"| --- | --- |",
            f"| Mean receding fraction | {_fmt(ch.get('mean_recession_fraction'))} |",
            f"| Median receding fraction | {_fmt(ch.get('median_recession_fraction'))} |",
            f"| Pairs with ≥1 receding pixel | {ch.get('n_pairs_with_recession')} |",
            "",
            "## 9. Persistence statistics",
            "",
            f"| Quantity | Value |",
            f"| --- | --- |",
            f"| Mean IoU(t0, t1) jointly valid | {_fmt(ch.get('mean_iou'))} |",
            f"| Median IoU(t0, t1) | {_fmt(ch.get('median_iou'))} |",
            f"| Mean persistent-flood fraction | {_fmt(ch.get('mean_persistent_flood_fraction'))} |",
            f"| Mean turnover (new + recede) / joint | {_fmt(ch.get('mean_turnover_fraction'))} |",
            "",
            "High IoU with long Δt is genuine haor inundation memory. "
            "Target B does **not** use the 192 h back-offset, so the nearest previous scene is the earlier map by construction.",
            "",
            "## 10. Rainfall completeness",
            "",
            "Required window for the **observed** transition is `(t0, t1]`. "
            "Missing hours are counted; they are **not** interpolated.",
            "",
            f"Lattice coverage: `{fr.get('lattice_start')}` … `{fr.get('lattice_end')}` hourly ERA5-Land / Open-Meteo (`{fr.get('lattice_kind')}`).",
            "",
            f"| Class | Pairs |",
            f"| --- | --- |",
            f"| FORCING_COMPLETE | {fr.get('n_complete')} |",
            f"| FORCING_PARTIAL | {fr.get('n_partial')} |",
            f"| FORCING_MISSING | {fr.get('n_missing')} |",
            f"| Complete fraction | {_fmt(fr.get('complete_pair_fraction'))} |",
            "",
            "Observational completeness is **not** forecast-available forcing. "
            "Rain in `(t0, t1]` is **POST-T0 OBSERVATION**. Using it as a t0 feature would be leakage.",
            "",
            "## 11. Feature availability",
            "",
            "| Input | Status | Kind | Causal at t0? |",
            "| --- | --- | --- | --- |",
            "| Rainfall history before t0 (lattice 72 h) | see pair JSON | PRE-T0 AVAILABLE INPUT | yes, if complete |",
            "| Rainfall during (t0, t1] | observational audit | POST-T0 OBSERVATION | **no** |",
            "| Elevation / slope | AVAILABLE when present on earlier sample | static | yes |",
            "| River distance / mask | AVAILABLE when present | static | yes |",
            "| River discharge | UNAVAILABLE at Target B t0 | cube Q is 192 h-aligned | no (not re-fetched) |",
            "| River level | UNAVAILABLE | — | no |",
            "| Prior flood map | AVAILABLE (earlier GFM scene) | PRE-T0 | yes (state at t0) |",
            "| Later flood map | TARGET | observation at t1 | no |",
            "",
            "## 12. Event-level summaries",
            "",
            "See `event_summaries.json`. Pair counts are nested under events; events remain the independent unit.",
            "",
        ]
    )
    for row in (report.get("event_summaries") or [])[:20]:
        lines.append(
            f"- `{row.get('event_id')}`: {row.get('n_pairs')} pairs, {row.get('n_regions')} AOIs, "
            f"split={row.get('split')}, median Δt h={_fmt(((row.get('delta_t_hours') or {}).get('median')), 1)}, "
            f"mean IoU={_fmt(((row.get('iou') or {}).get('mean')))}, "
            f"mean new-flood={_fmt(((row.get('new_flood_fraction') or {}).get('mean')))}"
        )
    lines.extend(
        [
            "",
            "## 13. Geographic summaries",
            "",
        ]
    )
    for row in report.get("by_region") or []:
        lines.append(
            f"- `{row.get('city_id')}`: {row.get('n_pairs')} pairs / {row.get('n_independent_events')} events, "
            f"mean IoU={_fmt(((row.get('iou') or {}).get('mean')))}, "
            f"mean new-flood={_fmt(((row.get('new_flood_fraction') or {}).get('mean')))}"
        )
    for aoi in (report.get("counts") or {}).get("regions_without_pairs") or []:
        lines.append(f"- `{aoi}`: 0 pairs (maps exist; no consecutive same-AOI scene pair)")
    lines.extend(
        [
            "",
            "## 14. Temporal summaries",
            "",
        ]
    )
    for row in report.get("by_year") or []:
        lines.append(
            f"- {row.get('year')}: {row.get('n_pairs')} pairs / {row.get('n_independent_events')} events, "
            f"mean turnover={_fmt(((row.get('turnover_fraction') or {}).get('mean')))}"
        )
    lines.extend(
        [
            "",
            "By flood mechanism:",
            "",
        ]
    )
    for row in report.get("by_mechanism") or []:
        lines.append(
            f"- `{row.get('flood_mechanism')}`: {row.get('n_pairs')} pairs / {row.get('n_independent_events')} events, "
            f"mean IoU={_fmt(((row.get('iou') or {}).get('mean')))}, "
            f"mean turnover={_fmt(((row.get('turnover_fraction') or {}).get('mean')))}"
        )
    lines.extend(
        [
            "",
            "By Δt bucket (IoU vs change):",
            "",
        ]
    )
    for row in report.get("by_delta_t_bucket") or []:
        lines.append(
            f"- {row.get('delta_t_bucket')}: n={row.get('n_pairs')}, mean IoU={_fmt(((row.get('iou') or {}).get('mean')))}, "
            f"mean new-flood={_fmt(((row.get('new_flood_fraction') or {}).get('mean')))}"
        )
    lines.extend(
        [
            "",
            "## 15. Causal-input limitations",
            "",
            "A forecast issued at t0 may use only information at or before t0.",
            "",
            f"- Pre-t0 lattice rain coverage (pair mean): **{_fmt(fr.get('mean_pre_t0_coverage'))}**.",
            f"- In-horizon observational rain coverage (pair mean): **{_fmt(fr.get('mean_in_horizon_coverage'))}**.",
            f"- Forecast-available in-horizon rain (NWP in cube): **{fr.get('forecast_available_in_horizon')}**.",
            f"- Pearson new-flood fraction vs pre-t0 rain sum: **{_fmt(assoc.get('new_flood_vs_pre_t0_rain'))}**.",
            f"- Pearson new-flood fraction vs in-horizon rain sum (association only): **{_fmt(assoc.get('new_flood_vs_in_horizon_rain'))}**.",
            "",
            "In-horizon rain is tabulated as a diagnostic association. It is not a model feature.",
            "",
            "## 16. Gate B1–B7",
            "",
            f"| Gate | Result | Rule |",
            f"| --- | --- | --- |",
            f"| B1 | {_gate('B1')} | {(gates.get('B1') or {}).get('rule')} |",
            f"| B2 | {_gate('B2')} | {(gates.get('B2') or {}).get('rule')} |",
            f"| B3 | {_gate('B3')} | {(gates.get('B3') or {}).get('rule')} |",
            f"| B4 | {_gate('B4')} | {(gates.get('B4') or {}).get('rule')} |",
            f"| B5 | {_gate('B5')} | {(gates.get('B5') or {}).get('rule')} |",
            f"| B6 | {_gate('B6')} | {(gates.get('B6') or {}).get('rule')} |",
            f"| B7 | {_gate('B7')} | {(gates.get('B7') or {}).get('rule')} |",
            "",
            "Class: **FORECASTABILITY AUDIT**. Not DIAGNOSTICALLY PROMISING / VALIDATED. Official Gate B still requires 20 GFM events.",
            "",
            "## 17. Comparison against the previous 192 h formulation",
            "",
            "| | A@192 h (Track A cube) | Target B |",
            "| --- | --- | --- |",
            "| t0 | `valid_at − 192 h` (SAR-slaved) | earlier scene `valid_at` |",
            "| Horizon | always 192 h | measured Δt |",
            "| Label | occurrence snapshot at later SAR time | NEWLY_FLOODED on jointly valid pixels |",
            "| Persistence feature | previous scene with `valid_at < t0` (nearest scene often illegal if revisit < 8 d) | earlier map **is** the state at t0 |",
            "| Rain in the gap | withheld (correct for a forecast; fatal for rain-driven inundation) | observed for diagnostics; **not** a causal feature |",
            "| 6–72 h product | UNSUPPORTED | still UNSUPPORTED |",
            "",
            "Phase 6.7: GBDT copied persistence on occurrence@192 h. Target B attacks that copy-last-map objective. "
            "It does not create a 24 h GFM map.",
            "",
            "## 18. Whether Target B is scientifically more promising",
            "",
            str(report.get("promising_narrative") or ""),
            "",
            "## 19. What remains missing",
            "",
            "- FORECAST-kind rain / NWP in `(t0, t1]` if Target B is ever trained as a forecast.",
            "- River discharge and wetness aligned to Target B t0 (not the 192 h issue time).",
            "- Official Gate B (20 independent GFM events) still FAIL at 15.",
            "- 6–72 h spatial API maps remain UNSUPPORTED.",
            "- Depth change remains UNSUPPORTED (no GFM depth).",
            "",
            "## 20. Exact next-step recommendation",
            "",
            str(report.get("next_step") or ""),
            "",
            "---",
            "",
            f"TARGET B STATUS: {DECISION_TEXT.get(letter, letter)}",
            "",
            "SPATIAL AI: NOT_VALIDATED",
            "",
            "SPATIAL API: UNAVAILABLE",
            "",
            "MODEL TRAINING: NOT AUTHORIZED",
            "",
            "TRACK A: DIAGNOSTIC ONLY",
            "",
            "TRACK B: SEPARATE HISTORICAL BENCHMARK",
            "",
            "TRACK C: NOT YET IMPLEMENTED",
            "",
            "SOLVER MODIFIED: NO",
            "",
            "END.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_phase68a(
    *,
    processed_dir: Optional[Path] = None,
    samples: Optional[Sequence[SpatialForecastSample]] = None,
    meta: Optional[dict] = None,
    expected_splits: Optional[dict] = None,
    lattice: Optional[dict] = None,
    lattice_index: Optional[LatticeIndex] = None,
    out_dir: Optional[Path] = None,
    write_artifacts: bool = True,
    write_docs: bool = False,
    lock_splits: bool = True,
) -> dict:
    from floodlens.ml.spatial.builder import build_spatial_samples_v2

    if samples is None:
        samples, meta = build_spatial_samples_v2(processed_dir=processed_dir)
    else:
        samples = list(samples)
        meta = meta or {
            "dataset_version": samples[0].dataset_version if samples else None,
            "label_kind": samples[0].label_kind if samples else None,
        }
    if not samples:
        raise RuntimeError(meta.get("reason") if isinstance(meta, dict) else "no Track A samples")

    if lock_splits:
        assert_frozen_splits(samples, expected_splits)
    elif expected_splits is not None:
        assert_frozen_splits(samples, expected_splits)

    if lattice_index is None:
        lattice_index = build_lattice_index(lattice)

    pairs = adjacent_pairs(samples)
    rows = [pair_statistics(a, b, lattice_index) for a, b in pairs]
    eligible = [r for r in rows if (r.get("gates") or {}).get("pair_eligible")]
    inv = inventory(samples)
    event_ids = sorted({(s.extra or {}).get("event_id") for s in samples if (s.extra or {}).get("event_id")})
    events_with_pairs = sorted({r["event_id"] for r in rows if r.get("event_id")})

    hours = summarize_numeric(r.get("delta_t_hours") for r in rows)
    days = summarize_numeric(r.get("delta_t_days") for r in rows)
    buckets = {name: 0 for _, _, name in DELTA_T_BINS}
    for r in rows:
        buckets[r.get("delta_t_bucket") or "12+ days"] = buckets.get(r.get("delta_t_bucket") or "12+ days", 0) + 1

    n_complete = sum(1 for r in rows if r.get("forcing_class") == "FORCING_COMPLETE")
    n_partial = sum(1 for r in rows if r.get("forcing_class") == "FORCING_PARTIAL")
    n_missing = sum(1 for r in rows if r.get("forcing_class") == "FORCING_MISSING")

    assoc = {
        "new_flood_vs_pre_t0_rain": pearson(
            [r.get("fraction_newly_flooded") for r in eligible],
            [(r.get("rainfall_pre_t0") or {}).get("precip_sum_mm") for r in eligible],
        ),
        "new_flood_vs_in_horizon_rain": pearson(
            [r.get("fraction_newly_flooded") for r in eligible],
            [(r.get("rainfall_in_horizon") or {}).get("precip_sum_mm") for r in eligible],
        ),
        "turnover_vs_in_horizon_rain": pearson(
            [r.get("turnover_fraction") for r in eligible],
            [(r.get("rainfall_in_horizon") or {}).get("precip_sum_mm") for r in eligible],
        ),
        "note": "In-horizon rain correlation is an observational association, not a causal feature.",
    }

    spatial_reg = load_spatial_registry()
    counts = {
        "dataset_version": meta.get("dataset_version") or (samples[0].dataset_version if samples else None),
        "n_independent_events": inv.get("n_independent_events") or len(event_ids),
        "n_maps": len(samples),
        "n_event_aoi_sequences": len(
            {((s.extra or {}).get("event_id"), s.city_id) for s in samples if (s.extra or {}).get("event_id")}
        ),
        "n_observed_transition_pairs": len(rows),
        "n_eligible_pairs": len(eligible),
        "n_events_with_pairs": len(events_with_pairs),
        "events_without_pairs": [e for e in event_ids if e not in set(events_with_pairs)],
        "regions_with_maps": sorted({s.city_id for s in samples}),
        "regions_without_pairs": sorted(
            {s.city_id for s in samples} - {r.get("city_id") for r in rows}
        ),
        "n_train_pairs": sum(1 for r in rows if r.get("split") == "train"),
        "n_val_pairs": sum(1 for r in rows if r.get("split") == "val"),
        "n_test_pairs": sum(1 for r in rows if r.get("split") == "test"),
        "event_ids": event_ids,
        "event_gap_days": EVENT_GAP_DAYS,
        "unsupported_horizons_h": list(UNSUPPORTED_HORIZONS_H),
        "target_a_horizon_hours": HORIZON_HOURS,
    }

    change = {
        "mean_iou": (summarize_numeric(r.get("iou_t0_t1") for r in eligible) or {}).get("mean"),
        "median_iou": (summarize_numeric(r.get("iou_t0_t1") for r in eligible) or {}).get("median"),
        "mean_new_flood_fraction": (summarize_numeric(r.get("fraction_newly_flooded") for r in eligible) or {}).get(
            "mean"
        ),
        "median_new_flood_fraction": (summarize_numeric(r.get("fraction_newly_flooded") for r in eligible) or {}).get(
            "median"
        ),
        "mean_recession_fraction": (summarize_numeric(r.get("fraction_receding") for r in eligible) or {}).get("mean"),
        "median_recession_fraction": (summarize_numeric(r.get("fraction_receding") for r in eligible) or {}).get(
            "median"
        ),
        "mean_persistent_flood_fraction": (
            summarize_numeric(r.get("fraction_persistent_flood") for r in eligible) or {}
        ).get("mean"),
        "mean_turnover_fraction": (summarize_numeric(r.get("turnover_fraction") for r in eligible) or {}).get("mean"),
        "n_pairs_with_new_flood": sum(1 for r in eligible if (r.get("n_newly_flooded") or 0) > 0),
        "n_pairs_with_recession": sum(1 for r in eligible if (r.get("n_receding") or 0) > 0),
        "mean_n_newly_flooded": (summarize_numeric(r.get("n_newly_flooded") for r in eligible) or {}).get("mean"),
    }
    unknown_block = {
        "mean_unknown_fraction": (summarize_numeric(r.get("unknown_fraction") for r in rows) or {}).get("mean"),
        "mean_joint_valid_fraction": (summarize_numeric(r.get("joint_valid_fraction") for r in rows) or {}).get("mean"),
        "mean_unknown_t0": (
            summarize_numeric(
                (r.get("unknown_pixels_t0") / r["n_pixels"]) if r.get("n_pixels") else None for r in rows
            )
            or {}
        ).get("mean"),
        "mean_unknown_t1": (
            summarize_numeric(
                (r.get("unknown_pixels_t1") / r["n_pixels"]) if r.get("n_pixels") else None for r in rows
            )
            or {}
        ).get("mean"),
        "unknown_never_dry": True,
    }
    forcing = {
        "n_complete": n_complete,
        "n_partial": n_partial,
        "n_missing": n_missing,
        "complete_pair_fraction": (n_complete / len(rows)) if rows else None,
        "mean_pre_t0_coverage": (summarize_numeric(r.get("pre_t0_input_coverage") for r in rows) or {}).get("mean"),
        "mean_in_horizon_coverage": (summarize_numeric(r.get("in_horizon_rain_coverage") for r in rows) or {}).get(
            "mean"
        ),
        "forecast_available_in_horizon": False,
        "lattice_start": None if lattice_index is None else lattice_index.start,
        "lattice_end": None if lattice_index is None else lattice_index.end,
        "lattice_kind": None if lattice_index is None else lattice_index.kind,
        "filled": False,
    }

    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "experiment_id": EXPERIMENT_ID,
        "catalog_status": "NOT_VALIDATED",
        "public_spatial_status": public_spatial_status(spatial_reg),
        "spatial_registry_status": spatial_reg.get("status"),
        "promoted_to_validated": False,
        "spatial_api": "UNAVAILABLE",
        "model_training": "NOT AUTHORIZED",
        "cnn_trained": False,
        "solver_modified": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
        "target": "TARGET_B_NEWLY_FLOODED",
        "t0_definition": "earlier.valid_at",
        "horizon_definition": "measured_delta_t",
        "counts": counts,
        "delta_t": {"hours": hours, "days": days, "buckets": buckets},
        "change": change,
        "unknown": unknown_block,
        "forcing": forcing,
        "association": assoc,
        "pairs": rows,
        "event_summaries": event_level_summaries(rows, samples),
        "by_region": aggregate_by(rows, "city_id"),
        "by_year": aggregate_by(rows, "year"),
        "by_mechanism": aggregate_by(rows, "flood_mechanism"),
        "by_delta_t_bucket": aggregate_by(rows, "delta_t_bucket"),
        "by_split": aggregate_by(rows, "split"),
        "gates": evaluate_gates_b(rows, counts["n_independent_events"], counts["n_events_with_pairs"]),
        "frozen_splits_locked": bool(lock_splits or expected_splits is not None),
        "cross_event_calendar_pairs_excluded": True,
    }
    letter = decide_letter(report)
    report["decision_letter"] = letter
    report["decision"] = DECISION_TEXT[letter]

    turn = change.get("mean_turnover_fraction")
    iou = change.get("mean_iou")
    report["promising_narrative"] = (
        f"Target B is an honest change label: mean jointly-valid IoU(t0,t1)="
        f"{None if _finite(iou) is None else round(float(iou), 3)}, "
        f"mean turnover={None if _finite(turn) is None else round(float(turn), 3)}, "
        f"{change.get('n_pairs_with_new_flood')} eligible pairs show new inundation. "
        f"That is more interpretable than occurrence@192 h, which Phase 6.7 showed is dominated by persistence/climatology. "
        f"It is **not** automatically a better *forecast*: in-horizon rain is POST-T0 OBSERVATION "
        f"(forecast-available NWP in the cube: {forcing.get('forecast_available_in_horizon')}; "
        f"observational completeness "
        f"{None if forcing.get('complete_pair_fraction') is None else round(float(forcing.get('complete_pair_fraction')), 3)}). "
        f"Letter E is withheld: 6–72 h spatial maps remain unsupported, official event n is 15, "
        f"and replacing Track A as a product target requires forecast-kind forcing, not a prettier diagnostic."
    )
    if letter == "B":
        report["next_step"] = (
            "Keep Target B as the observational change diagnostic. Do not train yet. "
            "Next authorized step, if any: add FORECAST-kind (NWP) rain for `(t0, t1]` as an explicit forcing layer, "
            "or a no-training study of whether pre-t0 rain + state at t0 can rank new-flood pixels. "
            "Do not invent 24 h GFM maps. Do not enable `/api/v1/forecast/ai-spatial`."
        )
    elif letter == "C":
        report["next_step"] = (
            "A later phase may run Target B diagnostic baselines (zero-change, climatology of expansion, pixel GBDT) "
            "with causal pre-t0 features only. Still not VALIDATED. Still no CNN."
        )
    elif letter == "D":
        report["next_step"] = (
            "Expand independent GFM events before Target B baselines. Do not treat additional pairs inside existing floods as new events."
        )
    elif letter == "A":
        report["next_step"] = (
            "Do not adopt Target B. Document why pairing or jointly valid coverage failed. Keep A@192 h as a diagnostic cube only."
        )
    else:
        report["next_step"] = (
            "Do not promote Target B to the primary Track A product target in this phase. "
            "6–72 h maps remain unsupported."
        )

    if write_artifacts:
        dest = Path(out_dir or OUT_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        payload = _jsonable(report)
        slim_pairs = list(rows)
        (dest / "config.json").write_text(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "dataset_version": counts.get("dataset_version"),
                    "t0_definition": "earlier.valid_at",
                    "horizon": "measured_delta_t",
                    "unknown": UNKNOWN,
                    "event_gap_days": EVENT_GAP_DAYS,
                    "rng_seed": RNG_SEED,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / "transition_pairs.json").write_text(json.dumps(_jsonable(slim_pairs), indent=2), encoding="utf-8")
        (dest / "transition_statistics.json").write_text(json.dumps(_jsonable(change), indent=2), encoding="utf-8")
        (dest / "rainfall_completeness.json").write_text(json.dumps(_jsonable(forcing), indent=2), encoding="utf-8")
        (dest / "delta_t_distribution.json").write_text(json.dumps(_jsonable(report["delta_t"]), indent=2), encoding="utf-8")
        (dest / "event_summaries.json").write_text(
            json.dumps(_jsonable(report["event_summaries"]), indent=2), encoding="utf-8"
        )
        (dest / "gate_results.json").write_text(json.dumps(_jsonable(report["gates"]), indent=2), encoding="utf-8")
        (dest / "phase68a_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        md = write_markdown_report(report)
        (dest / "PHASE_6_8A_TARGET_B_DIAGNOSTIC_REPORT.md").write_text(md, encoding="utf-8")
        if write_docs:
            REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            DOCS_REPORT.write_text(md, encoding="utf-8")
            report["report_md"] = str(DOCS_REPORT)
        report["artifact_dir"] = str(dest)
    return report
