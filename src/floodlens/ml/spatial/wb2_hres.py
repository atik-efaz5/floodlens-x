"""WeatherBench 2 operational IFS HRES precipitation (2016–2022).

Public GCS/HTTPS zarr. True initialization times (00/12 UTC). 10-day lead.
Native grid ~1.5°. Point-sampled at GloFAS proxy cells. Not TIGGE.
Does not treat ERA5 as a forecast. Does not fill missing leads.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.leakage import parse_ts
from floodlens.ml.sources import glofas_cells, http_get_bytes
from floodlens.ml.spatial.aois_v2 import q_proxy_city
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_VINTAGE,
    IFS_ISSUE_LATENCY_HOURS,
    TIGGE_ECMWF_CYCLES_UTC,
    last_available_nwp_run,
)
from floodlens.ml.spatial.vintage_steps import coverage_from_accumulation_windows

WB2_BASE = (
    "https://storage.googleapis.com/weatherbench2/datasets/hres/"
    "2016-2022-0012-240x121_equiangular_with_poles_conservative.zarr"
)
WB2_START = "2016-01-01T00:00:00Z"
WB2_END = "2022-12-31T12:00:00Z"
WB2_VAR = "total_precipitation_6hr"
WB2_STEP_HOURS = 6.0
WB2_MAX_LEAD_HOURS = 240.0
WB2_SOURCE_RESOLUTION = "1.5° (240×121 equiangular with poles)"
WB2_TARGET_RESOLUTION = "nearest GloFAS proxy point; GFM working grid 64×64 is not the NWP grid"
WB2_REGRID = "nearest-neighbor point sample at proxy lat/lon; no 20 m downscale"
PROCESSING_VERSION = "phase6.9b-wb2-hres-v1"
TIME_UNITS_ORIGIN = datetime(2016, 1, 1, tzinfo=timezone.utc)


def _iso(stamp: datetime) -> str:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def numcodecs_available() -> bool:
    try:
        from numcodecs import get_codec  # noqa: F401

        return True
    except ImportError:
        return False


def _codec(config: dict):
    from numcodecs import get_codec

    return get_codec(config)


def _get_json(path: str) -> Optional[dict]:
    raw = http_get_bytes(f"{WB2_BASE}/{path}", timeout=60)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _decode_array(name: str) -> Tuple[np.ndarray, dict]:
    meta = _get_json(f"{name}/.zarray")
    if not meta:
        raise RuntimeError(f"WB2 metadata missing: {name}")
    blob = http_get_bytes(f"{WB2_BASE}/{name}/0", timeout=60)
    if blob is None:
        raise RuntimeError(f"WB2 array missing: {name}")
    raw = _codec(meta["compressor"]).decode(blob)
    return np.frombuffer(raw, dtype=meta["dtype"]).copy(), meta


def load_coords(cache_dir: Path) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "wb2_coords.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    time_h, _ = _decode_array("time")
    leads_h, _ = _decode_array("prediction_timedelta")
    lat, _ = _decode_array("latitude")
    lon, _ = _decode_array("longitude")
    inits = [
        _iso(TIME_UNITS_ORIGIN + timedelta(hours=float(h)))
        for h in time_h.tolist()
    ]
    payload = {
        "inits": inits,
        "leads_hours": [float(x) for x in leads_h.tolist()],
        "latitude": [float(x) for x in lat.tolist()],
        "longitude": [float(x) for x in lon.tolist()],
        "source_resolution": WB2_SOURCE_RESOLUTION,
        "dataset": WB2_BASE,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def proxy_latlon(proxy_city: str) -> Tuple[float, float]:
    for cell in glofas_cells().get("cells") or []:
        if cell.get("city_id") == proxy_city:
            return float(cell["lat"]), float(cell["lon"])
    raise KeyError(proxy_city)


def nearest_index(coords: Sequence[float], value: float) -> int:
    arr = np.asarray(coords, dtype=float)
    return int(np.argmin(np.abs(arr - float(value))))


def wb2_eligible(t0: str) -> dict:
    run = last_available_nwp_run(t0, cycles=TIGGE_ECMWF_CYCLES_UTC, latency_hours=IFS_ISSUE_LATENCY_HOURS)
    if run is None:
        return {"eligible": False, "run": None, "reason": "no 00/12 cycle with 6 h issue latency"}
    if run < parse_ts(WB2_START) or run > parse_ts(WB2_END):
        return {
            "eligible": False,
            "run": _iso(run),
            "reason": "initialization outside WeatherBench2 HRES 2016-01-01…2022-12-31",
        }
    return {"eligible": True, "run": _iso(run), "reason": None}


def init_index(coords: dict, issue: str) -> Optional[int]:
    try:
        return coords["inits"].index(issue if issue.endswith("Z") else issue)
    except ValueError:
        # 2018-06-06T00:00:00Z vs stored
        want = parse_ts(issue)
        for i, stamp in enumerate(coords["inits"]):
            if parse_ts(stamp) == want:
                return i
        return None


def _init_cache_path(cache_dir: Path, issue: str) -> Path:
    run = parse_ts(issue)
    return Path(cache_dir) / f"wb2_hres_{run.strftime('%Y%m%dT%H%M')}.json"


def acquire_init_points(
    issue: str,
    cache_dir: Path,
    *,
    fetch: bool = True,
    coords: Optional[dict] = None,
) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _init_cache_path(cache_dir, issue)
    sidecar = path.with_suffix(".sha256")
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if payload and payload.get("status") == "OK" and payload.get("points"):
            digest = _sha256_bytes(path.read_bytes())
            if not sidecar.exists() or sidecar.read_text(encoding="utf-8").strip() == digest:
                return {"status": "CACHED", "path": str(path), "checksum": digest, "issue_time": issue}
    if not fetch:
        return {"status": "UNAVAILABLE", "path": str(path), "reason": "WB2 fetch disabled", "issue_time": issue}
    if not numcodecs_available():
        return {
            "status": "UNAVAILABLE",
            "reason": "numcodecs not installed; cannot decode WeatherBench2 blosc chunks",
            "issue_time": issue,
        }
    coords = coords or load_coords(cache_dir)
    idx = init_index(coords, issue)
    if idx is None:
        return {"status": "UNAVAILABLE", "reason": f"init {issue} not in WB2 time axis", "issue_time": issue}
    meta = _get_json(f"{WB2_VAR}/.zarray")
    if not meta:
        return {"status": "UNAVAILABLE", "reason": "WB2 precip metadata missing", "issue_time": issue}
    chunks = meta["chunks"]
    lead_chunk = int(chunks[1])
    n_leads = len(coords["leads_hours"])
    n_lon = len(coords["longitude"])
    n_lat = len(coords["latitude"])
    lead_blocks = []
    for c0 in range(0, n_leads, lead_chunk):
        key = f"{idx}.{c0 // lead_chunk}.0.0"
        blob = http_get_bytes(f"{WB2_BASE}/{WB2_VAR}/{key}", timeout=90)
        if blob is None:
            return {"status": "UNAVAILABLE", "reason": f"chunk {key} missing", "issue_time": issue}
        raw = _codec(meta["compressor"]).decode(blob)
        n_this = min(lead_chunk, n_leads - c0)
        arr = np.frombuffer(raw, dtype=meta["dtype"]).reshape(1, lead_chunk, n_lon, n_lat)
        lead_blocks.append(arr[0, :n_this])
    cube = np.concatenate(lead_blocks, axis=0)  # lead, lon, lat
    points = {}
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for cell in glofas_cells().get("cells") or []:
        city = cell["city_id"]
        lat, lon = float(cell["lat"]), float(cell["lon"])
        ilat = nearest_index(coords["latitude"], lat)
        ilon = nearest_index(coords["longitude"], lon)
        series = []
        for lead_i, lead_h in enumerate(coords["leads_hours"]):
            val = cube[lead_i, ilon, ilat]
            if val is None or not np.isfinite(val):
                mm = None
            else:
                mm = float(val) * 1000.0  # WB2 precipitation is meters
            valid = parse_ts(issue) + timedelta(hours=float(lead_h))
            series.append(
                {
                    "lead_hours": float(lead_h),
                    "valid_time": _iso(valid),
                    "precipitation_mm": mm,
                }
            )
        points[city] = {
            "request_lat": lat,
            "request_lon": lon,
            "grid_lat": coords["latitude"][ilat],
            "grid_lon": coords["longitude"][ilon],
            "series": series,
        }
    record = {
        "status": "OK",
        "provider": "WeatherBench 2 / ECMWF",
        "model": "IFS HRES operational (WB2 2016-2022 00/12)",
        "cycle": parse_ts(issue).strftime("%HUTC"),
        "issue_time": issue,
        "variable": WB2_VAR,
        "units": "mm",
        "native_resolution": WB2_SOURCE_RESOLUTION,
        "temporal_resolution": "6-hourly accumulation",
        "source_resolution": WB2_SOURCE_RESOLUTION,
        "target_resolution": WB2_TARGET_RESOLUTION,
        "regridding_method": WB2_REGRID,
        "license": "WB2 public GCS; ECMWF IFS HRES attribution",
        "attribution": "Rasp et al. WeatherBench 2; ECMWF IFS HRES",
        "source_version": "weatherbench2-hres-2016-2022-0012-240x121",
        "processing_version": PROCESSING_VERSION,
        "retrieved_at": retrieved,
        "source_url": WB2_BASE,
        "kind": "forecast",
        "vintage": FORECAST_VINTAGE,
        "points": points,
    }
    blob = json.dumps(record, separators=(",", ":")).encode("utf-8")
    path.write_bytes(blob)
    sidecar.write_text(_sha256_bytes(blob) + "\n", encoding="utf-8")
    return {
        "status": "DOWNLOADED",
        "path": str(path),
        "checksum": _sha256_bytes(blob),
        "issue_time": issue,
        "n_leads": n_leads,
        "bytes": len(blob),
    }


def acquire_wb2_for_pairs(
    pairs: Sequence[dict],
    cache_dir: Path,
    *,
    fetch: bool = True,
) -> dict:
    coords = None
    jobs = []
    seen = set()
    for pair in pairs:
        elig = wb2_eligible(pair["t0"])
        if not elig["eligible"]:
            continue
        issue = elig["run"]
        if issue in seen:
            continue
        seen.add(issue)
        jobs.append(issue)
    results = []
    if fetch and jobs and numcodecs_available():
        coords = load_coords(cache_dir)
    for i, issue in enumerate(jobs):
        if fetch:
            print(f"WB2 {i+1}/{len(jobs)} {issue}", flush=True)
        results.append(acquire_init_points(issue, cache_dir, fetch=fetch, coords=coords))
    ok = [r for r in results if r.get("status") in {"CACHED", "DOWNLOADED"}]
    return {
        "n_requested": len(jobs),
        "n_ok": len(ok),
        "n_failed": len(results) - len(ok),
        "results": results,
        "cache_dir": str(cache_dir),
        "fetch": fetch,
        "numcodecs": numcodecs_available(),
        "unique_initialisations": jobs,
    }


def load_init_points(cache_dir: Path, issue: str) -> Optional[dict]:
    path = _init_cache_path(cache_dir, issue)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("status") != "OK":
        return None
    return payload


def pair_wb2_coverage(pair: dict, cache_dir: Optional[Path]) -> dict:
    t0, t1 = pair["t0"], pair["t1"]
    elig = wb2_eligible(t0)
    base = {
        "forecast_source": None,
        "forecast_status": "UNAVAILABLE",
        "forecast_coverage_fraction": 0.0,
        "forecast_issue_ok": True,
        "forecast_filled": False,
        "reason": elig.get("reason") or "WB2 not eligible",
        "source_resolution": WB2_SOURCE_RESOLUTION,
        "target_resolution": WB2_TARGET_RESOLUTION,
        "regridding_method": WB2_REGRID,
        "temporal_resolution": "6-hourly",
        "documented_max_lead_hours": WB2_MAX_LEAD_HOURS,
    }
    if not elig["eligible"] or cache_dir is None:
        return {**base, "forecast_issue_time": elig.get("run")}
    payload = load_init_points(cache_dir, elig["run"])
    if payload is None:
        return {**base, "forecast_issue_time": elig["run"], "reason": "WB2 init not cached"}
    proxy = q_proxy_city(pair.get("city_id") or "")
    point = (payload.get("points") or {}).get(proxy)
    if not point:
        return {**base, "forecast_issue_time": payload.get("issue_time"), "reason": f"no point for {proxy}"}
    windows = []
    for row in point.get("series") or []:
        lead = float(row.get("lead_hours") or 0)
        if lead <= 0:
            continue
        windows.append((row["valid_time"], WB2_STEP_HOURS, row.get("precipitation_mm")))
    cov = coverage_from_accumulation_windows(
        issue_time=payload["issue_time"],
        t0=t0,
        t1=t1,
        windows=windows,
        filled=False,
    )
    cov.update(
        {
            "forecast_source": "weatherbench2-hres-ifs",
            "forecast_issue_time": payload["issue_time"],
            "forecast_model": payload.get("model"),
            "forecast_cycle": payload.get("cycle"),
            "forecast_variable": WB2_VAR,
            "forecast_units": "mm",
            "source_resolution": payload.get("source_resolution") or WB2_SOURCE_RESOLUTION,
            "target_resolution": WB2_TARGET_RESOLUTION,
            "regridding_method": WB2_REGRID,
            "temporal_resolution": payload.get("temporal_resolution"),
            "source_url": payload.get("source_url"),
            "retrieved_at": payload.get("retrieved_at"),
            "processing_version": payload.get("processing_version") or PROCESSING_VERSION,
            "license": payload.get("license"),
            "attribution": payload.get("attribution"),
            "source_version": payload.get("source_version"),
            "proxy_city": proxy,
            "grid_lat": point.get("grid_lat"),
            "grid_lon": point.get("grid_lon"),
            "documented_max_lead_hours": WB2_MAX_LEAD_HOURS,
        }
    )
    return cov
