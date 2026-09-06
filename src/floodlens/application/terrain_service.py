"""Windowed DEM access for modeling. Never invents elevations. Never loads a full country raster."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope, public_source_ref
from floodlens.application.dem_manager import HAS_RASTERIO, DEMManager
from floodlens.application.repository import get_repository
from floodlens.core.config import SimulationConfig


def _dem_path(path: Optional[str] = None) -> Optional[str]:
    uri = path or os.environ.get("FLOODLENS_DEM_PATH")
    if uri and Path(uri).exists():
        return uri
    return None


def get_bounds(city_id: str) -> dict:
    city = create_city_registry().get_city(city_id)
    terrain = get_repository().get_terrain(city_id)
    bounds = terrain.bounds if terrain and terrain.bounds else city.bounds.to_dict()
    return {
        "city_id": city_id,
        "bounds": bounds,
        "crs": (terrain.crs if terrain else city.crs) or "EPSG:4326",
        "provenance": envelope(
            data_status=terrain.data_status if terrain else "UNAVAILABLE",
            provider="DEM",
            dataset="terrain",
            freshness="STATIC",
        ),
    }


def get_resolution(city_id: str) -> dict:
    terrain = get_repository().get_terrain(city_id)
    return {
        "city_id": city_id,
        "resolution_deg": terrain.resolution_deg if terrain else None,
        "available": bool(terrain and terrain.data_status == "REAL"),
    }


def get_window(city_id: str, bounds: Optional[dict] = None, path: Optional[str] = None, max_size: int = 128) -> dict:
    """Read a spatial window. Does not load the full GeoTIFF."""
    uri = _dem_path(path)
    city = create_city_registry().get_city(city_id)
    window_bounds = bounds or city.bounds.to_dict()
    if not uri:
        from floodlens.application.demo_fixtures import demo_fixtures_enabled, ensure_demo_terrain

        if demo_fixtures_enabled():
            preview = ensure_demo_terrain(city_id, window_bounds)
            return {
                "available": False,
                "preview_available": True,
                "reason": (
                    "DEMO hillshade preview. Elevations are not a GeoTIFF DEM "
                    "and are not passed to the solver."
                ),
                "elevation": None,
                "statistics": preview["statistics"],
                "overlay_artifact_id": preview["overlay_artifact_id"],
                "bounds": window_bounds,
                "crs": preview["crs"],
                "provenance": envelope(
                    data_status="DEMO",
                    provider="demo-terrain-generator",
                    dataset="terrain",
                    freshness="SNAPSHOT",
                    simulated=True,
                    fallback_used=True,
                ),
            }
        return {
            "available": False,
            "reason": "Terrain unavailable. FLOODLENS_DEM_PATH is unset or the file is missing. Elevations are not invented.",
            "elevation": None,
            "provenance": envelope(
                data_status="UNAVAILABLE",
                provider="DEM",
                dataset="terrain",
                freshness="STATIC",
            ),
        }
    if not HAS_RASTERIO:
        return {
            "available": False,
            "reason": "rasterio is required for windowed GeoTIFF reads.",
            "elevation": None,
            "provenance": envelope(
                data_status="UNAVAILABLE",
                provider="DEM",
                dataset="terrain",
                freshness="STATIC",
            ),
        }

    import rasterio
    from rasterio.windows import from_bounds, Window

    with rasterio.open(uri) as src:
        west = window_bounds.get("west", src.bounds.left)
        south = window_bounds.get("south", src.bounds.bottom)
        east = window_bounds.get("east", src.bounds.right)
        north = window_bounds.get("north", src.bounds.top)
        window = from_bounds(west, south, east, north, transform=src.transform)
        window = window.intersection(Window(0, 0, src.width, src.height))
        if window.width <= 0 or window.height <= 0:
            window = Window(0, 0, min(max_size, src.width), min(max_size, src.height))
        col_off = int(window.col_off)
        row_off = int(window.row_off)
        width = min(int(np.ceil(window.width)), max_size)
        height = min(int(np.ceil(window.height)), max_size)
        sample = src.read(1, window=Window(col_off, row_off, width, height))
        nodata = src.nodata
        crs = src.crs.to_string() if src.crs else "EPSG:4326"
        transform = src.window_transform(Window(col_off, row_off, width, height))

    elevation = np.asarray(sample, dtype=np.float64)
    if nodata is not None:
        elevation = np.where(elevation == nodata, np.nan, elevation)
    finite = elevation[np.isfinite(elevation)]
    stats = {
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
    }
    return {
        "available": True,
        "elevation": elevation,
        "shape": list(elevation.shape),
        "crs": crs,
        "nodata": float(nodata) if nodata is not None else None,
        "bounds": window_bounds,
        "transform": [float(transform.a), float(transform.b), float(transform.c), float(transform.d), float(transform.e), float(transform.f)],
        "uri": public_source_ref(str(Path(uri).resolve())),
        "statistics": stats,
        "provenance": envelope(
            data_status="REAL",
            provider="GeoTIFF",
            dataset="terrain",
            freshness="STATIC",
            source_version=Path(uri).name,
        ),
    }


def get_elevation(city_id: str, row: int, col: int, path: Optional[str] = None) -> dict:
    window = get_window(city_id, path=path, max_size=max(row + 1, col + 1, 8))
    if not window["available"]:
        return window
    z = window["elevation"]
    if row < 0 or col < 0 or row >= z.shape[0] or col >= z.shape[1]:
        return {"available": False, "reason": "Cell outside window.", "elevation": None}
    value = float(z[row, col])
    if not np.isfinite(value):
        return {"available": False, "reason": "nodata", "elevation": None}
    return {"available": True, "elevation_m": value, "units": "m", "row": row, "col": col}


def calculate_slope(elevation: np.ndarray, dx: float = 1.0, dy: float = 1.0) -> np.ndarray:
    gy, gx = np.gradient(elevation, dy, dx)
    return np.sqrt(gx * gx + gy * gy)


def calculate_terrain_statistics(city_id: str, path: Optional[str] = None) -> dict:
    window = get_window(city_id, path=path)
    if not window["available"]:
        return window
    z = window["elevation"]
    slope = calculate_slope(z)
    finite_s = slope[np.isfinite(slope)]
    return {
        "available": True,
        "statistics": window["statistics"],
        "slope": {
            "min": float(finite_s.min()) if finite_s.size else None,
            "max": float(finite_s.max()) if finite_s.size else None,
            "mean": float(finite_s.mean()) if finite_s.size else None,
            "units": "rise/run on window grid",
        },
        "flow_direction": None,
        "flow_direction_note": "NOT_COMPUTED. D8/D-infinity flow direction is not part of this baseline.",
        "provenance": window["provenance"],
    }


def resample_window_to_grid(city_id: str, config: SimulationConfig, path: Optional[str] = None) -> dict:
    """Windowed read then bilinear resample to (Ny, Nx). Fails closed if DEM missing."""
    window = get_window(city_id, path=path, max_size=max(config.Nx, config.Ny, 64))
    if not window["available"]:
        return window
    z = window.get("elevation")
    if z is None:
        return {
            "available": False,
            "reason": "Terrain window has no elevation array. DEMO hillshade is not a solver DEM.",
            "elevation": None,
        }
    if (window.get("provenance") or {}).get("data_status") == "DEMO":
        return {
            "available": False,
            "reason": "DEMO hillshade is not a DEM. Solver DEM remains unconfigured.",
            "elevation": None,
        }
    if not np.isfinite(z).any():
        return {
            "available": False,
            "reason": "Terrain window contains no finite elevations.",
            "elevation": None,
        }
    filled = np.where(np.isfinite(z), z, np.nanmean(z))
    resampled = DEMManager.resample_terrain(filled, (config.Lx, config.Ly), config)
    return {
        "available": True,
        "elevation": resampled,
        "crs": window["crs"],
        "uri": window["uri"],
        "data_status": "REAL",
        "provenance": window["provenance"],
    }
