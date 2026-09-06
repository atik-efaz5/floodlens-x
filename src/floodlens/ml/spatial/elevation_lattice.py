"""Real elevation lattice (Open-Meteo / SRTM family) and slope. Not synthetic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from floodlens.ml.spatial.aois_v2 import AOI_BOUNDS, aoi_bounds
from floodlens.ml.spatial.schema import SPATIAL_DIR

ELEV_N = 17
CACHE = SPATIAL_DIR / "elevation_lattice.json"
UA = "floodlens-x-phase6/0.1"
ELEV_API = "https://api.open-meteo.com/v1/elevation"


def _http_json(url: str, timeout: int = 60) -> Optional[dict]:
    from urllib.error import URLError
    from urllib.request import Request, urlopen
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


def fetch_elevation(aoi_ids=None, cache_path: Optional[Path] = None) -> dict:
    cache_path = Path(cache_path or CACHE)
    aoi_ids = list(aoi_ids or AOI_BOUNDS.keys())
    payload = {
        "source": "open-meteo-elevation",
        "dem_family": "SRTM / Copernicus GLO via Open-Meteo",
        "kind": "OBSERVED",
        "synthetic": False,
        "lattice_n": ELEV_N,
        "aois": {},
        "note": "Real elevation samples. Not a fake terrain field.",
    }
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("aois"):
            missing = [a for a in aoi_ids if a not in (cached.get("aois") or {})]
            if not missing:
                return cached
            payload = cached
            payload.setdefault("aois", {})
    for aoi_id in aoi_ids:
        if aoi_id in (payload.get("aois") or {}):
            continue
        west, south, east, north = aoi_bounds(aoi_id)
        lats = np.linspace(south, north, ELEV_N)
        lons = np.linspace(west, east, ELEV_N)
        rows = []
        ok = True
        for lat in lats:
            lat_q = ",".join(f"{lat:.5f}" for _ in lons)
            lon_q = ",".join(f"{lon:.5f}" for lon in lons)
            url = f"{ELEV_API}?latitude={lat_q}&longitude={lon_q}"
            body = _http_json(url) or {}
            elev = body.get("elevation")
            if not elev or len(elev) != ELEV_N:
                ok = False
                break
            rows.append([float(v) if v is not None else float("nan") for v in elev])
        if not ok or len(rows) != ELEV_N:
            print(f"  elevation miss {aoi_id}", flush=True)
            continue
        grid = np.asarray(rows, dtype=np.float64)
        if not np.any(np.isfinite(grid)):
            print(f"  elevation miss {aoi_id} (all nan)", flush=True)
            continue
        payload["aois"][aoi_id] = {
            "bounds": [west, south, east, north],
            "n": ELEV_N,
            "crs": "EPSG:4326",
            "elevation": grid.tolist(),
        }
        print(f"  elevation {aoi_id} shape={grid.shape}", flush=True)
    if payload["aois"]:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        payload["kind"] = "UNAVAILABLE"
    return payload


def _resize(arr: np.ndarray, ny: int, nx: int) -> np.ndarray:
    ys = np.linspace(0, arr.shape[0] - 1, ny)
    xs = np.linspace(0, arr.shape[1] - 1, nx)
    out = np.zeros((ny, nx), dtype=np.float64)
    for i, y in enumerate(ys):
        y0 = int(np.floor(y))
        y1 = min(y0 + 1, arr.shape[0] - 1)
        ty = y - y0
        for j, x in enumerate(xs):
            x0 = int(np.floor(x))
            x1 = min(x0 + 1, arr.shape[1] - 1)
            tx = x - x0
            out[i, j] = (
                (1 - ty) * (1 - tx) * arr[y0, x0]
                + (1 - ty) * tx * arr[y0, x1]
                + ty * (1 - tx) * arr[y1, x0]
                + ty * tx * arr[y1, x1]
            )
    return out


def dem_and_slope(aoi_id: str, ny: int, nx: int, cache: Optional[dict] = None) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    cache = cache or (json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None)
    if not cache:
        return None, None
    pack = (cache.get("aois") or {}).get(aoi_id)
    if not pack:
        return None, None
    coarse = np.asarray(pack["elevation"], dtype=np.float64)
    elev = _resize(coarse, ny, nx)
    gy, gx = np.gradient(elev)
    slope = np.sqrt(gx * gx + gy * gy)
    return elev, slope
