"""Operational impact workspace. Never invents population, capacity, routes, or inventories."""

from __future__ import annotations

from typing import Optional

from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.geospatial import GridReference
from floodlens.application.impact import assess_impact, road_flood_fraction
from floodlens.application.ingest import ingest_osm_assets
from floodlens.application.platform_store import get_platform_store
from floodlens.application.population import get_population_provider
from floodlens.application.risk import risk_for_city

_CITIES = create_city_registry()
ASSET_LIMIT = 200
POINT_TYPES = {"hospital", "school", "bridge", "shelter", "clinic", "emergency", "fire_station", "police"}
CRITICAL_TYPES = {"emergency", "fire_station", "police", "clinic"}
SAFETY = (
    "Potential evacuation-risk analysis. Planning support only. "
    "Review with official emergency guidance. Not an official evacuation order."
)


def _city(city_id: str):
    try:
        return _CITIES.get_city(city_id)
    except KeyError as exc:
        raise KeyError(city_id) from exc


def _in_bbox(asset: dict, bbox: Optional[tuple[float, float, float, float]]) -> bool:
    if not bbox:
        return True
    west, south, east, north = bbox
    lat, lon = asset.get("lat"), asset.get("lon")
    if lat is not None and lon is not None:
        return west <= float(lon) <= east and south <= float(lat) <= north
    for pt in asset.get("coordinates") or []:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            if west <= float(pt[0]) <= east and south <= float(pt[1]) <= north:
                return True
    return False


def _scenario_info(ctx: dict) -> dict:
    job = ctx.get("job")
    return {
        "job_id": (job or {}).get("id"),
        "kind": (job or {}).get("kind"),
        "label": "SCENARIO" if job else "BASELINE",
        "artifact_id": ((job or {}).get("result") or {}).get("artifact_id"),
        "available": ctx.get("depth") is not None,
    }


def _flood_context(city_id: str, job_id: Optional[str] = None) -> dict:
    city = _city(city_id)
    store = get_platform_store()
    job = None
    if job_id:
        job = store.jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
    else:
        candidates = [
            row
            for row in store.jobs.values()
            if row.get("city_id") == city_id
            and row.get("status") == "completed"
            and (row.get("result") or {}).get("artifact_id")
        ]
        job = max(candidates, key=lambda row: row.get("created_at") or "") if candidates else None
    if not job or not job.get("result"):
        return {"city": city, "job": None, "depth": None, "grid": None, "assessment": None}
    from floodlens.application.artifact_store import get_artifact, get_depth

    artifact_id = job["result"].get("artifact_id")
    depth = get_depth(artifact_id) if artifact_id else None
    artifact = get_artifact(artifact_id) or {}
    if depth is None:
        return {"city": city, "job": job, "depth": None, "grid": None, "assessment": None}
    nx = artifact.get("nx") or depth.shape[1]
    ny = artifact.get("ny") or depth.shape[0]
    bounds = city.bounds.to_dict()
    grid = {
        "nx": nx,
        "ny": ny,
        "dx": (city.bounds.east - city.bounds.west) / nx,
        "dy": (city.bounds.north - city.bounds.south) / ny,
        "origin_x": city.bounds.west,
        "origin_y": city.bounds.south,
        "crs": "EPSG:4326",
    }
    return {
        "city": city,
        "job": job,
        "depth": depth,
        "grid": grid,
        "assessment": assess_impact(city_id, bounds, grid, depth),
    }


def _point_lookup(assessment: Optional[dict]) -> dict:
    return {row["id"]: row for row in (assessment or {}).get("assets") or []}


