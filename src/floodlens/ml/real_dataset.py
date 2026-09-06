"""Build leakage-safe ForecastSamples from the Open-Meteo GloFAS + precip snapshot.

Labels are MODELLED (GloFAS river discharge exceedance), not field observations.
Horizons 6h and 12h are not labeled: daily Q cannot support sub-daily targets.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.acquire_openmeteo import REAL_DIR
from floodlens.ml.leakage import assert_no_leakage, parse_ts
from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample
from floodlens.ml.splits import assign_temporal, by_split

REAL_DATASET_VERSION = "phase4.5-openmeteo-glofas-v1"
REAL_HORIZONS = (24, 48, 72)
Q_LOOKBACK_DAYS = 7
ISSUE_HOUR = 0


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_RAW_CACHE: dict = {}
_SAMPLE_CACHE: dict = {}


def load_raw(real_dir: Optional[Path] = None) -> Tuple[dict, dict, dict]:
    real_dir = Path(real_dir or REAL_DIR)
    key = str(real_dir)
    if key in _RAW_CACHE:
        return _RAW_CACHE[key]
    disc_path = real_dir / "discharge_2015_2024.json"
    precip_path = real_dir / "precip_2014_2024.json"
    manifest_path = real_dir / "manifest.json"
    if not disc_path.exists() or not precip_path.exists():
        raise FileNotFoundError(
            "Real Open-Meteo snapshot missing. Run scripts/phase45_acquire_openmeteo.py"
        )
    discharge = json.loads(disc_path.read_text(encoding="utf-8"))
    precip = json.loads(precip_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    _RAW_CACHE[key] = (discharge, precip, manifest)
    return _RAW_CACHE[key]


def snapshot_available(real_dir: Optional[Path] = None) -> bool:
    real_dir = Path(real_dir or REAL_DIR)
    return (real_dir / "discharge_2015_2024.json").exists() and (
        real_dir / "precip_2014_2024.json"
    ).exists()


def _index_series(times: Sequence[str], values: Sequence) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for t, v in zip(times, values):
        key = str(t)[:10] if len(str(t)) == 10 else str(t).replace("Z", "")
        out[key] = None if v is None else float(v)
    return out


def _index_hourly(times: Sequence[str], values: Sequence) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for t, v in zip(times, values):
        stamp = str(t).replace("Z", "")
        if len(stamp) == 16:
            stamp = stamp + ":00"
        out[stamp] = None if v is None else float(v)
    return out


def empirical_q2_thresholds(discharge: dict, train_end_year: int = 2021) -> Tuple[Dict[str, float], Dict[str, dict]]:
    """2-year RP ≈ median of annual maxima on TRAIN years only."""
    thresholds: Dict[str, float] = {}
    ams: Dict[str, dict] = {}
    for city_id, payload in (discharge.get("cities") or {}).items():
        by_year: Dict[int, float] = {}
        for day, q in zip(payload["time"], payload["river_discharge_m3s"]):
            if q is None:
                continue
            year = int(str(day)[:4])
            if year > train_end_year:
                continue
            by_year[year] = max(by_year.get(year, 0.0), float(q))
        series = np.array(list(by_year.values()), dtype=np.float64)
        if series.size == 0:
            raise ValueError(f"no train-period annual maxima for {city_id}")
        thresholds[city_id] = float(np.median(series))
        ams[city_id] = {str(y): by_year[y] for y in sorted(by_year)}
    return thresholds, ams


def build_real_samples(
    real_dir: Optional[Path] = None,
    horizons: Sequence[int] = REAL_HORIZONS,
) -> Tuple[List[ForecastSample], dict]:
    cache_key = (str(Path(real_dir or REAL_DIR)), tuple(horizons))
    if cache_key in _SAMPLE_CACHE:
        return _SAMPLE_CACHE[cache_key]
    discharge, precip, manifest = load_raw(real_dir)
    thresholds, ams = empirical_q2_thresholds(discharge)
    samples: List[ForecastSample] = []
    for city_id, q_payload in (discharge.get("cities") or {}).items():
        p_payload = (precip.get("cities") or {})[city_id]
        q_daily = _index_series(q_payload["time"], q_payload["river_discharge_m3s"])
        p_hourly = _index_hourly(p_payload["time"], p_payload["precipitation_mm"])
        q_thr = thresholds[city_id]
        days = sorted(q_daily.keys())
        for day in days:
            issue = parse_ts(day + "T00:00:00Z")
            if issue.year < 2015 or issue.year > 2024:
                continue
            # Need lookback ending at issue (t), not including future hours.
            look_vals = []
            look_kinds = []
            complete = 0
            for h in range(LOOKBACK_HOURS, 0, -1):
                stamp = (issue - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
                val = p_hourly.get(stamp)
                if val is None:
                    look_vals.append(0.0)
                    look_kinds.append("UNAVAILABLE")
                else:
                    look_vals.append(float(val))
                    look_kinds.append("OBSERVED")
                    complete += 1
            frac = complete / float(LOOKBACK_HOURS)
            if frac < 0.80:
                continue
            windows = {}
            for width in (1, 3, 6, 12, 24, 48, 72):
                acc = []
                miss = 0
                for h in range(1, width + 1):
                    stamp = (issue - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
                    val = p_hourly.get(stamp)
                    if val is None:
                        miss += 1
                    else:
                        acc.append(float(val))
                windows[width] = float(sum(acc)) if (width - miss) / width >= 0.80 else None
            if windows[24] is None:
                continue
            q_hist: List[Optional[float]] = []
            for d in range(Q_LOOKBACK_DAYS, 0, -1):
                key = (issue - timedelta(days=d)).strftime("%Y-%m-%d")
                qv = q_daily.get(key)
                q_hist.append(None if qv is None else float(qv))
            if q_hist[-1] is None:
                continue
            y_now = int(q_hist[-1] >= q_thr)
            for horizon in horizons:
                valid = issue + timedelta(hours=horizon)
                vkey = valid.strftime("%Y-%m-%d")
                q_future = q_daily.get(vkey)
                if q_future is None:
                    y_a = None
                    unknown = True
                else:
                    y_a = int(float(q_future) >= q_thr)
                    unknown = False
                if unknown:
                    continue
                sample = ForecastSample(
                    city_id=city_id,
                    issue_time=_iso(issue),
                    horizon_hours=int(horizon),
                    valid_at=_iso(valid),
                    x_precip_hourly=look_vals,
                    x_precip_hourly_kind=look_kinds,
                    x_precip_forecast_to_h=None,
                    x_precip_forecast_issued_at=None,
                    x_antecedent_24h=float(windows[24]),
                    x_antecedent_72h=windows.get(72),
                    x_dem_stats=None,
                    x_glofas_q_lookback=q_hist,
                    y_track_a=y_a,
                    y_track_b=None,
                    y_track_b_available=False,
                    lookback_complete_frac=frac,
                    label_source="open-meteo-glofas-v4-reanalysis",
                    label_kind="MODELLED",
                    issue_precip_forecast_id=None,
                    dataset_version=REAL_DATASET_VERSION,
                    missing_flags={
                        "dem": True,
                        "in_situ_gauge": True,
                        "forecast_precip_issued_at_t": True,
                        "precip_48h": windows.get(48) is None,
                        "precip_72h": windows.get(72) is None,
                    },
                    extra={
                        "y_at_issue": y_now,
                        "data_status": "REAL",
                        "q_threshold_m3s": q_thr,
                        "q_threshold_rule": "median_annual_maxima_train_2015_2021",
                        "precip_windows": {int(k): v for k, v in windows.items() if v is not None},
                        "grid_lat": q_payload.get("grid_lat"),
                        "grid_lon": q_payload.get("grid_lon"),
                        "track_a_note": (
                            "Positive if GloFAS daily Q on valid_at UTC date >= train-only "
                            "empirical 2-year threshold. MODELLED hydrology, not a gauge."
                        ),
                    },
                )
                samples.append(sample)
    assign_temporal(samples)
    if len(samples) > 400:
        assert_no_leakage(samples[:: max(1, len(samples) // 400)])
    else:
        assert_no_leakage(samples)
    meta = {
        "dataset_version": REAL_DATASET_VERSION,
        "n": len(samples),
        "label_kind": "MODELLED",
        "horizons": list(horizons),
        "q_thresholds_m3s": thresholds,
        "annual_maxima_train": ams,
        "splits": {
            name: sum(1 for s in samples if s.split == name) for name in ("train", "val", "test")
        },
        "cities": sorted({s.city_id for s in samples}),
        "manifest": manifest,
        "source_files": [
            "src/floodlens/application/data/ml/real/discharge_2015_2024.json",
            "src/floodlens/application/data/ml/real/precip_2014_2024.json",
        ],
        "positive": "GloFAS daily river_discharge on valid_at date >= train-period median AMS (≈2-year RP)",
        "negative": "modelled Q below that threshold",
        "unknown": "missing Q; dropped, never treated as dry",
        "not_horizons": [6, 12],
        "not_horizons_reason": "Labels are daily. Sub-daily 6h/12h targets would be fake.",
    }
    _SAMPLE_CACHE[cache_key] = (samples, meta)
    return samples, meta


SNAPSHOT_Q_END = "2024-12-31"


def q_lookback_before_issue(
    city_id: str,
    issue: datetime,
    real_dir: Optional[Path] = None,
    allow_live: bool = True,
) -> Optional[dict]:
    """Seven daily Q values for days t-7 … t-1 (issue-day Q excluded).

    Live Open-Meteo flood API is preferred when ``issue`` is after the committed
    snapshot. The 2015–2024 snapshot is used only for hindcast dates inside
    that range. Missing Q is unknown, never filled with zero-as-dry.
    """
    end_day = (issue - timedelta(days=1)).strftime("%Y-%m-%d")
    start_day = (issue - timedelta(days=Q_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    series: Dict[str, Optional[float]] = {}
    source = "unavailable"
    issue_day = issue.strftime("%Y-%m-%d")
    if issue_day <= SNAPSHOT_Q_END:
        discharge, _, _ = load_raw(real_dir)
        payload = (discharge.get("cities") or {}).get(city_id)
        if payload:
            series = _index_series(payload["time"], payload["river_discharge_m3s"])
            source = "snapshot_2015_2024"
    if (not series or any(series.get((issue - timedelta(days=d)).strftime("%Y-%m-%d")) is None
                          for d in range(1, Q_LOOKBACK_DAYS + 1))) and allow_live:
        from floodlens.ml.dataset_builder import city_centers
        from floodlens.ml.sources import FLOOD_URL, http_get_json

        centers = city_centers()
        if city_id in centers:
            lat, lon = centers[city_id]
            url = FLOOD_URL.format(lat=lat, lon=lon, start=start_day, end=end_day)
            payload = http_get_json(url, timeout=12)
            daily = (payload or {}).get("daily") or {}
            times = daily.get("time") or []
            values = daily.get("river_discharge") or []
            if times:
                live = _index_series(times, values)
                series = {**series, **live}
                source = "open-meteo-flood-live" if issue_day > SNAPSHOT_Q_END else "snapshot+live"
    values: List[Optional[float]] = []
    for d in range(Q_LOOKBACK_DAYS, 0, -1):
        key = (issue - timedelta(days=d)).strftime("%Y-%m-%d")
        values.append(None if not series else series.get(key))
    if values[-1] is None:
        return None
    return {"values": values, "source": source, "start_day": start_day, "end_day": end_day}


def assign_geographic_holdout(samples: Sequence[ForecastSample], test_city: str) -> List[ForecastSample]:
    """Relabel split in-place copies of the split field only (no deep copy)."""
    out = []
    for sample in samples:
        sample.split = "test" if sample.city_id == test_city else "train"
        out.append(sample)
    return out
