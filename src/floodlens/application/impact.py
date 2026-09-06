"""Impact: intersect flood depth samples with OSM assets. No invented counts."""

from __future__ import annotations

from typing import Optional

from floodlens.application.cell_inspection import InspectionError, latlon_to_grid_cell
from floodlens.application.geospatial import GeographicBounds, GridReference
from floodlens.application.population import get_population_provider
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, demo_provenance, isoformat

try:
    from shapely.geometry import LineString

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def _depth_at_point(lat: float, lon: float, bounds: GeographicBounds, grid: GridReference, depth) -> Optional[float]:
    try:
        row, col = latlon_to_grid_cell(lat, lon, grid, bounds)
    except InspectionError:
        return None
    return float(depth[row, col])


def _roads_affected(assets: list, bounds: GeographicBounds, grid: GridReference, depth, threshold: float = 0.05) -> dict:
    lines = [a for a in assets if a.get("coordinates") and a.get("asset_type") == "road"]
    if not lines:
        return {"computed": True, "percent_length_flooded": 0.0, "roads_evaluated": 0}
    if not HAS_SHAPELY:
        return {
            "computed": False,
            "reason": "NOT_COMPUTED: shapely is not installed; line length flood fraction withheld.",
            "roads_evaluated": len(lines),
        }
    flooded_len = 0.0
    total_len = 0.0
    for asset in lines:
        try:
            line = LineString(asset["coordinates"])
        except (TypeError, ValueError):
            continue
        if line.length <= 0:
            continue
        total_len += line.length
        samples = max(4, min(40, int(line.length / 0.002) or 4))
        wet = 0
        for i in range(samples + 1):
            pt = line.interpolate(i / samples, normalized=True)
            depth_m = _depth_at_point(pt.y, pt.x, bounds, grid, depth)
            if depth_m is not None and depth_m > threshold:
                wet += 1
        flooded_len += line.length * (wet / (samples + 1))
    percent = (100.0 * flooded_len / total_len) if total_len else 0.0
    return {
        "computed": True,
        "percent_length_flooded": round(percent, 2),
        "roads_evaluated": len(lines),
        "threshold_m": threshold,
    }


def road_flood_fraction(asset: dict, bounds: GeographicBounds, grid: GridReference, depth, threshold: float = 0.05) -> dict:
    """Per-road flood-exposure fraction. Missing raster/shapely stays NOT_COMPUTED, never 0."""
    if not asset.get("coordinates"):
        return {
            "status": "UNKNOWN",
            "computed": False,
            "percent_length_flooded": None,
            "reason": "No road geometry.",
        }
    if depth is None:
        return {
            "status": "NOT_COMPUTED",
            "computed": False,
            "percent_length_flooded": None,
            "reason": "ROAD FLOOD IMPACT: NOT_COMPUTED. No flood raster is attached.",
        }
    if not HAS_SHAPELY:
        return {
            "status": "NOT_COMPUTED",
            "computed": False,
            "percent_length_flooded": None,
            "reason": "ROAD FLOOD IMPACT: NOT_COMPUTED. shapely is not installed; line length flood fraction withheld.",
        }
    try:
        line = LineString(asset["coordinates"])
    except (TypeError, ValueError):
        return {
            "status": "UNKNOWN",
            "computed": False,
            "percent_length_flooded": None,
            "reason": "Road coordinates could not be parsed.",
        }
    if line.length <= 0:
        return {
            "status": "UNKNOWN",
            "computed": False,
            "percent_length_flooded": None,
            "reason": "Road geometry has zero length.",
        }
    samples = max(4, min(40, int(line.length / 0.002) or 4))
    wet = 0
    for i in range(samples + 1):
        pt = line.interpolate(i / samples, normalized=True)
        depth_m = _depth_at_point(pt.y, pt.x, bounds, grid, depth)
        if depth_m is not None and depth_m > threshold:
            wet += 1
    percent = 100.0 * wet / (samples + 1)
    return {
        "status": "AFFECTED" if percent > 0 else "NOT_AFFECTED",
        "computed": True,
        "percent_length_flooded": round(percent, 2),
        "reason": None,
        "threshold_m": threshold,
        "note": "Potential flood-exposure percentage of sampled road geometry. Not travel time or a safe route.",
    }


def assess_impact(city_id: str, bounds: dict, grid: dict, depth) -> dict:
    store = get_platform_store()
    assets = store.assets_for_city(city_id)
    geo_bounds = GeographicBounds(
        west=bounds["west"],
        south=bounds["south"],
        east=bounds["east"],
        north=bounds["north"],
    )
    grid_ref = GridReference(
        nx=grid["nx"],
        ny=grid["ny"],
        dx=grid.get("dx", 1.0),
        dy=grid.get("dy", 1.0),
        origin_x=grid.get("origin_x", bounds["west"]),
        origin_y=grid.get("origin_y", bounds["south"]),
        crs=grid.get("crs", "EPSG:4326"),
    )
    exposed = []
    for asset in assets:
        if asset.get("lat") is None or asset.get("lon") is None:
            continue
        depth_m = _depth_at_point(asset["lat"], asset["lon"], geo_bounds, grid_ref, depth)
        if depth_m is None:
            continue
        flooded = depth_m > 0.05
        exposed.append(
            {
                "id": asset["id"],
                "name": asset["name"],
                "asset_type": asset["asset_type"],
                "depth_m": depth_m,
                "flooded": flooded,
            }
        )
    counts = {}
    for row in exposed:
        if row["flooded"]:
            counts[row["asset_type"]] = counts.get(row["asset_type"], 0) + 1
    return {
        "city_id": city_id,
        "asset_total": len(assets),
        "point_assets_evaluated": len(exposed),
        "flooded_counts": counts,
        "assets": exposed,
        "roads_affected": _roads_affected(assets, geo_bounds, grid_ref, depth),
        "polygons_affected": {"computed": False, "reason": "NOT_COMPUTED"},
        "accessibility": {"computed": False, "reason": "NOT_COMPUTED"},
        "population_exposed": get_population_provider().expose(city_id)["population_exposed"],
        "population_note": get_population_provider().expose(city_id).get("reason")
        or "Population grid not ingested; count withheld.",
        "generated_at": isoformat(),
        "source": "impact-service",
        "data_status": "SIMULATED",
        "provenance": demo_provenance("impact-service", PHYSICS_MODEL_VERSION).to_dict(),
    }