def _point_status(asset: dict, lookup: dict, has_raster: bool) -> dict:
    if asset.get("asset_type") == "road":
        return {"status": "NOT_COMPUTED", "depth_m": None, "note": "See road flood-impact field."}
    if not has_raster:
        return {
            "status": "NOT_COMPUTED",
            "depth_m": None,
            "expected_depth_m": None,
            "note": "No physics flood raster is attached. Exposure is not inferred from river proximity.",
        }
    if asset.get("lat") is None or asset.get("lon") is None:
        return {"status": "UNKNOWN", "depth_m": None, "expected_depth_m": None, "note": "Point coordinates missing."}
    row = lookup.get(asset.get("id"))
    if not row:
        return {
            "status": "UNKNOWN",
            "depth_m": None,
            "expected_depth_m": None,
            "note": "Asset is outside the attached flood grid or was not sampled.",
        }
    flooded = bool(row.get("flooded"))
    return {
        "status": "EXPOSED" if flooded else "NOT_EXPOSED",
        "depth_m": row.get("depth_m"),
        "expected_depth_m": row.get("depth_m"),
        "note": "Potential flood exposure from the attached flood-impact layer. Not structural damage.",
        "computation": "COMPUTED FROM CURRENT FLOOD OVERLAY",
    }


def _category_row(status: str, *, total=None, affected=None, unknown=None, reason: str, source: str, computation: str) -> dict:
    return {
        "status": status,
        "total": total,
        "affected": affected,
        "unknown": unknown,
        "reason": reason,
        "source": source,
        "computation": computation,
    }


