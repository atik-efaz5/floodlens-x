"""Versioned /api/v1 platform routes. Existing /api/* remains for compatibility."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from floodlens.application.alerts import (
    AlertError,
    acknowledge_alert,
    alert_history,
    create_alert,
    evaluate_alerts,
    evaluate_alerts_detailed,
    list_alerts,
    metric_catalog,
)
from floodlens.application.assistant import chat as assistant_chat
from floodlens.application.auth import (
    ANONYMOUS_PERMISSIONS,
    decode_demo_token,
    encode_demo_token,
    has_permission,
    identity_from_authorization,
    parse_bearer,
)
from floodlens.application.errors import api_error
from floodlens.application.catalog import data_source_catalog, layer_catalog
from floodlens.application.celery_app import enqueue_or_celery
from floodlens.application.command import command_snapshot
from floodlens.application.data_contracts import envelope, public_source_ref
from floodlens.application.forecast import HeuristicForecastProvider, forecast_for_city
from floodlens.application.impact import assess_impact
from floodlens.application.impact_workspace import (
    evacuation_assessment,
    infrastructure_impact,
    region_impact,
    resource_priorities,
    shelter_assessments,
)
from floodlens.application.ingest import (
    fetch_open_meteo_precipitation,
    ingest_dem_metadata,
    ingest_osm_assets,
)
from floodlens.application.jobs import job_public_view, list_jobs, queue_job, run_job
from floodlens.application.monitoring import health, model_catalog, model_performance_center, readiness
from floodlens.application.osm_ingest import ingest_osm
from floodlens.application.platform_store import get_platform_store
from floodlens.application.reports import (
    generate_region_report,
    get_report,
    get_share,
    list_reports,
    report_csv,
    report_pdf,
    revoke_share,
    share_report,
)
from floodlens.application.repository import get_repository
from floodlens.application.research_diagnostics import (
    long_term_stability,
    run_lake_at_rest,
    run_parabolic_bowl,
)
from floodlens.application.research_center import (
    ai_experiment_center,
    diagnostic_inventory,
    generate_research_report,
    get_research_experiment,
    list_research_experiments,
    physics_vs_ai_status,
    research_overview,
    run_suite,
)
from floodlens.application.risk import risk_for_city
from floodlens.application.scenario_workspace import (
    causal_chain,
    compare_scenario_jobs,
    difference_map,
    scenario_baseline,
    scenario_capabilities,
    scenario_history,
    scenario_workspace,
)
from floodlens.application.rivers import (
    list_rivers,
    river_graph,
    river_observations,
    river_overview,
    river_segment_details,
    river_status,
    search_rivers,
    segment_neighbors,
)
from floodlens.application.city_data import create_city_registry
from floodlens.application.terrain import ingest_terrain

router = APIRouter(prefix="/api/v1")
_cities = create_city_registry()


def _role(authorization: Optional[str]) -> str:
    return decode_demo_token(authorization)


def _require(authorization: Optional[str], permission: str) -> str:
    """401 if unauthenticated on a non-public permission; 403 if the role lacks it."""
    role, status = parse_bearer(authorization)
    if status == "invalid":
        api_error(401, "UNAUTHORIZED", "Valid demo.<role> bearer token required")
    if status == "missing":
        if permission not in ANONYMOUS_PERMISSIONS:
            api_error(401, "UNAUTHORIZED", "Authentication required")
        role = "general"
    assert role is not None
    if not has_permission(role, permission):
        api_error(403, "FORBIDDEN", "Insufficient permission", permission=permission)
    return role


class LoginPayload(BaseModel):
    role: str = "general"


class JobPayload(BaseModel):
    kind: str = "simulation"
    city_id: str = "dhaka"
    nx: int = Field(default=16, ge=5, le=80)
    ny: int = Field(default=16, ge=5, le=80)
    rainfall_rate: float = 1.0e-5
    rainfall_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    duration_seconds: float = 0.5
    steps: int = 2
    river_level_delta_m: float = 0.0
    allow_synthetic_dem: bool = True


class ScenarioPayload(BaseModel):
    city_id: str = "dhaka"
    name: Optional[str] = None
    baseline_id: Optional[str] = None
    rainfall_multiplier: float = Field(default=1.3, ge=0.0, le=10.0)
    river_level_delta_m: float = 0.0
    nx: int = Field(default=12, ge=5, le=80)
    ny: int = Field(default=12, ge=5, le=80)
    duration_seconds: float = 0.3
    steps: int = 1
    allow_synthetic_dem: bool = True
    horizon_hours: Optional[int] = 24


class AiForecastPayload(BaseModel):
    city_id: str = "dhaka"


class ChatPayload(BaseModel):
    message: str
    city_id: str = "dhaka"
    river_id: str = "buriganga"
    context: Optional[dict] = None
    baseline_id: Optional[str] = None
    scenario_id: Optional[str] = None
    job_id: Optional[str] = None


class AlertPayload(BaseModel):
    city_id: str
    condition: str = "flood_probability"
    metric: Optional[str] = None
    threshold: float | str | None = None
    operator: str = "gte"
    channel: str = "in-app"
    location_id: Optional[str] = None
    kind: str = "personal"
    user_id: Optional[str] = None


class PlacePayload(BaseModel):
    label: str
    city_id: str
    lon: float
    lat: float
    user_id: str = "demo-user"
    location_type: str = "coordinate"
    river_id: Optional[str] = None
    zoom: Optional[float] = None
    layers: Optional[list] = None


class LocationPayload(BaseModel):
    name: str
    location_type: str = "city"
    city_id: Optional[str] = None
    river_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zoom: Optional[float] = None
    layers: Optional[list] = None
    alert_configuration: Optional[dict] = None


class LocationUpdatePayload(BaseModel):
    name: Optional[str] = None
    river_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zoom: Optional[float] = None
    layers: Optional[list] = None
    alert_configuration: Optional[dict] = None


class ShareCreatePayload(BaseModel):
    visibility: str = "private"
    map_state: Optional[dict] = None


class ReportCreatePayload(BaseModel):
    map_state: Optional[dict] = None


class ResearchRunPayload(BaseModel):
    suite: str
    steps: Optional[int] = None
    amplitude: Optional[float] = None
    i: Optional[int] = None
    j: Optional[int] = None
    direction: str = "x"


class ImpactPayload(BaseModel):
    city_id: str
    job_id: Optional[str] = None


class ComparePayload(BaseModel):
    job_ids: list[str]


@router.post("/auth/login")
def login(payload: LoginPayload) -> dict:
    try:
        token = encode_demo_token(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"token": token, "role": payload.role, "idp": "demo"}


@router.get("/catalog/layers")
def get_layers(city_id: str = "dhaka") -> dict:
    try:
        city = _cities.get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="city not found") from exc
    return layer_catalog(city_id, city.bounds.to_dict())


@router.get("/data-sources")
def get_data_sources(city_id: str = "dhaka") -> dict:
    return data_source_catalog(city_id)


def _parse_bbox(bbox: Optional[str]) -> Optional[tuple]:
    if not bbox:
        return None
    try:
        parts = [float(p.strip()) for p in bbox.split(",")]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north") from exc
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north")
    return tuple(parts)


@router.get("/infrastructure")
def get_infrastructure(
    city_id: Optional[str] = None,
    type: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    repo = get_repository()
    records = repo.list_infrastructure(
        city_id=city_id,
        asset_type=type,
        bbox=_parse_bbox(bbox),
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )
    features = [r.to_geojson_feature() for r in records]
    features = [f for f in features if f]
    fallback = any(r.data_status == "DEMO" for r in records)
    return {
        "type": "FeatureCollection",
        "features": features,
        "provenance": envelope(
            data_status="DEMO" if fallback else ("REAL" if features else "UNAVAILABLE"),
            provider="openstreetmap",
            dataset="infrastructure",
            freshness="SNAPSHOT",
            fallback_used=fallback,
            simulated=fallback,
        ),
        "fallback_used": fallback,
        "limit": min(limit, 500),
        "offset": offset,
    }


@router.get("/infrastructure/{record_id}")
def get_infrastructure_one(record_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    record = get_repository().get_infrastructure(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="infrastructure not found")
    return {"data": record.to_dict(), "feature": record.to_geojson_feature()}


@router.get("/rivers")
def get_rivers(
    city_id: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 80,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets(city_id or "dhaka")
    return list_rivers(city_id, bbox=_parse_bbox(bbox), limit=limit)


@router.get("/rivers/search")
def get_rivers_search(
    q: str,
    city_id: Optional[str] = None,
    limit: int = 20,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets(city_id or "dhaka")
    try:
        return search_rivers(q, city_id=city_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/observations")
def get_observations(
    city_id: Optional[str] = None,
    variable: str = "precipitation_mm",
    kind: Optional[str] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    repo = get_repository()
    overlay_id = None
    if variable in {"precipitation_mm", "rainfall", "precipitation"}:
        from floodlens.application.demo_fixtures import demo_fixtures_enabled, ensure_demo_rainfall

        if demo_fixtures_enabled() and city_id:
            overlay_id = ensure_demo_rainfall(city_id).get("overlay_artifact_id")
        rows = [r.to_dict() for r in repo.list_rainfall(city_id, kind)]
    else:
        rows = []
    if from_:
        rows = [r for r in rows if r.get("observed_at", "") >= from_]
    if to:
        rows = [r for r in rows if r.get("observed_at", "") <= to]
    fallback = any(r.get("data_status") == "DEMO" for r in rows)
    return {
        "data": rows,
        "variable": variable,
        "kind": kind,
        "provenance": envelope(
            data_status="DEMO" if fallback else ("REAL" if rows else "UNAVAILABLE"),
            provider="Open-Meteo" if rows else "none",
            dataset=variable,
            freshness="SNAPSHOT" if fallback else ("RECENT" if rows else "UNAVAILABLE"),
            fallback_used=fallback,
            simulated=fallback,
        ),
        "fallback_used": fallback,
        "overlay_artifact_id": overlay_id,
    }


@router.get("/terrain")
def get_terrain(city_id: str = "dhaka") -> dict:
    try:
        city = _cities.get_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="city not found") from exc
    dataset = get_repository().get_terrain(city_id)
    if dataset is None:
        payload = ingest_terrain(city_id, city.bounds.to_dict())
        if payload.get("dataset"):
            payload = dict(payload)
            ds = dict(payload["dataset"])
            ds["uri"] = public_source_ref(ds.get("uri")) or ""
            payload["dataset"] = ds
        return payload
    public = dataset.to_dict()
    public["uri"] = public_source_ref(public.get("uri")) or ""
    payload = {
        "city_id": city_id,
        "dataset": public,
        "available": dataset.data_status in {"REAL", "DEMO"},
        "provenance": envelope(
            data_status=dataset.data_status,  # type: ignore[arg-type]
            provider=dataset.source,
            dataset="terrain",
            freshness="SNAPSHOT" if dataset.data_status == "DEMO" else "STATIC",
            simulated=dataset.data_status == "DEMO",
        ),
    }
    if dataset.data_status == "DEMO":
        payload["overlay_artifact_id"] = f"demo-terrain-hillshade-{city_id}"
        payload["reason"] = "DEMO hillshade preview. Elevations are not a GeoTIFF DEM and are not passed to the solver."
    return payload


@router.get("/regions")
def get_regions() -> dict:
    features = []
    for city in _cities.list_cities():
        b = city.bounds
        ring = [
            [b.west, b.south],
            [b.east, b.south],
            [b.east, b.north],
            [b.west, b.north],
            [b.west, b.south],
        ]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "city_id": city.city_id,
                    "name": city.name,
                    "center_lon": city.center_lon,
                    "center_lat": city.center_lat,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "data": [
            {"city_id": c.city_id, "name": c.name, "bounds": c.bounds.to_dict()}
            for c in _cities.list_cities()
        ],
        "provenance": envelope(
            data_status="REAL",
            provider="city-registry",
            dataset="regions",
            freshness="STATIC",
        ),
        "fallback_used": False,
    }


@router.get("/regions/{city_id}")
def get_region_geometry(city_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    try:
        city = _cities.get_city(city_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error_code": "REGION_NOT_FOUND", "id": city_id})
    if city is None:
        raise HTTPException(status_code=404, detail={"error_code": "REGION_NOT_FOUND", "id": city_id})
    b = city.bounds
    ring = [
        [b.west, b.south],
        [b.east, b.south],
        [b.east, b.north],
        [b.west, b.north],
        [b.west, b.south],
    ]
    return {
        "city_id": city.city_id,
        "name": city.name,
        "region": city.region,
        "bounds": b.to_dict(),
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "note": "Study-region rectangle from the city registry. Not an administrative boundary.",
        "provenance": envelope(
            data_status="REAL",
            provider="city-registry",
            dataset="region-geometry",
            freshness="STATIC",
        ),
        "fallback_used": False,
    }


@router.get("/terrain/window")
def get_terrain_window(
    city_id: str = "dhaka",
    west: Optional[float] = None,
    south: Optional[float] = None,
    east: Optional[float] = None,
    north: Optional[float] = None,
) -> dict:
    from floodlens.application.terrain_service import get_window

    bounds = None
    if None not in (west, south, east, north):
        bounds = {"west": west, "south": south, "east": east, "north": north}
    result = get_window(city_id, bounds=bounds)
    if result.get("elevation") is not None:
        result = dict(result)
        result["elevation"] = None
        result["shape"] = result.get("shape")
        result["note"] = "Elevation array omitted from JSON; use physics jobs for resampled grids."
    return result


@router.get("/artifacts")
def list_artifacts() -> dict:
    from floodlens.application.artifact_store import public_summary

    rows = []
    for artifact_id in get_platform_store().artifacts:
        summary = public_summary(artifact_id)
        if summary and summary.get("kind") == "depth_snapshot":
            rows.append(summary)
    return {
        "data": rows,
        "provenance": envelope(
            data_status="SIMULATED" if rows else "UNAVAILABLE",
            provider="artifact-store",
            dataset="depth",
            freshness="SNAPSHOT",
            simulated=True,
        ),
        "fallback_used": False,
    }


@router.get("/scenarios/capabilities")
def get_scenario_capabilities(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    return scenario_capabilities()


@router.get("/scenarios/baseline")
def get_scenario_baseline(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    try:
        return scenario_baseline(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "REGION_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/scenarios/history")
def get_scenario_history(
    city_id: str = "dhaka",
    limit: int = Query(default=50, ge=1, le=50),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    try:
        return scenario_history(city_id, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "REGION_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/scenarios/causal-chain")
def get_scenario_causal_chain(
    city_id: str = "dhaka",
    job_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    return causal_chain(city_id, job_id)


@router.get("/scenarios/difference")
def get_scenario_difference(
    baseline_job: str,
    scenario_job: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    try:
        return difference_map(baseline_job, scenario_job)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/scenarios/workspace")
def get_scenario_workspace(
    city_id: str = "dhaka",
    baseline_job: Optional[str] = None,
    scenario_job: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    try:
        return scenario_workspace(city_id, baseline_job, scenario_job)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "REGION_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/scenarios")
def get_scenarios(city_id: Optional[str] = None, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    rows = [s.to_dict() for s in get_repository().list_scenarios(city_id)]
    for row in rows:
        row["river_level_applied_to_solver"] = False
        row["river_level_note"] = (
            "River-level scenario parameter recorded; physical river-boundary coupling is not enabled."
        )
    return {
        "data": rows,
        "provenance": envelope(
            data_status="SIMULATED" if rows else "UNAVAILABLE",
            provider="scenario-service",
            dataset="scenarios",
            freshness="SNAPSHOT",
            simulated=True,
        ),
        "fallback_used": False,
    }


@router.get("/rainfall")
def get_rainfall(
    city_id: str = "dhaka",
    kind: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.rainfall_service import get_rainfall_timeseries

    return get_rainfall_timeseries(city_id, kind)


@router.get("/rivers/{river_id}/state")
def get_river_state(river_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    from floodlens.application.river_state import river_state

    try:
        return river_state(river_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RIVER_NOT_FOUND", "id": str(exc)}) from exc


@router.post("/forecast/physics")
def post_physics_forecast(
    payload: JobPayload,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "jobs.write")
    body = payload.model_dump()
    city_id = body.pop("city_id")
    body.pop("kind", None)
    job = queue_job("physics_forecast", city_id, body)
    background_tasks.add_task(run_job, job["id"])
    return job_public_view(job)


@router.post("/forecast/ai")
def post_ai_forecast(
    payload: AiForecastPayload,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "jobs.write")
    job = queue_job("ai_forecast", payload.city_id, {})
    background_tasks.add_task(run_job, job["id"])
    return job_public_view(job)


@router.get("/forecast/ai/{job_id}")
def get_ai_forecast_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "forecast.read")
    store = get_platform_store()
    try:
        return job_public_view(store.get_job(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@router.post("/forecast/ai-spatial")
def post_ai_spatial_forecast(
    payload: AiForecastPayload,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "jobs.write")
    job = queue_job("ai_spatial_forecast", payload.city_id, {})
    background_tasks.add_task(run_job, job["id"])
    return job_public_view(job)


@router.get("/forecast/ai-spatial/{job_id}")
def get_ai_spatial_forecast_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "forecast.read")
    store = get_platform_store()
    try:
        return job_public_view(store.get_job(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@router.get("/flood-states")
def get_flood_states(city_id: str = "dhaka", horizon_hours: Optional[int] = None) -> dict:
    states = get_repository().list_flood_states(city_id, horizon_hours)
    return {
        "data": [s.to_dict() for s in states],
        "provenance": envelope(
            data_status=states[-1].data_status if states else "UNAVAILABLE",
            provider="PHYSICS-BASELINE-v0.1",
            dataset="flood-state",
            freshness="SNAPSHOT",
            simulated=True,
        ),
        "fallback_used": False,
    }


@router.get("/artifacts/{artifact_id}/overlay.png")
def get_overlay_png(artifact_id: str):
    from floodlens.application.artifact_store import overlay_png_bytes

    png = overlay_png_bytes(artifact_id)
    if png is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return Response(content=png, media_type="image/png")


@router.get("/artifacts/{artifact_id}/summary")
def get_artifact_summary(artifact_id: str) -> dict:
    from floodlens.application.artifact_store import public_summary

    summary = public_summary(artifact_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return summary


@router.post("/scenarios")
def post_scenario(
    payload: ScenarioPayload,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "jobs.write")
    body = payload.model_dump()
    city_id = body.pop("city_id")
    if not body.get("name"):
        multiplier = float(body.get("rainfall_multiplier") or 1.0)
        percent = int(round((multiplier - 1.0) * 100))
        body["name"] = "Baseline ×1.0" if percent == 0 else f"Rainfall {percent:+d}%"
    job = queue_job("scenario", city_id, body)
    background_tasks.add_task(run_job, job["id"])
    return job_public_view(job)


@router.get("/status")
def get_status(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    role = _require(authorization, "risk.read")
    ingest_osm_assets(city_id)
    payload = {
        "city_id": city_id,
        "risk": risk_for_city(city_id),
        "forecast": forecast_for_city(city_id),
        "layers": layer_catalog(city_id, _cities.get_city(city_id).bounds.to_dict()),
    }
    if has_permission(role, "command.read"):
        payload["command"] = command_snapshot(city_id)
    else:
        payload["command"] = {
            "status": "UNAVAILABLE",
            "reason": "command.read required",
            "current_risk": None,
            "population_exposed": None,
            "hospitals_at_risk": None,
            "alerts_active": None,
            "latest_job": None,
            "disclaimer": "Command KPIs are restricted. Null operational values are never fabricated.",
        }
    return payload


@router.get("/forecast")
def get_forecast(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "forecast.read")
    return forecast_for_city(city_id)


@router.get("/risk")
def get_risk(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "risk.read")
    return risk_for_city(city_id)


@router.get("/rivers/{river_id}")
def get_river(river_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    try:
        return river_status(river_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RIVER_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/rivers/{river_id}/graph")
def get_river_graph(river_id: str) -> dict:
    ingest_osm_assets("dhaka")
    try:
        return river_graph(river_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RIVER_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/rivers/{river_id}/observations")
def get_river_observations(river_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    try:
        return river_observations(river_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RIVER_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/rivers/{river_id}/overview")
def get_river_overview(river_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    try:
        return river_overview(river_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RIVER_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/rivers/{river_id}/segments/{segment_id}")
def get_river_segment(
    river_id: str,
    segment_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    try:
        return river_segment_details(river_id, segment_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RIVER_SEGMENT_NOT_FOUND", "id": str(exc)},
        ) from exc


@router.get("/rivers/{river_id}/segments/{segment_id}/neighbors")
def get_river_segment_neighbors(
    river_id: str,
    segment_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    ingest_osm_assets("dhaka")
    try:
        return segment_neighbors(river_id, segment_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RIVER_SEGMENT_NOT_FOUND", "id": str(exc)},
        ) from exc


@router.post("/ingest/osm")
def post_ingest_osm(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.write")
    return ingest_osm(city_id)


@router.post("/ingest/rainfall")
def post_ingest_rainfall(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.write")
    return fetch_open_meteo_precipitation(city_id)


@router.post("/ingest/dem")
def post_ingest_dem(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.write")
    city = _cities.get_city(city_id)
    if city is None:
        api_error(404, "CITY_NOT_FOUND", "city not found")
    return ingest_dem_metadata(city_id, city.bounds.to_dict())


@router.post("/jobs")
def post_job(
    payload: JobPayload,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "jobs.write")
    body = payload.model_dump()
    kind = body.pop("kind")
    city_id = body.pop("city_id")
    if kind in {"physics_forecast", "scenario", "ai_forecast", "ai_spatial_forecast"}:
        job = queue_job(kind, city_id, body)
        background_tasks.add_task(run_job, job["id"])
        return job_public_view(job)
    return enqueue_or_celery(kind, city_id, body)


@router.get("/jobs")
def get_jobs(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.read")
    return {"jobs": list_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.read")
    store = get_platform_store()
    try:
        return job_public_view(store.get_job(job_id))
    except KeyError as exc:
        api_error(404, "JOB_NOT_FOUND", "job not found")


@router.post("/jobs/{job_id}/run")
def post_run_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.write")
    try:
        return run_job(job_id)
    except KeyError as exc:
        api_error(404, "JOB_NOT_FOUND", "job not found")


@router.get("/impact")
def get_impact(
    city_id: str,
    job_id: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 200,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "impact.read")
    try:
        return region_impact(city_id, job_id=job_id, bbox=_parse_bbox(bbox), limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "IMPACT_CONTEXT_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/impact/infrastructure")
def get_impact_infrastructure(
    city_id: str,
    job_id: Optional[str] = None,
    category: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 200,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "impact.read")
    try:
        return infrastructure_impact(
            city_id,
            job_id=job_id,
            category=category,
            bbox=_parse_bbox(bbox),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "IMPACT_CONTEXT_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/impact/shelters")
def get_impact_shelters(
    city_id: str,
    job_id: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 200,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "impact.read")
    try:
        return shelter_assessments(city_id, job_id=job_id, bbox=_parse_bbox(bbox), limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "IMPACT_CONTEXT_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/impact/evacuation")
def get_impact_evacuation(
    city_id: str,
    job_id: Optional[str] = None,
    bbox: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "impact.read")
    try:
        return evacuation_assessment(city_id, job_id=job_id, bbox=_parse_bbox(bbox))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "IMPACT_CONTEXT_NOT_FOUND", "id": str(exc)}) from exc


@router.get("/impact/resources")
def get_impact_resources(
    city_id: str,
    job_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "resources.read")
    try:
        return resource_priorities(city_id, job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "IMPACT_CONTEXT_NOT_FOUND", "id": str(exc)}) from exc


@router.post("/impact/assess")
def post_impact(payload: ImpactPayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "impact.read")
    ingest_osm_assets(payload.city_id)
    city = _cities.get_city(payload.city_id)
    store = get_platform_store()
    depth = None
    grid = None
    if payload.job_id:
        job = store.jobs.get(payload.job_id)
        if not job or not job.get("result"):
            raise HTTPException(status_code=404, detail="job result not available")
        from floodlens.application.artifact_store import get_artifact, get_depth

        artifact_id = job["result"]["artifact_id"]
        depth = get_depth(artifact_id)
        artifact = get_artifact(artifact_id) or {}
        if depth is not None:
            grid = {
                "nx": artifact.get("nx") or depth.shape[1],
                "ny": artifact.get("ny") or depth.shape[0],
                "dx": (city.bounds.east - city.bounds.west) / (artifact.get("nx") or depth.shape[1]),
                "dy": (city.bounds.north - city.bounds.south) / (artifact.get("ny") or depth.shape[0]),
                "origin_x": city.bounds.west,
                "origin_y": city.bounds.south,
                "crs": "EPSG:4326",
            }
    if depth is None:
        return {
            "city_id": payload.city_id,
            "available": False,
            "reason": "No physics flood raster is attached. Run a simulation job first.",
            "flooded_counts": {},
        }
    return assess_impact(payload.city_id, city.bounds.to_dict(), grid, depth)


@router.post("/scenarios/compare")
def post_compare(payload: ComparePayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "jobs.read")
    return compare_scenario_jobs(payload.job_ids)


@router.post("/assistant/chat")
def post_chat(payload: ChatPayload, authorization: Optional[str] = Header(default=None)) -> dict:
    role = _require(authorization, "assistant.chat")
    ingest_osm_assets(payload.city_id)
    context = dict(payload.context or {})
    context.setdefault("city_id", payload.city_id)
    context.setdefault("selected_region", payload.city_id)
    context.setdefault("river_id", payload.river_id)
    if payload.river_id:
        context.setdefault("selected_river", payload.river_id)
    if payload.baseline_id:
        context["baseline_id"] = payload.baseline_id
    if payload.scenario_id:
        context["scenario_id"] = payload.scenario_id
    if payload.job_id:
        context["selected_job"] = payload.job_id
    context.pop("role", None)
    return assistant_chat(payload.message, context, role=role)


@router.get("/assistant/tools")
def get_assistant_tools(authorization: Optional[str] = Header(default=None)) -> dict:
    from floodlens.application.assistant import tool_catalog

    role = _require(authorization, "assistant.chat")
    return {"tools": tool_catalog(role), "role": role}


@router.get("/research/inventory")
def get_research_inventory(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    return diagnostic_inventory()


@router.get("/research/overview")
def get_research_overview(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    return research_overview()


@router.get("/research/ai")
def get_research_ai(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    return ai_experiment_center()


@router.get("/research/physics-vs-ai")
def get_physics_vs_ai(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    return physics_vs_ai_status()


@router.get("/research/experiments")
def get_research_experiments(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    return list_research_experiments()


@router.get("/research/experiments/{experiment_id}")
def get_research_experiment_by_id(experiment_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    try:
        return get_research_experiment(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="experiment not found") from exc


@router.post("/research/run")
def post_research_run(payload: ResearchRunPayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    from floodlens.application.rate_limit import RateLimitExceeded

    kwargs = {}
    suite = payload.suite
    key = suite.strip().lower().replace("-", "_")
    try:
        if key in {"long_term", "long_term_stability"}:
            kwargs["steps"] = payload.steps or 50
        elif key in {"lake_at_rest", "parabolic_bowl", "conservation", "spectral"}:
            if payload.steps is not None:
                kwargs["steps"] = payload.steps
        elif key == "perturbation":
            if payload.amplitude is not None:
                kwargs["amplitude"] = payload.amplitude
            if payload.steps is not None:
                kwargs["steps"] = payload.steps
        elif key == "interface_balance":
            kwargs["i"] = payload.i
            kwargs["j"] = payload.j
            kwargs["direction"] = payload.direction
        elif key == "jacobian":
            kwargs["i"] = payload.i
            kwargs["j"] = payload.j
        return run_suite(suite, identity_from_authorization(authorization), **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown suite") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.post("/research/reports")
def post_research_report(
    experiment_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "research.read")
    from floodlens.application.rate_limit import RateLimitExceeded

    try:
        return generate_research_report(experiment_id, created_by=identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="experiment not found") from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.get("/research/diagnostics/{suite}")
def get_diagnostics(
    suite: str,
    steps: Optional[int] = None,
    amplitude: Optional[float] = None,
    i: Optional[int] = Query(default=None),
    j: Optional[int] = Query(default=None),
    direction: str = "x",
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "research.read")
    from floodlens.application.rate_limit import RateLimitExceeded

    key = suite.strip().lower().replace("-", "_")
    kwargs = {}
    if key in {"long_term", "long_term_stability"}:
        kwargs["steps"] = steps or 20
    elif key == "perturbation" and amplitude is not None:
        kwargs["amplitude"] = amplitude
    elif key == "interface_balance":
        kwargs["i"] = i
        kwargs["j"] = j
        kwargs["direction"] = direction
    elif key == "jacobian":
        kwargs["i"] = i
        kwargs["j"] = j
    try:
        return run_suite(suite, identity_from_authorization(authorization), **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown suite") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.post("/reports")
def post_report(
    city_id: str = "dhaka",
    baseline_job: Optional[str] = None,
    scenario_job: Optional[str] = None,
    event_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    payload: Optional[ReportCreatePayload] = Body(default=None),
) -> dict:
    _require(authorization, "reports.write")
    from floodlens.application.rate_limit import RateLimitExceeded

    owner = identity_from_authorization(authorization)
    map_state = payload.map_state if payload else None
    try:
        return generate_region_report(
            city_id,
            baseline_job_id=baseline_job,
            scenario_job_id=scenario_job,
            created_by=owner,
            map_state=map_state,
            event_id=event_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT", "action": exc.action}) from exc


@router.get("/reports")
def get_reports(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "reports.read")
    return list_reports(identity_from_authorization(authorization))


@router.get("/reports/{report_id}")
def get_report_by_id(
    report_id: str,
    fmt: Optional[str] = Query(default=None, alias="format"),
    authorization: Optional[str] = Header(default=None),
):
    _require(authorization, "reports.read")
    from floodlens.application.rate_limit import RateLimitExceeded

    owner = identity_from_authorization(authorization)
    try:
        report = get_report(report_id, owner=owner)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc
    if fmt in {None, "json"}:
        return report
    try:
        check = __import__("floodlens.application.rate_limit", fromlist=["check_rate"]).check_rate
        check(owner, "export")
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc
    if fmt == "csv":
        return Response(content=report_csv(report), media_type="text/csv")
    if fmt == "pdf":
        return Response(content=report_pdf(report), media_type="application/pdf")
    raise HTTPException(status_code=400, detail="format must be json, csv, or pdf")


@router.post("/shares/{report_id}")
def post_share(
    report_id: str,
    visibility: str = "private",
    authorization: Optional[str] = Header(default=None),
) -> dict:
    from floodlens.application.rate_limit import RateLimitExceeded

    _require(authorization, "shares.write")
    owner = identity_from_authorization(authorization)
    try:
        return share_report(report_id, owner=owner, visibility=visibility)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"error_code": "FORBIDDEN", "message": "FORBIDDEN"}) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.get("/shares/{share_id}")
def get_share_by_id(share_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    requester = identity_from_authorization(authorization) if authorization else None
    payload = get_share(share_id, requester=requester, authenticated=bool(authorization))
    if payload.get("available") is False:
        raise HTTPException(status_code=404, detail={"error_code": "SHARE_UNAVAILABLE", "reason": payload.get("reason")})
    return payload


@router.post("/shares/{share_id}/revoke")
def post_share_revoke(share_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "shares.write")
    try:
        return revoke_share(share_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="share not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc


@router.get("/alerts/metrics")
def get_alert_metrics(
    city_id: str = "dhaka",
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "alerts.read")
    from floodlens.application.alerts import read_metric

    catalog = metric_catalog()
    for row in catalog["metrics"]:
        reading = read_metric(city_id, row["metric"])
        row["available"] = bool(reading.get("available"))
        row["current_status"] = reading.get("status") or "UNAVAILABLE"
        if not reading.get("available"):
            row["reason"] = reading.get("reason") or row.get("reason") or "METRIC UNAVAILABLE"
    return catalog


@router.post("/alerts")
def post_alert(payload: AlertPayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "alerts.write")
    from floodlens.application.rate_limit import RateLimitExceeded

    if payload.threshold is None:
        raise HTTPException(status_code=400, detail={"error_code": "MALFORMED_THRESHOLD", "reason": "threshold required"})
    try:
        return create_alert(
            owner=identity_from_authorization(authorization),
            role=_role(authorization),
            city_id=payload.city_id,
            condition=payload.metric or payload.condition,
            threshold=payload.threshold,
            channel=payload.channel,
            operator=payload.operator,
            location_id=payload.location_id,
            kind=payload.kind,
        )
    except AlertError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.code, "reason": exc.message, "metric_status": "UNAVAILABLE" if exc.code == "METRIC_UNAVAILABLE" else None},
        ) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.get("/alerts")
def get_alerts(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "alerts.read")
    return list_alerts(identity_from_authorization(authorization))


@router.get("/alerts/evaluate")
def get_alert_eval(
    city_id: str = "dhaka",
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "alerts.read")
    detailed = evaluate_alerts_detailed(city_id, owner=identity_from_authorization(authorization))
    return {"fired": detailed["fired"], "evaluations": detailed["evaluations"]}


@router.post("/alerts/{alert_id}/acknowledge")
def post_alert_ack(alert_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "alerts.write")
    try:
        return acknowledge_alert(alert_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@router.get("/alerts/{alert_id}/history")
def get_alert_history(alert_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "alerts.read")
    try:
        return alert_history(alert_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@router.post("/places")
def post_place(payload: PlacePayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.write")
    from floodlens.application.locations import LocationError, create_location
    from floodlens.application.rate_limit import RateLimitExceeded

    try:
        return create_location(
            owner=identity_from_authorization(authorization),
            name=payload.label,
            location_type=payload.location_type,
            city_id=payload.city_id,
            river_id=payload.river_id,
            latitude=payload.lat,
            longitude=payload.lon,
            zoom=payload.zoom,
            layers=payload.layers,
        )
    except LocationError as exc:
        raise HTTPException(status_code=400, detail={"error_code": exc.code, "reason": str(exc)}) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.get("/places")
def get_places(authorization: Optional[str] = Header(default=None)) -> dict:
    from floodlens.application.locations import list_locations

    if not authorization:
        return {"places": []}
    _require(authorization, "places.read")
    payload = list_locations(identity_from_authorization(authorization))
    return {"places": payload["locations"]}


@router.post("/locations")
def post_location(payload: LocationPayload, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.write")
    from floodlens.application.locations import LocationError, create_location
    from floodlens.application.rate_limit import RateLimitExceeded

    try:
        return create_location(
            owner=identity_from_authorization(authorization),
            name=payload.name,
            location_type=payload.location_type,
            city_id=payload.city_id,
            river_id=payload.river_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            zoom=payload.zoom,
            layers=payload.layers,
            alert_configuration=payload.alert_configuration,
        )
    except LocationError as exc:
        raise HTTPException(status_code=400, detail={"error_code": exc.code, "reason": str(exc)}) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error_code": "RATE_LIMIT"}) from exc


@router.get("/locations")
def get_locations(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.read")
    from floodlens.application.locations import list_locations, location_dashboard

    owner = identity_from_authorization(authorization)
    listed = list_locations(owner)
    dash = location_dashboard(owner)
    return {**listed, "cards": dash["cards"]}


@router.get("/locations/{location_id}")
def get_location_by_id(location_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.read")
    from floodlens.application.locations import get_location

    try:
        return get_location(location_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="location not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc


@router.get("/locations/{location_id}/restore")
def get_location_restore(location_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.read")
    from floodlens.application.locations import restore_context

    try:
        return restore_context(location_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="location not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc


@router.patch("/locations/{location_id}")
def patch_location(
    location_id: str,
    payload: LocationUpdatePayload,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "places.write")
    from floodlens.application.locations import update_location

    try:
        return update_location(location_id, identity_from_authorization(authorization), **payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="location not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc


@router.delete("/locations/{location_id}")
def delete_location_route(location_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "places.write")
    from floodlens.application.locations import delete_location

    try:
        return delete_location(location_id, identity_from_authorization(authorization))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="location not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc


@router.get("/command")
def get_command(city_id: str = "dhaka", authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "command.read")
    return command_snapshot(city_id)


@router.get("/research/compare")
def get_research_compare(
    baseline_job: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "research.read")
    from floodlens.ml.compare import COMPARISON_NOT_YET_COMPARABLE, PHYSICS_FOOTNOTE
    from floodlens.ml.registry import public_status
    from floodlens.ml.spatial.registry_spatial import public_spatial_status

    heuristic = HeuristicForecastProvider().forecast("dhaka")
    physics = None
    runtime = None
    if baseline_job:
        store = get_platform_store()
        job = store.jobs.get(baseline_job)
        if job and job.get("result"):
            physics = job["result"]
    return {
        "physics": {
            "status": "IMPLEMENTED" if physics else "NO_JOB",
            "max_depth_m": (physics or {}).get("max_depth_m"),
            "flood_fraction": (physics or {}).get("flood_fraction"),
            "validation_status": (physics or {}).get("validation_status"),
            "runtime": runtime,
            "footnote": PHYSICS_FOOTNOTE,
            "clock": "solver_seconds_not_meteorological_hours",
        },
        "heuristic": {
            "status": "IMPLEMENTED",
            "horizons": heuristic.get("horizons"),
            "model_kind": "HEURISTIC",
        },
        "ai": {
            "status": public_status(),
            "accuracy_claim": None,
            "label_kind": "MODELLED",
            "comparable_to_physics": False,
        },
        "ai_spatial": {
            "status": public_spatial_status(),
            "accuracy_claim": None,
            "label_kind": "OBSERVED",
            "horizon_hours": 192,
            "comparable_to_physics": False,
        },
        "ranking_claim": None,
        "comparable_to_physics": False,
        "comparison_status": "COMPARISON NOT YET COMPARABLE",
        "note": (
            "Mass error and SWE diagnostics stay on the research/diagnostics routes. "
            + PHYSICS_FOOTNOTE
            + " "
            + COMPARISON_NOT_YET_COMPARABLE
        ),
    }


@router.get("/historical-events")
def get_historical_events() -> dict:
    from floodlens.ml.dataset_builder import historical_events_from_catalog

    events = historical_events_from_catalog()
    return {
        "data": events,
        "provenance": envelope(
            data_status="UNAVAILABLE",
            provider="cems-rapid-mapping-catalog",
            dataset="events",
            freshness="UNAVAILABLE",
        ),
        "fallback_used": False,
        "note": (
            "Metadata catalog only. observed_flood_extent is null; polygons were not downloaded. "
            "Absence of an EMSR activation is not a dry label."
        ),
    }


@router.get("/history/events")
def get_history_events(
    year: Optional[int] = None,
    region: Optional[str] = None,
    flood_mechanism: Optional[str] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.historical_workspace import event_catalog

    return event_catalog(
        year=year,
        region=region,
        flood_mechanism=flood_mechanism,
        source=source,
        model=model,
        status=status,
    )


@router.get("/history/events/{event_id}")
def get_history_event(event_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.historical_workspace import event_detail

    try:
        return event_detail(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc


@router.get("/history/events/{event_id}/observations")
def get_history_observations(event_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.historical_workspace import event_observations

    try:
        return event_observations(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc


@router.get("/history/events/{event_id}/timeline")
def get_history_timeline(event_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    return get_history_observations(event_id, authorization=authorization)


@router.get("/history/events/{event_id}/predictions")
def get_history_predictions(event_id: str, authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.historical_workspace import discover_predictions

    try:
        return discover_predictions(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc


@router.get("/history/events/{event_id}/compare")
def get_history_compare(
    event_id: str,
    prediction_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "map.read")
    from floodlens.application.historical_workspace import compare_event

    try:
        return compare_event(event_id, prediction_id=prediction_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc


@router.post("/history/events/{event_id}/report")
def post_history_report(
    event_id: str,
    city_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require(authorization, "reports.write")
    from floodlens.application.historical_workspace import generate_historical_report

    try:
        return generate_historical_report(event_id, city_id=city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="historical event not found") from exc


@router.get("/health")
def get_health() -> dict:
    return health()


@router.get("/ready")
def get_ready() -> dict:
    return readiness()


@router.get("/models")
def get_models() -> dict:
    return model_catalog()


@router.get("/models/performance")
def get_model_performance() -> dict:
    return model_performance_center()


@router.get("/models/{model_id}")
def get_model(model_id: str) -> dict:
    from floodlens.application.historical_workspace import model_registry_payload

    registry = model_registry_payload()
    for row in registry["models"]:
        if row["id"] == model_id:
            return row
    raise HTTPException(status_code=404, detail="model not found")


@router.get("/experiments")
def get_experiments(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    from floodlens.ml.train import list_experiments

    return {"experiments": list_experiments(), "accuracy_claim": None}


@router.get("/metrics")
def get_metrics(authorization: Optional[str] = Header(default=None)) -> dict:
    _require(authorization, "research.read")
    from floodlens.ml.train import list_experiments

    experiments = list_experiments()
    latest = experiments[-1] if experiments else None
    return {
        "latest": latest,
        "accuracy_claim": None,
        "note": "Metrics are reported as AUPRC/Brier/BSS by split and horizon. Not accuracy.",
    }
