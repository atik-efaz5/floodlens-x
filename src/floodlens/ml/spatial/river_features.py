"""Distance-to-river from HydroRIVERS (if local) or OSM waterways (real geometries)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from floodlens.ml.spatial.aois_v2 import AOI_BOUNDS, aoi_bounds
from floodlens.ml.spatial.schema import SPATIAL_DIR

CACHE = SPATIAL_DIR / "rivers_osm.json"
HYDRORIVERS_CACHE = SPATIAL_DIR / "hydrorivers.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "floodlens-x-phase6/0.1"
# Degrees: ~2 km at Bangladesh latitudes. Binary river mask at working resolution.
RIVER_MASK_DEG = 0.02


def _http_json(url: str, body: Optional[bytes] = None, timeout: int = 90) -> Optional[dict]:
    from urllib.error import URLError
    from urllib.request import Request, urlopen
    import subprocess

    headers = {"User-Agent": UA}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        cmd = ["curl", "-sS", "-A", UA, "--max-time", str(timeout)]
        if body is not None:
            cmd.extend(["-d", body.decode()])
        cmd.append(url)
        try:
            raw = subprocess.check_output(cmd)
            return json.loads(raw.decode())
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
            return None


def _vertices_from_geojson(path: Path) -> List[List[float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    coords: List[List[float]] = []
    features = data.get("features") if isinstance(data, dict) else None
    if features is None and isinstance(data, dict) and "aois" in data:
        return []
    for feat in features or []:
        geom = (feat or {}).get("geometry") or {}
        kind = geom.get("type")
        if kind == "LineString":
            lines = [geom.get("coordinates") or []]
        elif kind == "MultiLineString":
            lines = geom.get("coordinates") or []
        else:
            continue
        for line in lines:
            for pt in line:
                if len(pt) < 2:
                    continue
                lon, lat = float(pt[0]), float(pt[1])
                coords.append([lat, lon])
    return coords


def _clip_vertices(verts: List[List[float]], bounds: Tuple[float, float, float, float]) -> List[List[float]]:
    west, south, east, north = bounds
    pad = 0.05
    return [
        v
        for v in verts
        if (south - pad) <= v[0] <= (north + pad) and (west - pad) <= v[1] <= (east + pad)
    ]


def load_hydrorivers(aoi_ids=None, path: Optional[Path] = None) -> Optional[dict]:
    """Use a local HydroRIVERS GeoJSON/JSON clip if the operator provided one."""
    env = os.environ.get("FLOODLENS_HYDRORIVERS_PATH")
    candidate = Path(path or env or HYDRORIVERS_CACHE)
    if not candidate.exists():
        return None
    aoi_ids = list(aoi_ids or AOI_BOUNDS.keys())
    if candidate.suffix.lower() in {".geojson", ".json"}:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("aois"):
            return {
                "source": raw.get("source") or "hydrorivers",
                "license": raw.get("license") or "HydroRIVERS (free scientific/commercial use)",
                "kind": "OBSERVED",
                "aois": raw["aois"],
                "note": "Local HydroRIVERS clip. Not a fake river network.",
            }
        verts = _vertices_from_geojson(candidate)
        payload = {
            "source": "hydrorivers",
            "license": "HydroRIVERS v1 (free for scientific/commercial use)",
            "kind": "OBSERVED",
            "aois": {},
            "note": "Local HydroRIVERS geometry clip. Not a fake river network.",
        }
        for aoi_id in aoi_ids:
            clipped = _clip_vertices(verts, aoi_bounds(aoi_id))
            payload["aois"][aoi_id] = {"n_vertices": len(clipped), "vertices": clipped[:8000]}
        return payload
    return None


def fetch_rivers(aoi_ids=None, cache_path: Optional[Path] = None) -> dict:
    hydro = load_hydrorivers(aoi_ids=aoi_ids)
    if hydro is not None:
        return hydro
    cache_path = Path(cache_path or CACHE)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    aoi_ids = list(aoi_ids or AOI_BOUNDS.keys())
    payload = {
        "source": "openstreetmap-overpass",
        "license": "ODbL",
        "kind": "OBSERVED",
        "aois": {},
        "note": "OSM waterways clipped to AOIs. Not a fake river network. HydroRIVERS file may replace this cache.",
    }
    for aoi_id in aoi_ids:
        west, south, east, north = aoi_bounds(aoi_id)
        query = (
            f"[out:json][timeout:25];"
            f'(way["waterway"~"river|stream|canal"]({south},{west},{north},{east}););'
            f"out geom;"
        )
        body = _http_json(OVERPASS, f"data={query}".encode())
        coords: List[List[float]] = []
        for el in (body or {}).get("elements") or []:
            for pt in el.get("geometry") or []:
                if "lat" in pt and "lon" in pt:
                    coords.append([float(pt["lat"]), float(pt["lon"])])
        payload["aois"][aoi_id] = {"n_vertices": len(coords), "vertices": coords[:8000]}
        print(f"  rivers {aoi_id} vertices={len(coords)}", flush=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def river_distance_map(aoi_id: str, ny: int, nx: int, cache: Optional[dict] = None) -> Optional[np.ndarray]:
    if cache is None:
        cache = load_hydrorivers(aoi_ids=[aoi_id])
        if cache is None and CACHE.exists():
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        if cache is None and HYDRORIVERS_CACHE.exists():
            cache = json.loads(HYDRORIVERS_CACHE.read_text(encoding="utf-8"))
    if not cache:
        return None
    pack = (cache.get("aois") or {}).get(aoi_id)
    verts = np.asarray((pack or {}).get("vertices") or [], dtype=np.float64)
    if verts.size == 0:
        return None
    west, south, east, north = aoi_bounds(aoi_id)
    lats = np.linspace(north, south, ny)
    lons = np.linspace(west, east, nx)
    # subsample vertices for O(n) distance
    if verts.shape[0] > 400:
        idx = np.linspace(0, verts.shape[0] - 1, 400).astype(int)
        verts = verts[idx]
    out = np.zeros((ny, nx), dtype=np.float64)
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            d2 = (verts[:, 0] - lat) ** 2 + (verts[:, 1] - lon) ** 2
            out[i, j] = float(np.sqrt(np.min(d2)))
    return out


def river_mask_map(distance: Optional[np.ndarray], threshold_deg: float = RIVER_MASK_DEG) -> Optional[np.ndarray]:
    if distance is None:
        return None
    return (np.asarray(distance, dtype=np.float64) <= threshold_deg).astype(np.float64)
