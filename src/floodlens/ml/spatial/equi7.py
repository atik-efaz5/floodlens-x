"""Equi7Grid Asia 20 m (Azimuthal Equidistant) helpers.

GFM AS020M tiles use Equi7, not EPSG:4326. Physics city grids are geographic;
that CRS mismatch is documented in docs/TERRAIN.md and is not hidden here.

Spherical aeqd with WGS84 R is used (no pyproj). Window error vs ellipsoid
aeqd is on the order of ~1 km — about one 500 m cell. Documented, not claimed
as survey-grade.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np

# GeoTIFF tags from GFM ENSEMBLE_FLOOD … AS020M E039N021T3
R_WGS84 = 6378137.0
LAT0_DEG = 47.0
LON0_DEG = 94.0
FALSE_EASTING = 4340913.84808
FALSE_NORTHING = 4812712.92347
TIE_X = 3900000.0
TIE_Y = 2400000.0
PIXEL_M = 20.0
TILE_SIZE = 15000
TILE_ID = "E039N021T3"
# T3 tiles are 300 km. North edge of N021 is 2_400_000; N024 sits immediately north.
TILE_CATALOG = {
    "E039N021T3": {"tie_x": 3900000.0, "tie_y": 2400000.0},
    "E039N024T3": {"tie_x": 3900000.0, "tie_y": 2700000.0},
}
NEIGHBOR_TILE_ID = "E039N024T3"


def lonlat_to_equi7(lat_deg: float, lon_deg: float) -> Tuple[float, float]:
    lat0 = math.radians(LAT0_DEG)
    lon0 = math.radians(LON0_DEG)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_c = math.sin(lat0) * math.sin(lat) + math.cos(lat0) * math.cos(lat) * math.cos(lon - lon0)
    cos_c = max(-1.0, min(1.0, cos_c))
    c = math.acos(cos_c)
    k = 1.0 if abs(c) < 1e-12 else c / math.sin(c)
    x = R_WGS84 * k * math.cos(lat) * math.sin(lon - lon0)
    y = R_WGS84 * k * (
        math.cos(lat0) * math.sin(lat) - math.sin(lat0) * math.cos(lat) * math.cos(lon - lon0)
    )
    return x + FALSE_EASTING, y + FALSE_NORTHING


def tile_ties(tile_id: str = TILE_ID) -> Tuple[float, float]:
    spec = TILE_CATALOG.get(tile_id) or TILE_CATALOG[TILE_ID]
    return float(spec["tie_x"]), float(spec["tie_y"])


def equi7_to_pixel(x: float, y: float, tile_id: str = TILE_ID) -> Tuple[float, float]:
    tie_x, tie_y = tile_ties(tile_id)
    col = (x - tie_x) / PIXEL_M
    row = (tie_y - y) / PIXEL_M
    return row, col


def lonlat_to_pixel(lat_deg: float, lon_deg: float, tile_id: str = TILE_ID) -> Tuple[float, float]:
    x, y = lonlat_to_equi7(lat_deg, lon_deg)
    return equi7_to_pixel(x, y, tile_id=tile_id)


def city_window(bounds: Sequence[float], pad: int = 8, tile_id: str = TILE_ID) -> Tuple[int, int, int, int]:
    """Return (row0, row1, col0, col1) clipped to the Equi7 tile."""
    west, south, east, north = bounds
    rows = []
    cols = []
    for lat, lon in ((south, west), (south, east), (north, west), (north, east)):
        r, c = lonlat_to_pixel(lat, lon, tile_id=tile_id)
        rows.append(r)
        cols.append(c)
    r0 = max(0, int(math.floor(min(rows))) - pad)
    r1 = min(TILE_SIZE, int(math.ceil(max(rows))) + pad)
    c0 = max(0, int(math.floor(min(cols))) - pad)
    c1 = min(TILE_SIZE, int(math.ceil(max(cols))) + pad)
    if r1 <= r0 or c1 <= c0:
        raise ValueError(f"empty Equi7 window for bounds {bounds}")
    return r0, r1, c0, c1


def in_tile(lat_deg: float, lon_deg: float, tile_id: str = TILE_ID) -> bool:
    r, c = lonlat_to_pixel(lat_deg, lon_deg, tile_id=tile_id)
    return 0 <= r < TILE_SIZE and 0 <= c < TILE_SIZE


def block_reduce_mode(arr: np.ndarray, out_h: int, out_w: int, nodata: int = 255) -> Tuple[np.ndarray, np.ndarray]:
    """Resample a class raster to (out_h, out_w).

    Returns (class_map, flood_fraction) where flood_fraction is the share of
    valid 20 m pixels that are flood, and class is 255 if too few valid pixels.
    """
    src = np.asarray(arr)
    h, w = src.shape
    frac = np.zeros((out_h, out_w), dtype=np.float32)
    cls = np.full((out_h, out_w), nodata, dtype=np.uint8)
    for i in range(out_h):
        r0 = int(round(i * h / out_h))
        r1 = int(round((i + 1) * h / out_h))
        r1 = max(r1, r0 + 1)
        for j in range(out_w):
            c0 = int(round(j * w / out_w))
            c1 = int(round((j + 1) * w / out_w))
            c1 = max(c1, c0 + 1)
            block = src[r0:r1, c0:c1]
            valid = block != nodata
            n_valid = int(np.sum(valid))
            if n_valid < max(1, block.size // 8):
                continue
            wet = float(np.mean(block[valid] == 1))
            frac[i, j] = wet
            cls[i, j] = 1 if wet >= 0.25 else 0
    return cls, frac
