"""City AOI 32×32 working grids. Native GFM is 20 m Equi7; we resample.

Sunamganj at 32×32 is ~1 km/cell after cap (native target 500 m, MAX_CELLS=32).
Dhaka/Sylhet are coarser. Honesty flags stay on the sample.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from floodlens.application.city_data import create_city_registry
from floodlens.ml.spatial.schema import GRID_SIZE, TARGET_RESOLUTION_M

CITIES = ("dhaka", "sunamganj", "sylhet")


def city_bounds(city_id: str) -> Tuple[float, float, float, float]:
    city = create_city_registry().get_city(city_id)
    b = city.bounds
    return (b.west, b.south, b.east, b.north)


def cell_size_m(bounds: Tuple[float, float, float, float], ny: int, nx: int) -> Tuple[float, float]:
    west, south, east, north = bounds
    lat_m = 111_320.0 * (north - south) / max(ny, 1)
    mean_lat = 0.5 * (south + north)
    lon_m = 111_320.0 * math.cos(math.radians(mean_lat)) * (east - west) / max(nx, 1)
    return lon_m, lat_m


def grid_spec(city_id: str, size: int = GRID_SIZE) -> dict:
    bounds = city_bounds(city_id)
    dx_m, dy_m = cell_size_m(bounds, size, size)
    return {
        "city_id": city_id,
        "nx": size,
        "ny": size,
        "bounds": list(bounds),
        "crs": "EPSG:4326",
        "dx_m": dx_m,
        "dy_m": dy_m,
        "target_resolution_m": TARGET_RESOLUTION_M,
        "note": (
            "Working tensor is {size}×{size} on the city geographic bounds. "
            "Native GFM is 20 m Equi7. This is not 500 m radar."
        ).format(size=size),
    }


def all_grid_specs() -> Dict[str, dict]:
    return {cid: grid_spec(cid) for cid in CITIES}
