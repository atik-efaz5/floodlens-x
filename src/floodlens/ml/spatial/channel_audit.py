"""Per-channel spatial/temporal audit. Convolution is forbidden without spatial fields."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from floodlens.ml.spatial.schema import SpatialForecastSample

SPATIAL = "SPATIAL"
TEMPORAL_ONLY = "TEMPORAL-ONLY"
CONSTANT = "CONSTANT"
MISSING = "MISSING"
MIN_SPATIAL_CHANNELS = 4
# Within-tile variance below this is treated as constant (broadcast).
SPATIAL_VAR_EPS = 1e-8


def _map_from_sample(sample: SpatialForecastSample, name: str) -> Optional[np.ndarray]:
    extra = sample.extra or {}
    if name == "precip_24h":
        arr = extra.get("precip_24h_map")
        if arr is None:
            h, w = sample.y_flood.shape
            return np.full((h, w), float(sample.x_antecedent_24h or 0.0))
        return np.asarray(arr, dtype=np.float64)
    if name == "precip_72h":
        arr = extra.get("precip_72h_map")
        if arr is None:
            h, w = sample.y_flood.shape
            windows = extra.get("precip_windows") or {}
            val = float(sample.x_antecedent_72h or windows.get(72) or 0.0)
            return np.full((h, w), val)
        return np.asarray(arr, dtype=np.float64)
    if name == "log1p_q":
        q = sample.x_glofas_q_lookback or []
        q_last = float(q[-1]) if q and q[-1] is not None else 0.0
        h, w = sample.y_flood.shape
        return np.full((h, w), np.log1p(max(q_last, 0.0)))
    if name == "month_sin":
        month = int(sample.issue_time[5:7])
        h, w = sample.y_flood.shape
        return np.full((h, w), np.sin(2 * np.pi * month / 12.0))
    if name == "month_cos":
        month = int(sample.issue_time[5:7])
        h, w = sample.y_flood.shape
        return np.full((h, w), np.cos(2 * np.pi * month / 12.0))
    if name == "persistence":
        if sample.x_persistence is None:
            return None
        return np.asarray(sample.x_persistence, dtype=np.float64)
    if name == "persistence_valid":
        if sample.x_persistence is None:
            h, w = sample.y_flood.shape
            return np.zeros((h, w))
        return np.isfinite(np.asarray(sample.x_persistence)).astype(np.float64)
    if name == "precip_is_aoi_point":
        h, w = sample.y_flood.shape
        return np.full((h, w), 1.0 if sample.precip_is_aoi_point else 0.0)
    if name == "dem":
        return None if sample.x_dem is None else np.asarray(sample.x_dem, dtype=np.float64)
    if name == "slope":
        arr = extra.get("slope")
        return None if arr is None else np.asarray(arr, dtype=np.float64)
    if name == "river_distance":
        arr = extra.get("river_distance")
        return None if arr is None else np.asarray(arr, dtype=np.float64)
    if name == "precip_intensity_24h":
        arr = extra.get("precip_intensity_24h_map")
        return None if arr is None else np.asarray(arr, dtype=np.float64)
    if name == "height_above_river":
        arr = extra.get("height_above_river")
        return None if arr is None else np.asarray(arr, dtype=np.float64)
    raise KeyError(name)


CHANNEL_NAMES = (
    "precip_24h",
    "precip_72h",
    "log1p_q",
    "month_sin",
    "month_cos",
    "persistence",
    "persistence_valid",
    "precip_is_aoi_point",
    "dem",
    "slope",
    "river_distance",
    "precip_intensity_24h",
    "height_above_river",
)


def classify_stack(maps: Sequence[Optional[np.ndarray]]) -> dict:
    """Classify one channel across tiles: spatial vs temporal-only vs constant vs missing."""
    present = [np.asarray(m, dtype=np.float64) for m in maps if m is not None]
    if not present:
        return {
            "class": MISSING,
            "spatial_variance": None,
            "temporal_variance": None,
            "unique_value_fraction": None,
            "missingness": 1.0,
            "n_tiles": 0,
        }
    spatial_vars = []
    means = []
    unique_fracs = []
    miss = []
    for arr in present:
        finite = np.isfinite(arr)
        miss.append(1.0 - float(np.mean(finite)) if arr.size else 1.0)
        vals = arr[finite]
        if vals.size == 0:
            spatial_vars.append(0.0)
            unique_fracs.append(0.0)
            means.append(float("nan"))
            continue
        spatial_vars.append(float(np.var(vals)))
        unique_fracs.append(float(len(np.unique(np.round(vals, 6)))) / float(vals.size))
        means.append(float(np.mean(vals)))
    spatial_var = float(np.mean(spatial_vars))
    finite_means = [m for m in means if np.isfinite(m)]
    temporal_var = float(np.var(finite_means)) if len(finite_means) > 1 else 0.0
    unique_frac = float(np.mean(unique_fracs))
    missingness = float(np.mean(miss))
    if spatial_var > SPATIAL_VAR_EPS:
        klass = SPATIAL
    elif temporal_var > SPATIAL_VAR_EPS:
        klass = TEMPORAL_ONLY
    else:
        klass = CONSTANT
    return {
        "class": klass,
        "spatial_variance": spatial_var,
        "temporal_variance": temporal_var,
        "unique_value_fraction": unique_frac,
        "missingness": missingness,
        "n_tiles": len(present),
        "geographic_coverage": sorted({}),  # filled by caller
    }


def audit_channels(samples: Sequence[SpatialForecastSample]) -> dict:
    rows: Dict[str, dict] = {}
    cities = sorted({s.city_id for s in samples})
    for name in CHANNEL_NAMES:
        maps = [_map_from_sample(s, name) for s in samples]
        row = classify_stack(maps)
        row["geographic_coverage"] = cities
        rows[name] = row
    n_spatial = sum(1 for r in rows.values() if r["class"] == SPATIAL)
    return {
        "channels": rows,
        "n_spatial": n_spatial,
        "min_spatial_required": MIN_SPATIAL_CHANNELS,
        "cnn_allowed": n_spatial >= MIN_SPATIAL_CHANNELS,
        "note": (
            "A convolutional model needs within-tile spatial variance. "
            "Broadcast rain/Q/month are TEMPORAL-ONLY, not spatial features."
        ),
    }


def refuse_cnn(audit: dict) -> Optional[str]:
    if audit.get("cnn_allowed"):
        return None
    return (
        f"CNN refused: {audit.get('n_spatial', 0)} spatial channels "
        f"< {MIN_SPATIAL_CHANNELS}. Do not train a U-Net on broadcast features."
    )
