"""Smallest Target-B forecast-vintage acquisition.

Open-Meteo Single Runs (IFS HRES, 2024-03-14+) is the only no-credential vintage
product that can be fetched as point timeseries. TIGGE is planned, not auto-downloaded.
Does not fabricate missing leads. Does not treat ERA5 as a forecast.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlencode

from floodlens.ml.leakage import hours_between, parse_ts
from floodlens.ml.sources import glofas_cells, http_get_json
from floodlens.ml.spatial.aois_v2 import q_proxy_city
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_VINTAGE,
    IFS_HRES_ARCHIVE_START,
    IFS_HRES_DOCUMENTED_LEAD_HOURS,
    IFS_ISSUE_LATENCY_HOURS,
    TIGGE_ECMWF_CYCLES_UTC,
    UNAVAILABLE,
    issue_at_or_before_t0,
    last_available_nwp_run,
    valid_time_in_target_interval,
)
from floodlens.ml.spatial.phase68a import hour_key, hours_in_open_closed

SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
SINGLE_RUNS_MODEL = "ecmwf_ifs"
SINGLE_RUNS_FORECAST_DAYS = 16
# 06/18 UTC cycles returned empty from this archive; 00/12 are reproducible.
SINGLE_RUNS_CYCLES = TIGGE_ECMWF_CYCLES_UTC
PROCESSING_VERSION = "phase6.9a-forecast-vintage-v1"
TIGGE_MAX_LEAD_HOURS = 360.0
BANGLADESH_AREA = "27/88/20.5/93"  # N/W/S/E


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def proxy_latlon(proxy_city: str) -> tuple:
    for cell in glofas_cells().get("cells") or []:
        if cell.get("city_id") == proxy_city:
            return float(cell["lat"]), float(cell["lon"])
    raise KeyError(proxy_city)


def run_param(stamp: datetime) -> str:
    return stamp.strftime("%Y-%m-%dT%H:%M")


def cache_name(proxy_city: str, run: datetime) -> str:
    return f"ifs_hres_{proxy_city}_{run.strftime('%Y%m%dT%H%M')}.json"


def cds_credentials_present() -> bool:
    return bool(os.environ.get("CDSAPI_KEY") or Path.home().joinpath(".cdsapirc").exists())


def tigge_plan(pairs: Sequence[dict]) -> dict:
    """Smallest TIGGE extract that could cover Target B. Not executed by default."""
    inits = []
    for pair in pairs:
        t0 = pair["t0"]
        run = last_available_nwp_run(t0, cycles=TIGGE_ECMWF_CYCLES_UTC)
        if run is None:
            continue
        inits.append(_iso(run))
    unique_inits = sorted(set(inits))
    n_unique_t0 = len({str(p.get("t0"))[:10] for p in pairs})
    # 0.5° over Bangladesh ~14×10 cells, 6-hourly to 15 d, control forecast only.
    n_points = 14 * 10
    n_steps = int(TIGGE_MAX_LEAD_HOURS / 6) + 1
    bytes_est = n_points * n_steps * max(len(unique_inits), 1) * 8
    years = sorted({int(str(p.get("t0"))[:4]) for p in pairs})
    return {
        "product": "TIGGE ECMWF total precipitation (control forecast)",
        "provider": "ECMWF / ECDS",
        "dataset": "tigge-forecasts",
        "originating_centre": "ecmwf",
        "param": "tp",
        "type": "cf",
        "grid": "0.5/0.5",
        "area": BANGLADESH_AREA,
        "step": "0/to/360/by/6",
        "cycles": "00/12 UTC",
        "latency_hours": IFS_ISSUE_LATENCY_HOURS,
        "years_needed": years,
        "n_target_b_pairs": len(pairs),
        "n_unique_t0_dates": n_unique_t0,
        "n_unique_initialisations": len(unique_inits),
        "pairs_potentially_covered_15d": sum(
            1 for p in pairs if float(p.get("delta_t_hours") or 0) <= TIGGE_MAX_LEAD_HOURS
        ),
        "estimated_storage_mb": round(bytes_est / 1e6, 3),
        "bandwidth_note": "Point/area extract is small; ECDS login is the blocker, not volume.",
        "licensing": "CC BY 4.0 (ECMWF TIGGE)",
        "access_requirements": "ECMWF Data Store account; 48 h archive delay",
        "cds_credentials_present": cds_credentials_present(),
        "acquired": False,
        "reason_not_acquired": (
            "No CDS/ECDS credentials"
            if not cds_credentials_present()
            else "Credentials present but TIGGE retrieve is not auto-executed (avoid cube downloads)."
        ),
        "initialisations": unique_inits,
        "reproducibility": "MARS/ECDS request with issue+step+valid; do not interpolate missing steps.",
    }


def single_runs_eligibility(t0: str) -> dict:
    run = last_available_nwp_run(t0, cycles=SINGLE_RUNS_CYCLES)
    archive_start = parse_ts(IFS_HRES_ARCHIVE_START)
    if run is None:
        return {"eligible": False, "run": None, "reason": "no NWP cycle with issue latency <= t0"}
    if run < archive_start:
        return {
            "eligible": False,
            "run": _iso(run),
            "reason": "before Open-Meteo IFS HRES Single Runs archive (2024-03-14)",
        }
    return {"eligible": True, "run": _iso(run), "reason": None}


def _run_url(lat: float, lon: float, run: datetime) -> str:
    query = urlencode(
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": "precipitation",
            "timezone": "UTC",
            "forecast_days": str(SINGLE_RUNS_FORECAST_DAYS),
            "models": SINGLE_RUNS_MODEL,
            "run": run_param(run),
        }
    )
    return f"{SINGLE_RUNS_URL}?{query}"


def load_cached_run(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("status") == "ERROR" or payload.get("hourly") is None:
        return None
    return payload


def acquire_single_run(
    proxy_city: str,
    run: datetime,
    cache_dir: Path,
    *,
    fetch: bool = True,
) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / cache_name(proxy_city, run)
    sidecar = path.with_suffix(".sha256")
    cached = load_cached_run(path)
    if cached is not None:
        digest = _sha256_bytes(path.read_bytes())
        if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
            cached = None
        else:
            return {
                "status": "CACHED",
                "path": str(path),
                "checksum": digest,
                "proxy_city": proxy_city,
                "run": _iso(run),
                "source_url": cached.get("source_url"),
            }
    if not fetch:
        return {
            "status": UNAVAILABLE,
            "path": str(path),
            "proxy_city": proxy_city,
            "run": _iso(run),
            "reason": "not fetched (acquire disabled)",
        }
    lat, lon = proxy_latlon(proxy_city)
    url = _run_url(lat, lon, run)
    payload = http_get_json(url, timeout=90)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not payload or not isinstance(payload, dict) or not (payload.get("hourly") or {}).get("time"):
        fail = {
            "status": "ERROR",
            "error": True,
            "reason": "Single Runs API returned no hourly precipitation",
            "source_url": url,
            "retrieved_at": retrieved,
            "proxy_city": proxy_city,
            "run": _iso(run),
        }
        path.write_text(json.dumps(fail, indent=2), encoding="utf-8")
        return {
            "status": UNAVAILABLE,
            "path": str(path),
            "proxy_city": proxy_city,
            "run": _iso(run),
            "reason": fail["reason"],
            "source_url": url,
        }
    hourly = payload.get("hourly") or {}
    record = {
        "status": "OK",
        "provider": "Open-Meteo Single Runs",
        "model": SINGLE_RUNS_MODEL,
        "product": "ECMWF IFS HRES 9 km precipitation",
        "kind": "forecast",
        "vintage": FORECAST_VINTAGE,
        "proxy_city": proxy_city,
        "latitude": lat,
        "longitude": lon,
        "issue_time": _iso(run),
        "run_param": run_param(run),
        "source_url": url,
        "retrieved_at": retrieved,
        "processing_version": PROCESSING_VERSION,
        "license": "CC BY 4.0; ECMWF open data terms for IFS",
        "hourly": {
            "time": list(hourly.get("time") or []),
            "precipitation": list(hourly.get("precipitation") or []),
        },
        "units": "mm",
        "spatial_resolution": "IFS HRES ~9 km (point sample at GloFAS proxy)",
        "temporal_resolution": "hourly (Open-Meteo interpolation of IFS steps)",
    }
    blob = json.dumps(record, separators=(",", ":")).encode("utf-8")
    path.write_bytes(blob)
    digest = _sha256_bytes(blob)
    sidecar.write_text(digest + "\n", encoding="utf-8")
    return {
        "status": "DOWNLOADED",
        "path": str(path),
        "checksum": digest,
        "proxy_city": proxy_city,
        "run": _iso(run),
        "source_url": url,
        "n_hours": len(record["hourly"]["time"]),
    }


def acquire_single_runs_for_pairs(
    pairs: Sequence[dict],
    cache_dir: Path,
    *,
    fetch: bool = True,
) -> dict:
    jobs = []
    seen = set()
    for pair in pairs:
        t0 = pair["t0"]
        elig = single_runs_eligibility(t0)
        if not elig["eligible"]:
            continue
        proxy = q_proxy_city(pair.get("city_id") or "")
        run = last_available_nwp_run(t0, cycles=SINGLE_RUNS_CYCLES)
        key = (proxy, run_param(run))
        if key in seen:
            continue
        seen.add(key)
        jobs.append((proxy, run))
    results = [acquire_single_run(proxy, run, cache_dir, fetch=fetch) for proxy, run in jobs]
    ok = [r for r in results if r.get("status") in {"CACHED", "DOWNLOADED"}]
    return {
        "n_requested": len(jobs),
        "n_ok": len(ok),
        "n_failed": len(results) - len(ok),
        "results": results,
        "cache_dir": str(cache_dir),
        "fetch": fetch,
    }


def load_run_hourly(cache_dir: Path, proxy_city: str, run: datetime) -> Optional[dict]:
    path = Path(cache_dir) / cache_name(proxy_city, run)
    payload = load_cached_run(path)
    if payload is None:
        return None
    times = (payload.get("hourly") or {}).get("time") or []
    vals = (payload.get("hourly") or {}).get("precipitation") or []
    by_hour = {}
    for stamp, val in zip(times, vals):
        by_hour[hour_key(stamp)] = None if val is None else float(val)
    return {
        "issue_time": payload.get("issue_time") or _iso(run),
        "by_hour": by_hour,
        "source_url": payload.get("source_url"),
        "retrieved_at": payload.get("retrieved_at"),
        "n_hours": len(times),
        "path": str(path),
        "processing_version": payload.get("processing_version") or PROCESSING_VERSION,
        "license": payload.get("license"),
        "spatial_resolution": payload.get("spatial_resolution"),
        "temporal_resolution": payload.get("temporal_resolution"),
        "model": payload.get("model") or SINGLE_RUNS_MODEL,
    }


def pair_forecast_coverage(
    pair: dict,
    cache_dir: Optional[Path],
    *,
    allow_fetch: bool = False,
) -> dict:
    t0 = pair["t0"]
    t1 = pair["t1"]
    elig = single_runs_eligibility(t0)
    required = hours_in_open_closed(t0, t1)
    n_req = len(required)
    base = {
        "forecast_source": None,
        "forecast_status": UNAVAILABLE,
        "forecast_coverage_fraction": 0.0,
        "forecast_lead_min": None,
        "forecast_lead_max": None,
        "forecast_n_hours_required": n_req,
        "forecast_n_hours_present": 0,
        "forecast_issue_time": None,
        "forecast_issue_ok": True,
        "forecast_valid_ok": True,
        "forecast_filled": False,
        "forecast_resolution": None,
        "reason": elig.get("reason") or "no forecast-vintage product in cube",
        "documented_max_lead_hours": IFS_HRES_DOCUMENTED_LEAD_HOURS,
    }
    if not elig["eligible"]:
        return base
    run = last_available_nwp_run(t0, cycles=SINGLE_RUNS_CYCLES)
    issue = _iso(run)
    if not issue_at_or_before_t0(issue, t0):
        base["forecast_issue_ok"] = False
        base["reason"] = "issue_time > t0"
        return base
    proxy = q_proxy_city(pair.get("city_id") or "")
    if allow_fetch and cache_dir is not None:
        acquire_single_run(proxy, run, cache_dir, fetch=True)
    hourly = load_run_hourly(cache_dir, proxy, run) if cache_dir is not None else None
    if hourly is None:
        base["reason"] = "IFS HRES Single Runs eligible but not acquired/cached"
        base["forecast_issue_time"] = issue
        return base
    if not issue_at_or_before_t0(hourly["issue_time"], t0):
        return {
            **base,
            "forecast_issue_time": hourly["issue_time"],
            "forecast_issue_ok": False,
            "reason": "cached run issue_time > t0 (rejected)",
        }
    present = 0
    leads = []
    valid_ok = True
    for stamp in required:
        key = hour_key(_iso(stamp))
        if hourly["by_hour"].get(key) is None:
            continue
        valid = _iso(stamp)
        if not valid_time_in_target_interval(valid, t0, t1):
            valid_ok = False
            continue
        present += 1
        leads.append(hours_between(valid, hourly["issue_time"]))
    frac = (present / n_req) if n_req else 0.0
    return {
        "forecast_source": "open-meteo-single-runs-ecmwf-ifs",
        "forecast_status": FORECAST_VINTAGE if present else UNAVAILABLE,
        "forecast_coverage_fraction": frac,
        "forecast_lead_min": min(leads) if leads else None,
        "forecast_lead_max": max(leads) if leads else None,
        "forecast_n_hours_required": n_req,
        "forecast_n_hours_present": present,
        "forecast_issue_time": hourly["issue_time"],
        "forecast_issue_ok": True,
        "forecast_valid_ok": valid_ok,
        "forecast_filled": False,
        "forecast_resolution": hourly.get("spatial_resolution"),
        "forecast_temporal_resolution": hourly.get("temporal_resolution"),
        "reason": None if present else "run cached but no in-horizon hours",
        "documented_max_lead_hours": IFS_HRES_DOCUMENTED_LEAD_HOURS,
        "source_url": hourly.get("source_url"),
        "retrieved_at": hourly.get("retrieved_at"),
        "processing_version": hourly.get("processing_version"),
        "license": hourly.get("license"),
        "proxy_city": proxy,
    }


def forecast_feature_provenance(cov: dict) -> dict:
    return {
        "source": cov.get("forecast_source") or "none",
        "source_version": cov.get("forecast_source") or PROCESSING_VERSION,
        "issue_time": cov.get("forecast_issue_time"),
        "valid_time": None,
        "retrieval_time": cov.get("retrieved_at"),
        "status": cov.get("forecast_status"),
        "units": "mm",
        "resolution": cov.get("forecast_resolution"),
        "processing_version": cov.get("processing_version") or PROCESSING_VERSION,
    }
