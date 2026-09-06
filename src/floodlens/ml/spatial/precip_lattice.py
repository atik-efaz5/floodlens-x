"""Spatial rainfall lattice from Open-Meteo archive (ERA5-Land family). Not fabricated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from floodlens.ml.spatial.aois_v2 import AOI_BOUNDS, aoi_bounds
from floodlens.ml.spatial.schema import SPATIAL_DIR

LATTICE_N = 3
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
CACHE = SPATIAL_DIR / "precip_lattice.json"
START = "2016-06-01"
END = "2024-08-31"
UA = "floodlens-x-phase6/0.1"


def lattice_points(aoi_id: str, n: int = LATTICE_N) -> List[Tuple[float, float]]:
    west, south, east, north = aoi_bounds(aoi_id)
    lats = np.linspace(south, north, n)
    lons = np.linspace(west, east, n)
    return [(float(lat), float(lon)) for lat in lats for lon in lons]


def _http_json(url: str, timeout: int = 90) -> Optional[dict]:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    import subprocess

    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        try:
            raw = subprocess.check_output(["curl", "-sS", "-A", UA, "--max-time", str(timeout), url])
            return json.loads(raw.decode())
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
            return None


def fetch_lattice(aoi_ids: Optional[List[str]] = None, cache_path: Optional[Path] = None) -> dict:
    """Download hourly precip at lattice points. Cached; not a dense radar cube."""
    cache_path = Path(cache_path or CACHE)
    aoi_ids = list(aoi_ids or AOI_BOUNDS.keys())
    payload: dict = {
        "source": "open-meteo-archive",
        "model_family": "ERA5-Land / Open-Meteo best match",
        "license": "CC BY 4.0",
        "kind": "REANALYSIS",
        "start": START,
        "end": END,
        "lattice_n": LATTICE_N,
        "aois": {},
        "note": "Point lattice sampling of a real reanalysis field. Not fabricated rain.",
    }
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("aois"):
            payload.update(cached)
            payload.setdefault("aois", {})
            if all(aid in payload["aois"] and (payload["aois"][aid].get("n_points") or 0) >= 4 for aid in aoi_ids):
                return payload
    for aoi_id in aoi_ids:
        if (payload.get("aois") or {}).get(aoi_id, {}).get("n_points", 0) >= 4:
            continue
        pts = lattice_points(aoi_id)
        rows = []
        for lat, lon in pts:
            url = (
                f"{ARCHIVE}?latitude={lat:.4f}&longitude={lon:.4f}"
                f"&start_date={START}&end_date={END}&hourly=precipitation&timezone=UTC"
            )
            body = _http_json(url)
            hourly = (body or {}).get("hourly") or {}
            rows.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "time": hourly.get("time") or [],
                    "precipitation_mm": hourly.get("precipitation") or [],
                }
            )
            print(f"  precip lattice {aoi_id} {lat:.3f},{lon:.3f} n={len(rows[-1]['time'])}", flush=True)
        payload.setdefault("aois", {})[aoi_id] = {"points": rows, "n_points": len(rows)}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
    if not payload.get("aois"):
        payload["kind"] = "UNAVAILABLE"
    return payload


def _idw(values: np.ndarray, lats: np.ndarray, lons: np.ndarray, grid_lats: np.ndarray, grid_lons: np.ndarray) -> np.ndarray:
    out = np.zeros((grid_lats.size, grid_lons.size), dtype=np.float64)
    for i, lat in enumerate(grid_lats):
        for j, lon in enumerate(grid_lons):
            d2 = (lats - lat) ** 2 + (lons - lon) ** 2
            d2 = np.maximum(d2, 1e-12)
            w = 1.0 / d2
            finite = np.isfinite(values)
            if not np.any(finite):
                out[i, j] = 0.0
                continue
            out[i, j] = float(np.sum(w[finite] * values[finite]) / np.sum(w[finite]))
    return out


def precip_maps_at_issue(
    aoi_id: str,
    issue_iso: str,
    ny: int,
    nx: int,
    lattice: Optional[dict] = None,
) -> Optional[dict]:
    """24 h and 72 h accumulations on the working grid. None if lattice missing."""
    lattice = lattice or (json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None)
    if not lattice:
        return None
    pack = (lattice.get("aois") or {}).get(aoi_id)
    if not pack:
        return None
    points = pack.get("points") or []
    if len(points) < 4:
        return None
    issue = issue_iso.replace("Z", "")[:19]
    if len(issue) == 16:
        issue = issue + ":00"
    from datetime import datetime, timedelta, timezone

    def _hour_key(value) -> str:
        stamp = str(value).replace("Z", "")
        if len(stamp) >= 16:
            return stamp[:16] + ":00"
        return stamp

    t0 = datetime.fromisoformat(issue).replace(tzinfo=timezone.utc)
    t0 = t0.replace(minute=0, second=0, microsecond=0)
    west, south, east, north = aoi_bounds(aoi_id)
    grid_lats = np.linspace(north, south, ny)
    grid_lons = np.linspace(west, east, nx)
    lats = np.asarray([p["lat"] for p in points], dtype=np.float64)
    lons = np.asarray([p["lon"] for p in points], dtype=np.float64)

    def accum(hours: int) -> np.ndarray:
        vals = []
        for p in points:
            index = {_hour_key(t): v for t, v in zip(p.get("time") or [], p.get("precipitation_mm") or [])}
            acc = 0.0
            n = 0
            for h in range(1, hours + 1):
                stamp = _hour_key((t0 - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S"))
                v = index.get(stamp)
                if v is None:
                    continue
                acc += float(v)
                n += 1
            vals.append(acc if n / hours >= 0.5 else np.nan)
        return _idw(np.asarray(vals, dtype=np.float64), lats, lons, grid_lats, grid_lons)

    m24 = accum(24)
    m72 = accum(72)
    if not np.any(np.isfinite(m24)):
        return None
    cube_rows = []
    intensity = []
    for p in points:
        index = {_hour_key(t): v for t, v in zip(p.get("time") or [], p.get("precipitation_mm") or [])}
        series = []
        for h in range(1, 73):
            stamp = _hour_key((t0 - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S"))
            v = index.get(stamp)
            series.append(float(v) if v is not None else np.nan)
        cube_rows.append(series)
        window24 = np.asarray(series[:24], dtype=np.float64)
        intensity.append(float(np.nanmax(window24)) if np.any(np.isfinite(window24)) else np.nan)
    cube = np.asarray(cube_rows, dtype=np.float64)
    mint = _idw(np.asarray(intensity, dtype=np.float64), lats, lons, grid_lats, grid_lons)
    completeness = float(np.mean(np.isfinite(cube)))
    t0_iso = t0.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    start_iso = (t0 - timedelta(hours=72)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "precip_24h_map": m24,
        "precip_72h_map": m72,
        "precip_intensity_24h_map": mint,
        "precip_cube_lattice": cube,
        "n_lattice_points": len(points),
        "precip_is_aoi_point": False,
        "x_antecedent_24h": float(np.nanmean(m24)),
        "x_antecedent_72h": float(np.nanmean(m72)),
        "t0": t0_iso,
        "input_start": start_iso,
        "input_end": t0_iso,
        "rainfall_source": lattice.get("source") or "open-meteo-archive",
        "rainfall_status": lattice.get("kind") or "REANALYSIS",
        "cube_completeness": completeness,
        "spatial_resolution": "ERA5-Land ~11 km lattice, IDW to working grid",
        "temporal_resolution": "hourly lookback 72 h",
        "units": "mm",
    }
