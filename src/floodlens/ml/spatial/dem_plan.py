"""DEM ingestion plan for spatial tiles. Never invents elevations.

Synthetic DEM remains pipeline-test only (``make_synthetic_sample``).
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from floodlens.ml.spatial.schema import GRID_SIZE

DEM_INGESTION_PLAN = {
    "env": "FLOODLENS_DEM_PATH",
    "reader": "floodlens.application.terrain_service.get_window",
    "resample": "city EPSG:4326 bounds onto 32×32 working tensor",
    "fail_closed": True,
    "synthetic_allowed": "pipeline tests only; never for real-model evaluation",
    "candidate_sources": [
        "Copernicus GLO-30 (license check before redistribution)",
        "FABDEM (Copernicus-derived, flattened buildings/forests)",
        "SRTM 1-arc-second (void-filled)",
    ],
    "justification": (
        "Without terrain, six of eight U-Net channels are spatially constant and "
        "the remaining two are lagged inundation. Terrain is first-order for "
        "where water can stand; missing DEM is a structural limitation, not a "
        "cosmetic gap."
    ),
    "not_acquired": (
        "No local GeoTIFF is configured. Do not download a national DEM in this "
        "phase unless FLOODLENS_DEM_PATH is set by the operator. Phase 6 v2 also "
        "samples real Open-Meteo elevation (SRTM/GLO family) per AOI lattice; "
        "that is still not a synthetic DEM."
    ),
}


def try_load_city_dem(city_id: str) -> Tuple[Optional[np.ndarray], bool]:
    """Return (elevation 32×32, present). Zeros are not invented when missing."""
    from floodlens.application.terrain_service import get_window

    window = get_window(city_id, max_size=GRID_SIZE)
    if not window.get("available"):
        return None, False
    elev = window.get("elevation")
    if elev is None:
        return None, False
    arr = np.asarray(elev, dtype=np.float64)
    if arr.size == 0 or not np.any(np.isfinite(arr)):
        return None, False
    if arr.ndim != 2:
        return None, False
    if arr.shape != (GRID_SIZE, GRID_SIZE):
        # nearest-neighbor resize without inventing values outside the window
        ys = np.linspace(0, arr.shape[0] - 1, GRID_SIZE)
        xs = np.linspace(0, arr.shape[1] - 1, GRID_SIZE)
        yi = np.clip(np.round(ys).astype(int), 0, arr.shape[0] - 1)
        xi = np.clip(np.round(xs).astype(int), 0, arr.shape[1] - 1)
        arr = arr[np.ix_(yi, xi)]
    return arr, True


def try_load_aoi_dem(aoi_id: str, ny: int, nx: int):
    """GLO-30 (or configured GeoTIFF) window on AOI bounds. Never synthetic.

    Extra v2 AOIs are not product cities. Use a catalog city_id so get_window
    can open the file, and pass explicit AOI geographic bounds.
    """
    from floodlens.application.terrain_service import get_window
    from floodlens.ml.spatial.aois_v2 import aoi_bounds, q_proxy_city

    west, south, east, north = aoi_bounds(aoi_id)
    bounds = {"west": west, "south": south, "east": east, "north": north}
    proxy = q_proxy_city(aoi_id)
    if proxy not in {"dhaka", "sunamganj", "sylhet"}:
        proxy = "sunamganj"
    try:
        window = get_window(proxy, bounds=bounds, max_size=max(int(ny), int(nx), 64))
    except Exception as exc:
        return None, False, {
            "status": "UNAVAILABLE",
            "reason": f"get_window_failed:{exc}",
            "source": None,
            "synthetic": False,
        }
    if not window.get("available"):
        return None, False, {
            "status": "UNAVAILABLE",
            "reason": window.get("reason") or "FLOODLENS_DEM_PATH unset or missing",
            "source": None,
            "synthetic": False,
        }
    elev = window.get("elevation")
    if elev is None:
        return None, False, {"status": "UNAVAILABLE", "reason": "empty_window", "synthetic": False}
    arr = np.asarray(elev, dtype=np.float64)
    if arr.size == 0 or not np.any(np.isfinite(arr)) or arr.ndim != 2:
        return None, False, {"status": "UNAVAILABLE", "reason": "nodata_window", "synthetic": False}
    if arr.shape != (ny, nx):
        ys = np.linspace(0, arr.shape[0] - 1, ny)
        xs = np.linspace(0, arr.shape[1] - 1, nx)
        yi = np.clip(np.round(ys).astype(int), 0, arr.shape[0] - 1)
        xi = np.clip(np.round(xs).astype(int), 0, arr.shape[1] - 1)
        arr = arr[np.ix_(yi, xi)]
    meta = {
        "status": "OBSERVED",
        "source": "FLOODLENS_DEM_PATH",
        "crs": window.get("crs"),
        "nodata": window.get("nodata"),
        "uri": window.get("uri"),
        "vertical_metadata": window.get("statistics"),
        "synthetic": False,
        "resolution": f"window resampled to {ny}×{nx}",
    }
    return arr, True, meta


def height_above_nearest_river(dem: Optional[np.ndarray], river_mask: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Elevation minus min elevation on river-mask cells. Not a global D8 HAND."""
    if dem is None or river_mask is None:
        return None
    elev = np.asarray(dem, dtype=np.float64)
    mask = np.asarray(river_mask) > 0
    if not np.any(mask):
        return None
    river_vals = elev[mask]
    river_vals = river_vals[np.isfinite(river_vals)]
    if river_vals.size == 0:
        return None
    return elev - float(np.min(river_vals))
