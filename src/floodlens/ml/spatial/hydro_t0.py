"""Target-B GloFAS reanalysis Q reindexed to t0.

MODELLED/REANALYSIS state only. Never labelled FORECAST.
Does not couple the numerical solver. Does not modify cube samples.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from floodlens.ml.leakage import hours_between, parse_ts
from floodlens.ml.real_dataset import Q_LOOKBACK_DAYS, load_raw
from floodlens.ml.spatial.aois_v2 import q_proxy_city
from floodlens.ml.spatial.forecast_forcing import MODELLED_STATE, UNAVAILABLE, state_timestamp_at_or_before_t0
from floodlens.ml.spatial.phase69 import last_complete_q_day

# Daily GloFAS completeness: lag is measured from the end of the last complete
# Q calendar day, not from the 00:00 date stamp (which would mark every noon t0 STALE).
FRESH_LAG_HOURS = 24.0
STALE_LAG_HOURS = 72.0
MAX_WALKBACK_DAYS = 14
SOURCE_ID = "glofas-reanalysis-open-meteo"
SOURCE_VERSION = "open-meteo-glofas-v4-reanalysis-2015-2024"
PROCESSING_VERSION = "phase6.9a-hydro-t0-v1"
UNITS = "m3 s-1"
RESOLUTION = "daily 0.05deg proxy cell"


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_staleness(lag_hours: Optional[float]) -> str:
    if lag_hours is None:
        return "MISSING"
    if lag_hours <= FRESH_LAG_HOURS:
        return "FRESH"
    if lag_hours <= STALE_LAG_HOURS:
        return "STALE"
    return "VERY_STALE"


def index_daily_q(times: Sequence[str], values: Sequence) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for stamp, val in zip(times, values):
        key = str(stamp)[:10]
        out[key] = None if val is None else float(val)
    return out


def series_for_proxy(discharge: dict, proxy_city: str) -> Dict[str, Optional[float]]:
    payload = (discharge.get("cities") or {}).get(proxy_city) or {}
    return index_daily_q(payload.get("time") or [], payload.get("river_discharge_m3s") or [])


def _end_of_q_day(q_date: str) -> datetime:
    day = datetime.fromisoformat(q_date).replace(tzinfo=timezone.utc)
    return day + timedelta(days=1)


def reindex_glofas_q_at_t0(
    t0: str,
    city_id: str,
    *,
    discharge: Optional[dict] = None,
    series: Optional[Dict[str, Optional[float]]] = None,
) -> dict:
    """Latest daily Q whose calendar day is complete at or before Target-B t0."""
    proxy = q_proxy_city(city_id)
    if series is None:
        if discharge is None:
            discharge, _, _ = load_raw()
        series = series_for_proxy(discharge, proxy)
    target_day = last_complete_q_day(t0)
    q_date = None
    q_value = None
    walkback_days = 0
    day = datetime.fromisoformat(target_day).date()
    for back in range(0, MAX_WALKBACK_DAYS + 1):
        key = (day - timedelta(days=back)).isoformat()
        val = series.get(key)
        if val is not None:
            q_date = key
            q_value = float(val)
            walkback_days = back
            break
    if q_date is None:
        return {
            "pair_city_id": city_id,
            "proxy_city": proxy,
            "t0": t0,
            "glofas_q_date": None,
            "glofas_state_time": None,
            "lag_hours": None,
            "q_m3s": None,
            "q_lookback": [None] * Q_LOOKBACK_DAYS,
            "source": SOURCE_ID,
            "status": UNAVAILABLE,
            "kind": "modelled",
            "staleness": "MISSING",
            "walkback_days": None,
            "state_time_ok": False,
            "note": "No daily Q at or before last complete day before t0.",
        }
    state_time = _iso(_end_of_q_day(q_date))
    lag_hours = hours_between(t0, state_time)
    ok = state_timestamp_at_or_before_t0(state_time, t0)
    lookback: List[Optional[float]] = []
    t0p = parse_ts(t0)
    for d in range(Q_LOOKBACK_DAYS, 0, -1):
        key = (t0p - timedelta(days=d)).strftime("%Y-%m-%d")
        val = series.get(key)
        lookback.append(None if val is None else float(val))
    if not ok:
        status = UNAVAILABLE
        note = "Rejected: glofas_state_time > t0."
    else:
        status = MODELLED_STATE
        note = "GloFAS reanalysis Q reindexed to last complete day before Target-B t0. Not a forecast."
    return {
        "pair_city_id": city_id,
        "proxy_city": proxy,
        "t0": t0,
        "glofas_q_date": q_date,
        "glofas_state_time": state_time,
        "lag_hours": lag_hours,
        "q_m3s": q_value,
        "q_lookback": lookback,
        "q_lookback_days": Q_LOOKBACK_DAYS,
        "target_complete_day": target_day,
        "walkback_days": walkback_days,
        "source": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "processing_version": PROCESSING_VERSION,
        "units": UNITS,
        "resolution": RESOLUTION,
        "status": status,
        "kind": "modelled",
        "staleness": classify_staleness(lag_hours) if ok else "MISSING",
        "state_time_ok": ok,
        "note": note,
    }


def hydro_feature_provenance(row: dict, retrieval_time: str) -> dict:
    return {
        "source": row.get("source"),
        "source_version": row.get("source_version") or SOURCE_VERSION,
        "issue_time": None,
        "valid_time": row.get("glofas_state_time"),
        "retrieval_time": retrieval_time,
        "status": row.get("status"),
        "units": row.get("units") or UNITS,
        "resolution": row.get("resolution") or RESOLUTION,
        "processing_version": row.get("processing_version") or PROCESSING_VERSION,
    }
