"""Build ForecastSample rows. Synthetic development set is labeled SIMULATED."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from floodlens.application.city_data import create_city_registry
from floodlens.ml.leakage import assert_no_leakage, parse_ts
from floodlens.ml.schema import (
    DATASET_VERSION,
    HORIZONS,
    ISSUE_STRIDE_HOURS,
    LOOKBACK_HOURS,
    ForecastSample,
)
from floodlens.ml.splits import assign_temporal
from floodlens.ml.sources import emsr_catalog, openmeteo_sample

CITIES = ("sunamganj", "dhaka", "sylhet")
GEO_TRAIN_CITIES = ("meghna_holdout",)


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _precip_series(city_id: str, n_hours: int, start: datetime, rng: np.random.Generator) -> np.ndarray:
    hours = np.arange(n_hours)
    month = np.array([(start + timedelta(hours=int(h))).month for h in hours])
    monsoon = ((month >= 5) & (month <= 9)).astype(np.float64)
    base = 0.15 + 2.2 * monsoon
    diurnal = 0.4 * (1.0 + np.sin(2 * np.pi * (hours % 24) / 24.0))
    # Occasional intense storms that persist ~36 h — delayed flood labels follow.
    storm = np.zeros(n_hours)
    n_storms = max(4, n_hours // 400)
    for _ in range(n_storms):
        t0 = int(rng.integers(48, n_hours - 80))
        width = int(rng.integers(18, 40))
        peak = float(rng.uniform(8.0, 22.0))
        storm[t0 : t0 + width] += peak * np.exp(-0.5 * ((np.arange(width) - width / 3.0) / (width / 4.0)) ** 2)
    noise = rng.gamma(0.6, 0.5, size=n_hours)
    city_scale = {"sunamganj": 1.15, "dhaka": 0.85, "sylhet": 1.05, "meghna_holdout": 1.0}.get(city_id, 1.0)
    return np.clip((base + diurnal + storm + noise) * city_scale, 0.0, None)


def _antecedent(values: np.ndarray, end_idx: int, hours: int) -> float:
    start = max(0, end_idx - hours + 1)
    window = values[start : end_idx + 1]
    if window.size == 0:
        return 0.0
    return float(np.sum(window))


def build_synthetic_samples(
    start: str = "2020-01-01T00:00:00Z",
    end: str = "2024-03-01T00:00:00Z",
    cities: Sequence[str] = CITIES,
    seed: int = 7,
    include_geographic_extra: bool = False,
    stride_hours: int = 24,
) -> List[ForecastSample]:
    """Leakage-safe development series. Track A is modelled-style, not observations."""
    rng = np.random.default_rng(seed)
    t0 = parse_ts(start)
    t1 = parse_ts(end)
    n_hours = int((t1 - t0).total_seconds() // 3600) + 24
    city_list = list(cities)
    if include_geographic_extra:
        city_list = city_list + list(GEO_TRAIN_CITIES)
    samples: List[ForecastSample] = []
    for city_id in city_list:
        precip = _precip_series(city_id, n_hours, t0, rng)
        # Track A: delayed catchment response — flood if 24–48 h antecedent is high.
        flood_daily = np.zeros(n_hours, dtype=np.int32)
        for h in range(24, n_hours):
            acc = float(np.sum(precip[h - 24 : h]))
            flood_daily[h] = 1 if acc > 48.0 else 0
        issue = t0 + timedelta(hours=LOOKBACK_HOURS + 72)
        while issue < t1 - timedelta(hours=72):
            idx = int((issue - t0).total_seconds() // 3600)
            look = precip[idx - LOOKBACK_HOURS + 1 : idx + 1]
            if look.size < LOOKBACK_HOURS:
                issue += timedelta(hours=stride_hours)
                continue
            complete = float(np.isfinite(look).mean())
            if complete < 0.80:
                issue += timedelta(hours=stride_hours)
                continue
            ant24 = float(np.sum(look))
            ant72 = _antecedent(precip, idx, 72)
            y_now = int(flood_daily[idx])
            for horizon in HORIZONS:
                valid = issue + timedelta(hours=horizon)
                vidx = idx + horizon
                if vidx >= n_hours:
                    continue
                y_a = int(flood_daily[vidx])
                sample = ForecastSample(
                    city_id=city_id,
                    issue_time=_iso(issue),
                    horizon_hours=int(horizon),
                    valid_at=_iso(valid),
                    x_precip_hourly=[float(x) for x in look],
                    x_precip_hourly_kind=["SIMULATED"] * LOOKBACK_HOURS,
                    x_precip_forecast_to_h=None,
                    x_precip_forecast_issued_at=None,
                    x_antecedent_24h=ant24,
                    x_antecedent_72h=ant72,
                    x_dem_stats=None,
                    x_glofas_q_lookback=None,
                    y_track_a=y_a,
                    y_track_b=None,
                    y_track_b_available=False,
                    lookback_complete_frac=complete,
                    label_source="synthetic-glofas-proxy",
                    label_kind="MODELLED",
                    issue_precip_forecast_id=None,
                    extra={
                        "y_at_issue": y_now,
                        "data_status": "SIMULATED",
                        "track_a_note": "Synthetic delayed-runoff flag standing in for GloFAS RP exceedance. Not observations.",
                    },
                )
                samples.append(sample)
            issue += timedelta(hours=stride_hours)
    assign_temporal(samples)
    assert_no_leakage(samples)
    return samples


def samples_from_openmeteo_sample() -> List[ForecastSample]:
    """Build samples from the committed 7-day REAL archive extract (labels unavailable)."""
    blob = openmeteo_sample()
    samples: List[ForecastSample] = []
    for city_id, payload in (blob.get("cities") or {}).items():
        times = payload.get("time") or []
        vals = payload.get("precipitation_mm") or []
        if len(times) < LOOKBACK_HOURS + max(HORIZONS):
            continue
        for i in range(LOOKBACK_HOURS, len(times) - max(HORIZONS), ISSUE_STRIDE_HOURS):
            issue = parse_ts(times[i])
            look_t = times[i - LOOKBACK_HOURS + 1 : i + 1]
            look_v = [float(v or 0.0) for v in vals[i - LOOKBACK_HOURS + 1 : i + 1]]
            if len(look_v) < LOOKBACK_HOURS:
                continue
            for horizon in HORIZONS:
                v_i = i + horizon
                if v_i >= len(times):
                    continue
                samples.append(
                    ForecastSample(
                        city_id=city_id,
                        issue_time=_iso(issue),
                        horizon_hours=int(horizon),
                        valid_at=_iso(parse_ts(times[v_i])),
                        x_precip_hourly=look_v,
                        x_precip_hourly_kind=["OBSERVED"] * LOOKBACK_HOURS,
                        x_precip_forecast_to_h=None,
                        x_precip_forecast_issued_at=None,
                        x_antecedent_24h=float(sum(look_v)),
                        x_antecedent_72h=None,
                        x_dem_stats=None,
                        x_glofas_q_lookback=None,
                        y_track_a=None,
                        y_track_b=None,
                        y_track_b_available=False,
                        lookback_complete_frac=1.0,
                        label_source="open-meteo-sample",
                        label_kind="MODELLED",
                        issue_precip_forecast_id=None,
                        extra={"data_status": blob.get("data_status", "REAL"), "openmeteo_times": look_t},
                    )
                )
    assign_temporal(samples)
    assert_no_leakage(samples)
    return samples


def write_jsonl(samples: Sequence[ForecastSample], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.to_dict()) + "\n")
    meta = {
        "dataset_version": DATASET_VERSION,
        "n": len(samples),
        "format": "jsonl",
        "parquet": "optional; pyarrow not required. JSONL is the MVP store.",
        "cities": sorted({s.city_id for s in samples}),
        "splits": {
            name: sum(1 for s in samples if s.split == name)
            for name in ("train", "val", "test")
        },
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def read_jsonl(path: Path) -> List[ForecastSample]:
    samples = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            samples.append(ForecastSample.from_dict(json.loads(line)))
    return samples


def try_write_parquet(samples: Sequence[ForecastSample], path: Path) -> Optional[Path]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return None
    table = pa.Table.from_pylist([s.to_dict() for s in samples])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def historical_events_from_catalog() -> List[dict]:
    catalog = emsr_catalog()
    events = []
    for row in catalog.get("cited_public_activations") or []:
        events.append(
            {
                "event_id": row["code"],
                "name": row["name"],
                "region": "Bangladesh",
                "start_time": row.get("event_time_utc"),
                "end_time": row.get("activation_time_utc"),
                "source": row.get("source_url"),
                "data_status": "UNAVAILABLE",
                "observed_flood_extent": None,
                "observations": {},
                "metadata": {
                    "label_kind": "OBSERVED",
                    "polygons_downloaded": False,
                    "intersects_mvp_aois": row.get("intersects_mvp_aois"),
                    "y_track_b_available": False,
                    "note": row.get("intersects_reason"),
                },
            }
        )
    for row in catalog.get("named_holdout_events_not_in_emsr_public_list") or []:
        window = row.get("window_utc") or [None, None]
        events.append(
            {
                "event_id": "holdout-2022-ne-bangladesh",
                "name": row["name"],
                "region": "sylhet,sunamganj",
                "start_time": window[0],
                "end_time": window[1],
                "source": "GloFAS news / International Charter; no EMSR code invented",
                "data_status": "UNAVAILABLE",
                "observed_flood_extent": None,
                "observations": {},
                "metadata": {
                    "split": row.get("split"),
                    "y_track_b_available": False,
                    "note": row.get("note"),
                },
            }
        )
    return events


def city_centers() -> Dict[str, tuple]:
    registry = create_city_registry()
    out = {}
    for city_id in CITIES:
        city = registry.get_city(city_id)
        out[city_id] = (city.center_lat, city.center_lon)
    return out


def as_synthetic_track_b(samples: Sequence[ForecastSample], keep_frac: float = 0.2, seed: int = 11) -> List[ForecastSample]:
    """Sparse mapped-event analog. Not real EMSR polygons. For Track B pipeline tests only."""
    rng = np.random.default_rng(seed)
    out = []
    for sample in samples:
        row = ForecastSample.from_dict(sample.to_dict())
        if rng.random() < keep_frac and row.y_track_a is not None:
            row.y_track_b = int(row.y_track_a)
            row.y_track_b_available = True
            row.label_kind = "OBSERVED"
            row.label_source = "synthetic-mapped-event"
            extra = dict(row.extra or {})
            extra["track_b_note"] = (
                "Synthetic sparse mapped subset for pipeline tests. Not CEMS polygons."
            )
            row.extra = extra
        else:
            row.y_track_b = None
            row.y_track_b_available = False
        out.append(row)
    return out