def region_impact(city_id: str, job_id: Optional[str] = None, bbox=None, limit: int = ASSET_LIMIT) -> dict:
    ingest_osm_assets(city_id)
    ctx = _flood_context(city_id, job_id)
    store = get_platform_store()
    cap = min(max(limit, 1), ASSET_LIMIT)
    assets = [a for a in store.assets_for_city(city_id) if _in_bbox(a, bbox)]
    lookup = _point_lookup(ctx["assessment"])
    has_raster = ctx["depth"] is not None
    pop = get_population_provider().expose(city_id)
    assessment = ctx["assessment"]
    flooded = (assessment or {}).get("flooded_counts") or {}

    def typed(kind: str) -> list:
        return [a for a in assets if a.get("asset_type") == kind]

    def point_category(kind: str, label_source: str) -> dict:
        rows = typed(kind)
        if not has_raster:
            return _category_row(
                "NOT_COMPUTED",
                total=len(rows),
                affected=None,
                unknown=len(rows),
                reason="No flood raster is attached. Assets are listed; exposure is not invented.",
                source=label_source,
                computation="NOT_COMPUTED",
            )
        exposed = 0
        unknown = 0
        for asset in rows:
            status = _point_status(asset, lookup, True)["status"]
            if status == "EXPOSED":
                exposed += 1
            elif status != "NOT_EXPOSED":
                unknown += 1
        return _category_row(
            "SIMULATED",
            total=len(rows),
            affected=exposed,
            unknown=unknown,
            reason="Point depth sampled on the attached physics/scenario raster (threshold 0.05 m).",
            source=label_source,
            computation="COMPUTED FROM CURRENT FLOOD OVERLAY",
        )

    roads = typed("road")
    road_info = (assessment or {}).get("roads_affected") or {}
    if not roads:
        road_cat = _category_row(
            "UNAVAILABLE",
            total=0,
            affected=None,
            unknown=None,
            reason="No road geometry is cataloged in this region/bbox.",
            source="osm-or-fixture",
            computation="UNAVAILABLE",
        )
    elif not has_raster or not road_info.get("computed"):
        road_cat = _category_row(
            "NOT_COMPUTED",
            total=len(roads),
            affected=None,
            unknown=len(roads),
            reason=(road_info.get("reason") or "ROAD FLOOD IMPACT: NOT_COMPUTED."),
            source="osm-or-fixture",
            computation="NOT_COMPUTED",
        )
    else:
        road_cat = _category_row(
            "SIMULATED",
            total=len(roads),
            affected=road_info.get("roads_evaluated"),
            unknown=None,
            reason="Potential flood-exposure percentage of evaluated road geometry. Not accessibility or travel time.",
            source="osm-or-fixture",
            computation="COMPUTED FROM CURRENT FLOOD OVERLAY",
        )
        road_cat["percent_length_flooded"] = road_info.get("percent_length_flooded")

    return {
        "city_id": city_id,
        "scenario": _scenario_info(ctx),
        "timestamp": (assessment or {}).get("generated_at"),
        "categories": {
            "population": _category_row(
                pop.get("data_status") or ("UNAVAILABLE" if not pop.get("available") else "REAL"),
                total=None,
                affected=pop.get("population_exposed"),
                unknown=None,
                reason=pop.get("reason") or "No authoritative population dataset is currently configured.",
                source="population-provider",
                computation="UNAVAILABLE" if not pop.get("available") else "COMPUTED",
            ),
            "buildings": _category_row(
                "NOT_COMPUTED",
                reason="Polygon building impact is NOT_COMPUTED.",
                source="none",
                computation="NOT_COMPUTED",
            ),
            "roads": road_cat,
            "bridges": point_category("bridge", "osm-or-fixture"),
            "hospitals": point_category("hospital", "osm-or-fixture"),
            "schools": point_category("school", "osm-or-fixture"),
            "agriculture": _category_row(
                "UNAVAILABLE",
                reason="No agriculture exposure dataset is configured.",
                source="none",
                computation="UNAVAILABLE",
            ),
            "critical": _category_row(
                "NOT_COMPUTED" if not has_raster else "SIMULATED",
                total=len([a for a in assets if a.get("asset_type") in CRITICAL_TYPES]),
                affected=sum(flooded.get(k, 0) for k in CRITICAL_TYPES) if has_raster else None,
                unknown=None if has_raster else len([a for a in assets if a.get("asset_type") in CRITICAL_TYPES]),
                reason="Critical OSM amenities (clinic/emergency/fire/police) when cataloged.",
                source="osm-or-fixture",
                computation="NOT_COMPUTED" if not has_raster else "COMPUTED FROM CURRENT FLOOD OVERLAY",
            ),
            "shelters": point_category("shelter", "osm-or-fixture"),
        },
        "asset_total": len(assets),
        "limit": cap,
        "safety": SAFETY,
        "assumptions": [
            "Point flooding uses depth > 0.05 m on the attached raster only.",
            "OSM/fixture geometry may be DEMO. DEMO is not treated as a live operational inventory.",
            "Population, shelter capacity, occupancy, routes, and resource inventories are not invented.",
        ],
        "provenance": envelope(
            data_status="SIMULATED" if has_raster else "PARTIAL",
            provider="impact-service",
            dataset="impact-workspace",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def infrastructure_impact(
    city_id: str,
    job_id: Optional[str] = None,
    category: Optional[str] = None,
    bbox=None,
    limit: int = ASSET_LIMIT,
) -> dict:
    ingest_osm_assets(city_id)
    ctx = _flood_context(city_id, job_id)
    cap = min(max(limit, 1), ASSET_LIMIT)
    store = get_platform_store()
    assets = [a for a in store.assets_for_city(city_id) if _in_bbox(a, bbox)]
    if category:
        if category == "critical":
            assets = [a for a in assets if a.get("asset_type") in CRITICAL_TYPES]
        else:
            assets = [a for a in assets if a.get("asset_type") == category]
    lookup = _point_lookup(ctx["assessment"])
    geo = ctx["city"].bounds if ctx["grid"] else None
    grid_ref = GridReference(**ctx["grid"]) if ctx["grid"] else None
    rows = []
    for asset in assets[:cap]:
        point = _point_status(asset, lookup, ctx["depth"] is not None)
        road = None
        if asset.get("asset_type") == "road":
            if geo is not None and grid_ref is not None:
                road = road_flood_fraction(asset, geo, grid_ref, ctx["depth"])
            else:
                road = {
                    "status": "NOT_COMPUTED",
                    "computed": False,
                    "percent_length_flooded": None,
                    "reason": "ROAD FLOOD IMPACT: NOT_COMPUTED. No flood raster is attached.",
                }
        if road and not road.get("computed"):
            computation = "NOT_COMPUTED"
        else:
            computation = point.get("computation") or (
                "NOT_COMPUTED" if ctx["depth"] is None else "COMPUTED FROM CURRENT FLOOD OVERLAY"
            )
        rows.append(
            {
                "id": asset.get("id"),
                "name": asset.get("name"),
                "asset_type": asset.get("asset_type"),
                "latitude": asset.get("lat"),
                "longitude": asset.get("lon"),
                "impact_status": road["status"] if road else point["status"],
                "expected_depth_m": None if asset.get("asset_type") == "road" else point.get("expected_depth_m"),
                "road_flood_impact": road,
                "source": asset.get("source") or "osm-or-fixture",
                "timestamp": asset.get("retrieved_at") or asset.get("updated_at"),
                "data_status": asset.get("data_status") or "DEMO",
                "note": (road or point).get("reason") or (road or point).get("note"),
                "computation": computation,
            }
        )
    return {
        "city_id": city_id,
        "category": category,
        "assets": rows,
        "limit": cap,
        "count": len(rows),
        "scenario": _scenario_info(ctx),
        "safety": SAFETY,
        "provenance": envelope(
            data_status="DEMO",
            provider="osm-or-fixture",
            dataset="infrastructure-impact",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def shelter_assessments(city_id: str, job_id: Optional[str] = None, bbox=None, limit: int = ASSET_LIMIT) -> dict:
    payload = infrastructure_impact(city_id, job_id, category="shelter", bbox=bbox, limit=limit)
    rows = []
    for asset in payload["assets"]:
        exposure = asset["impact_status"]
        if exposure == "EXPOSED":
            suitability = "EXPOSED"
        elif exposure == "NOT_EXPOSED":
            suitability = "CAUTION"
        else:
            suitability = "UNKNOWN"
        rows.append(
            {
                **asset,
                "exposure_status": exposure,
                "accessibility_status": "NOT_COMPUTED",
                "capacity": None,
                "occupancy": None,
                "distance_m": None,
                "suitability": suitability,
                "suitability_note": (
                    "SHELTER FLOOD EXPOSURE uses the attached raster when available. "
                    "ACCESSIBILITY: UNAVAILABLE. CAPACITY: UNAVAILABLE. OCCUPANCY: UNAVAILABLE. "
                    "Not labeled globally safe. Fixture capacity figures are not treated as an authoritative inventory."
                ),
            }
        )
    return {
        "city_id": city_id,
        "shelters": rows,
        "limit": payload["limit"],
        "count": len(rows),
        "capacity_status": "UNAVAILABLE",
        "occupancy_status": "UNAVAILABLE",
        "accessibility_status": "NOT_COMPUTED",
        "scenario": payload["scenario"],
        "safety": SAFETY,
        "provenance": payload["provenance"],
    }


def evacuation_assessment(city_id: str, job_id: Optional[str] = None, bbox=None) -> dict:
    summary = region_impact(city_id, job_id, bbox=bbox)
    risk = risk_for_city(city_id)
    city = _city(city_id)
    roads = summary["categories"]["roads"]
    accessibility = {
        "status": "NOT_COMPUTED" if roads["status"] in {"NOT_COMPUTED", "UNAVAILABLE"} else "PARTIAL",
        "road_flood_exposure_percent": roads.get("percent_length_flooded"),
        "travel_time": None,
        "safe_route": None,
        "reason": roads["reason"]
        if roads["status"] != "SIMULATED"
        else "Potential flood-exposure percentage only. ROAD ACCESSIBILITY / travel time remain NOT_COMPUTED.",
    }
    from floodlens.application.demo_fixtures import demo_evac_route, demo_fixtures_enabled

    routes = {
        "status": "NOT_COMPUTED",
        "reason": "No routing graph is configured. Arbitrary nearest-road logic is not an evacuation route.",
    }
    if demo_fixtures_enabled():
        routes = demo_evac_route(city_id)
        if accessibility["status"] == "NOT_COMPUTED":
            accessibility = {
                **accessibility,
                "status": "DEMO",
                "reason": "DEMO planning accessibility note. Travel time remains NOT_COMPUTED. Not an official route.",
            }
    return {
        "city_id": city_id,
        "kind": "POTENTIAL EVACUATION-RISK ANALYSIS",
        "official_evacuation_order": False,
        "safety": SAFETY,
        "planning_boundary": {
            "kind": "STUDY REGION",
            "name": city.name,
            "source": "city-registry",
            "note": "Study region rectangle, not an administrative district and not an evacuation zone.",
        },
        "current_risk_category": risk.get("category"),
        "current_risk_note": "Heuristic P × E × S category. Not an evacuation order and not a validated inundation zone.",
        "routes": routes,
        "road_accessibility": accessibility,
        "exposed_infrastructure": {
            "hospitals": summary["categories"]["hospitals"],
            "schools": summary["categories"]["schools"],
            "bridges": summary["categories"]["bridges"],
            "shelters": summary["categories"]["shelters"],
        },
        "scenario": summary["scenario"],
        "provenance": summary["provenance"],
    }


def resource_priorities(city_id: str, job_id: Optional[str] = None) -> dict:
    summary = region_impact(city_id, job_id)
    hospitals = summary["categories"]["hospitals"]
    from floodlens.application.demo_fixtures import demo_fixtures_enabled, demo_resource_inventory

    inventory = {
        "rescue_boats": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "rescue_workers": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "medical_teams": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "pumps": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "food": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "water": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
        "shelter_capacity": {"kind": "OBSERVED RESOURCE INVENTORY", "status": "UNAVAILABLE", "value": None},
    }
    if demo_fixtures_enabled():
        inventory = demo_resource_inventory()
    priorities = []
    if hospitals["affected"] is None:
        priorities.append(
            {
                "priority": "UNKNOWN",
                "what": "Hospital resource planning",
                "why": "Hospital flood exposure has not been computed.",
                "evidence": "No attached flood raster or no evaluated hospital points.",
                "limitations": "No observed inventory. Do not treat this as an official allocation.",
                "data_status": "NOT_COMPUTED",
            }
        )
    else:
        n = hospitals["affected"]
        priorities.append(
            {
                "priority": "HIGH" if n >= 1 else "LOW",
                "what": "Hospital planning priority",
                "why": (
                    f"{n} hospitals are currently classified as exposed by the available spatial impact calculation."
                    if n >= 1
                    else "0 hospitals were classified as exposed by the available spatial impact calculation."
                ),
                "evidence": {
                    "hospitals_total": hospitals["total"],
                    "hospitals_exposed": n,
                    "computation": hospitals["computation"],
                    "scenario_job_id": summary["scenario"].get("job_id"),
                },
                "limitations": (
                    "Road accessibility could not be computed. Observed rescue/medical inventories are UNAVAILABLE. "
                    "Planning support only."
                ),
                "data_status": hospitals["status"],
            }
        )
    pop = summary["categories"]["population"]
    if pop["affected"] is None:
        priorities.append(
            {
                "priority": "UNKNOWN",
                "what": "Population-weighted resource allocation",
                "why": "Population exposure is UNAVAILABLE.",
                "evidence": pop["reason"],
                "limitations": "Do not infer population from OSM building counts.",
                "data_status": "UNAVAILABLE",
            }
        )
    return {
        "city_id": city_id,
        "inventory": inventory,
        "planning_estimates": {
            "status": "UNAVAILABLE",
            "reason": "No documented planning-estimate model. Inventories are not fabricated.",
        },
        "priorities": priorities,
        "safety": SAFETY,
        "scenario": summary["scenario"],
        "provenance": summary["provenance"],
    }
