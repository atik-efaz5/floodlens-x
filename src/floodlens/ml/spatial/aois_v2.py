"""Bangladesh spatial AOIs for Phase 6. Product catalog stays three cities."""

from __future__ import annotations

from typing import Dict, Tuple

from floodlens.ml.spatial.tiles import city_bounds

# west, south, east, north
AOI_BOUNDS: Dict[str, Tuple[float, float, float, float]] = {
    "sunamganj": (91.20, 24.80, 91.50, 25.10),
    "sylhet": (91.50, 24.40, 92.30, 25.20),
    "kishoreganj": (90.70, 24.20, 91.20, 24.65),
    "netrokona": (90.65, 24.70, 91.15, 25.10),
    "dhaka_sw": (90.00, 23.50, 90.40, 23.80),
    "dhaka_se": (90.40, 23.50, 90.80, 23.80),
    "dhaka_nw": (90.00, 23.80, 90.40, 24.10),
    "dhaka_ne": (90.40, 23.80, 90.80, 24.10),
}

# Keep full Dhaka for product clips; v2 training prefers subtiles so cell size ~1 km.
AOI_IDS_V2 = tuple(AOI_BOUNDS.keys())
PRODUCT_CITIES = ("dhaka", "sunamganj", "sylhet")

Q_PROXY = {
    "sunamganj": "sunamganj",
    "sylhet": "sylhet",
    "kishoreganj": "sunamganj",
    "netrokona": "sunamganj",
    "dhaka_sw": "dhaka",
    "dhaka_se": "dhaka",
    "dhaka_nw": "dhaka",
    "dhaka_ne": "dhaka",
    "dhaka": "dhaka",
}

GEO_TEST_AOIS = frozenset({"sunamganj", "sylhet", "netrokona"})


def aoi_bounds(aoi_id: str) -> Tuple[float, float, float, float]:
    if aoi_id in AOI_BOUNDS:
        return AOI_BOUNDS[aoi_id]
    return city_bounds(aoi_id)


def q_proxy_city(aoi_id: str) -> str:
    return Q_PROXY.get(aoi_id, "sunamganj")
