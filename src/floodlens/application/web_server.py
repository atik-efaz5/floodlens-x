"""FastAPI backend for FloodLens-X scenario execution and geospatial inspection."""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from floodlens.application.geospatial import (
    DEFAULT_VISUALIZATION_LAYERS,
    GridReference,
    ScenarioRunRequest,
    ScenarioRunResponse,
    ScenarioSession,
)
from floodlens.application.service import SimulationService
from floodlens.application.city_data import create_city_registry
from floodlens.application.comparison import (
    ComparisonEngine,
    ComparisonError,
    ComparisonRequest,
    ScenarioResultRecord,
    TemporalResultError,
)
from floodlens.application.scenario_results import (
    ScenarioResultStore,
    empty_result_record,
    velocity_from_state,
)
from floodlens.application.location_search import (
    LocationSearchService,
    parse_coordinate_query,
)
from floodlens.application.cell_inspection import CellInspectionService, InspectionError
from floodlens.application.api_v1 import router as v1_router
from floodlens.core.config import SimulationConfig
from floodlens.visualization.layer import VisualizationLayer

app = FastAPI(
    title="FloodLens-X API",
    description="Hydrodynamic flood simulation web backend",
    version="0.1.0",
)


def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "https://floodlens-x.vercel.app",
    ]
    extra = os.environ.get("FLOODLENS_CORS_ORIGINS", "")
    for part in extra.split(","):
        origin = part.strip()
        if origin and origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router)

_LOGGER = logging.getLogger("floodlens.api")


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    response = await call_next(request)
    auth = request.headers.get("authorization") or ""
    role = "anonymous"
    if auth.lower().startswith("bearer demo."):
        role = auth.split(".", 1)[-1].split()[0][:24]
    _LOGGER.info(
        "method=%s path=%s status=%s role=%s",
        request.method,
        request.url.path,
        response.status_code,
        role,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    _LOGGER.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": {"error_code": "INTERNAL", "message": "Internal server error"}},
    )

_session: Optional[ScenarioSession] = None
_city_registry = create_city_registry()
_result_store = ScenarioResultStore()
_comparison_engine = ComparisonEngine()
_location_search_service = LocationSearchService()
_cell_inspection_service = CellInspectionService(_result_store)


class ScenarioRunPayload(BaseModel):
    """HTTP request body for scenario execution."""

    nx: int = Field(default=50, ge=5, le=300)
    ny: int = Field(default=50, ge=5, le=300)
    rainfall_rate: float = Field(default=1.0e-5, ge=0.0)
    duration_seconds: float = Field(default=5.0, gt=0.0)
    scenario: str = Field(default="sunamganj")
    city_id: Optional[str] = None
    scenario_id: Optional[str] = None


class ComparisonPayload(BaseModel):
    """HTTP request body for read-only scenario comparison."""

    city_id: str
    scenario_a_id: str
    scenario_b_id: str
    layer: str = "depth"
    time: Optional[float] = None
    comparison_mode: str = "DIFFERENCE"


class TimeSeriesFrame(BaseModel):
    """Single time-step simulation output."""

    time: float
    depth_grid: List[List[float]]


def get_session() -> ScenarioSession:
    """Return the active scenario session, creating a default if needed."""
    global _session
    if _session is None:
        _session = ScenarioSession.default_sunamganj()
    return _session


def set_session(session: ScenarioSession) -> None:
    """Replace the active scenario session (primarily for tests)."""
    global _session
    _session = session


def get_result_store() -> ScenarioResultStore:
    return _result_store


def reset_result_store() -> None:
    _result_store.clear()


def get_location_search_service() -> LocationSearchService:
    return _location_search_service


def set_location_search_service(service: LocationSearchService) -> None:
    global _location_search_service
    _location_search_service = service


def get_cell_inspection_service() -> CellInspectionService:
    return _cell_inspection_service


def set_cell_inspection_service(service: CellInspectionService) -> None:
    global _cell_inspection_service
    _cell_inspection_service = service


def _grid_for_city(city, config) -> GridReference:
    return GridReference(
        nx=config.Nx,
        ny=config.Ny,
        dx=float(city.grid_metadata.dx) if city.grid_metadata else float(config.Lx / config.Nx),
        dy=float(city.grid_metadata.dy) if city.grid_metadata else float(config.Ly / config.Ny),
        origin_x=city.bounds.west,
        origin_y=city.bounds.south,
        crs=city.crs,
        cell_center_convention=(
            city.grid_metadata.cell_center_convention if city.grid_metadata else "cell_center"
        ),
        row_orientation=(
            city.grid_metadata.row_orientation if city.grid_metadata else "south_to_north"
        ),
    )


def _record_from_snapshots(
    session: ScenarioSession,
    city_id: str,
    scenario_id: str,
    name: str,
    flooded_area_km2: float,
    snapshots,
) -> ScenarioResultRecord:
    city = _city_registry.get_city(city_id)
    config = session.config
    grid = _grid_for_city(city, config)
    record = empty_result_record(
        scenario_id=scenario_id,
        city_id=city_id,
        name=name,
        grid=grid,
        bounds=city.bounds,
        crs=city.crs,
        h_dry_threshold=float(session.h_dry_threshold),
    )
    if snapshots:
        for snapshot in snapshots:
            record.add_snapshot(snapshot.time, snapshot.depth, snapshot.velocity)
    elif session.state is not None:
        h = np.asarray(session.state.h, dtype=np.float64)
        hu = np.asarray(session.state.U[:, :, 1], dtype=np.float64)
        hv = np.asarray(session.state.U[:, :, 2], dtype=np.float64)
        record.add_snapshot(
            float(session.state.time),
            h,
            velocity_from_state(h, hu, hv, session.h_dry_threshold),
        )
    record.flooded_area_km2 = flooded_area_km2
    return record


def _generate_synthetic_dem(nx: int, ny: int, lx: float, ly: float) -> np.ndarray:
    """Build a lightweight Sunamganj-like synthetic topography.

    Layout matches SimulationConfig: shape (ny, nx) == (Ny, Nx).
    """
    x = np.linspace(0, lx, nx)
    y = np.linspace(0, ly, ny)
    X, Y = np.meshgrid(x, y)

    z_regional = 30.0 * (1.0 - Y / ly) ** 1.5 + 2.0
    channel_center = lx * (0.5 + 0.15 * np.sin(2 * np.pi * Y / ly))
    channel_depth = 4.0 * np.exp(-((X - channel_center) ** 2) / (2 * (lx * 0.08) ** 2))
    z = np.maximum(1.0, z_regional - channel_depth)

    haor_bowl = 2.5 * np.exp(
        -((X - lx * 0.45) ** 2 + (Y - ly * 0.25) ** 2) / (2 * (lx * 0.15) ** 2)
    )
    return np.maximum(0.8, z - haor_bowl).astype(np.float64)


def run_scenario_simulation(request: ScenarioRunRequest) -> ScenarioRunResponse:
    """Execute a simulation and update the active scenario session with time-series tracking."""
    session = get_session()

    config = SimulationConfig(
        Nx=request.nx,
        Ny=request.ny,
        Lx=session.config.Lx,
        Ly=session.config.Ly,
        T_end=request.duration_seconds,
        CFL=session.config.CFL,
        manning_n=session.config.manning_n,
        h_dry_threshold=session.config.h_dry_threshold,
        boundary_condition=session.config.boundary_condition,
        name=f"{session.config.name}_{request.nx}x{request.ny}",
    )

    dem = _generate_synthetic_dem(request.nx, request.ny, config.Lx, config.Ly)
    service = SimulationService(config)
    result = service.run_scenario(
        dem=dem,
        rainfall_rate=request.rainfall_rate,
        steps=1,
        track_progress=False,
    )

    if not result.success or result.final_state is None:
        return ScenarioRunResponse(
            status="failed",
            success=False,
            max_depth_m=0.0,
            flooded_area_km2=0.0,
            simulation_time_s=0.0,
            nx=request.nx,
            ny=request.ny,
        )

    viz = VisualizationLayer(h_dry_threshold=config.h_dry_threshold)
    metrics = viz.compute_metrics(result.final_state, config)
    flooded_area_km2 = float(metrics["inundated_area"]) / 1e6
    max_depth_m = float(metrics["max_depth"])

    session.config = config
    session.state = result.final_state
    session.max_depth_map = result.final_state.h.copy()
    session.snapshots = result.snapshots
    session.time_series_frames = [
        {"time": snapshot.time, "depth_grid": snapshot.depth.tolist()}
        for snapshot in result.snapshots
    ]
    times = tuple(snapshot.time for snapshot in result.snapshots)
    session.update_metadata_time_range(request.duration_seconds)

    return ScenarioRunResponse(
        status="completed",
        success=True,
        max_depth_m=max_depth_m,
        flooded_area_km2=flooded_area_km2,
        simulation_time_s=float(result.final_state.time),
        nx=request.nx,
        ny=request.ny,
        available_times=times,
        start_time=times[0] if times else 0.0,
        end_time=times[-1] if times else 0.0,
    )


@app.get("/api/scenario/metadata")
def get_scenario_metadata() -> dict:
    """Return scenario bounds, center, CRS, time range, and visualization layers."""
    session = get_session()
    payload = session.metadata.to_dict()
    payload["visualization_layers"] = list(DEFAULT_VISUALIZATION_LAYERS)
    return payload


@app.post("/api/scenario/run")
def post_scenario_run(payload: ScenarioRunPayload) -> dict:
    """Run a rainfall scenario and return summary inundation metrics."""
    request = ScenarioRunRequest(
        nx=payload.nx,
        ny=payload.ny,
        rainfall_rate=payload.rainfall_rate,
        duration_seconds=payload.duration_seconds,
        scenario=payload.scenario,
    )
    try:
        response = run_scenario_simulation(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response.success and payload.scenario_id:
        session = get_session()
        city_id = payload.city_id or (
            payload.scenario if _city_registry.has_city(payload.scenario) else "sunamganj"
        )
        record = _record_from_snapshots(
            session,
            city_id=city_id,
            scenario_id=payload.scenario_id,
            name=payload.scenario_id,
            flooded_area_km2=response.flooded_area_km2,
            snapshots=getattr(session, "snapshots", ()),
        )
        _result_store.put(record)
        response.city_id = city_id
        response.scenario_id = payload.scenario_id
        response.available_times = record.available_times()
        if response.available_times:
            response.start_time = response.available_times[0]
            response.end_time = response.available_times[-1]
    return response.to_dict()


@app.get("/api/geocode/search")
def get_geocode_search(
    q: str = Query(..., description="Place name or 'lat, lon' coordinates"),
) -> dict:
    """Resolve a place query to geographic coordinates."""
    coordinate_result = parse_coordinate_query(q)
    if coordinate_result is not None:
        return {
            "query": q.strip(),
            "provider": "coordinates",
            "results": [coordinate_result.to_dict()],
        }

    try:
        return _location_search_service.search(q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cell/inspect")
def get_cell_inspect(
    lat: Optional[float] = Query(None, description="WGS84 latitude"),
    lon: Optional[float] = Query(None, description="WGS84 longitude"),
    latitude: Optional[float] = Query(None, description="WGS84 latitude (legacy alias)"),
    longitude: Optional[float] = Query(None, description="WGS84 longitude (legacy alias)"),
    city_id: Optional[str] = Query(None, description="Active city identifier"),
    scenario_id: Optional[str] = Query(None, description="Active scenario identifier"),
    time: Optional[float] = Query(None, description="Requested simulation time (seconds)"),
) -> dict:
    """Map a geographic point to a stored simulation cell and return modeled metrics."""
    resolved_lat = lat if lat is not None else latitude
    resolved_lon = lon if lon is not None else longitude
    if resolved_lat is None or resolved_lon is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_COORDINATES",
                "message": "lat/lon query parameters are required",
            },
        )

    try:
        inspection = _cell_inspection_service.inspect(
            city_id=city_id or "",
            scenario_id=scenario_id or "",
            latitude=resolved_lat,
            longitude=resolved_lon,
            time=time,
        )
    except InspectionError as exc:
        status_code = 400
        if exc.error_code in ("RESULT_NOT_AVAILABLE", "TIME_NOT_FOUND"):
            status_code = 404
        elif exc.error_code == "OUTSIDE_SIMULATION_DOMAIN":
            status_code = 422
        elif exc.error_code == "GRID_METADATA_ERROR":
            status_code = 409
        raise HTTPException(status_code=status_code, detail=exc.to_dict()) from exc

    return inspection.to_dict()


@app.get("/api/cities")
def get_cities() -> dict:
    """Return list of all supported cities with metadata."""
    cities = _city_registry.list_cities()
    return {
        "cities": [city.to_dict() for city in cities],
        "count": len(cities),
    }


@app.get("/api/cities/{city_id}")
def get_city(city_id: str) -> dict:
    """Return full metadata for a specific city including scenarios.

    Args:
        city_id: The city identifier.

    Returns:
        City metadata with associated scenarios.

    Raises:
        HTTPException: 404 if city not found.
    """
    try:
        city = _city_registry.get_city(city_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"City {city_id} not found",
        )

    scenarios = _city_registry.get_scenarios_for_city(city_id)
    return {
        "city": city.to_dict(),
        "scenarios": [scenario.to_dict() for scenario in scenarios],
        "scenario_count": len(scenarios),
    }


@app.get("/api/scenario/{scenario_id}/timeline")
def get_scenario_timeline(
    scenario_id: str,
    city_id: str = Query(..., description="City identifier for the stored scenario"),
) -> dict:
    """Return the stored simulation times for a completed scenario."""
    try:
        return _result_store.timeline(city_id, scenario_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RESULT_NOT_AVAILABLE",
                "message": str(exc),
            },
        ) from exc


@app.get("/api/scenario/{scenario_id}/snapshot")
def get_scenario_snapshot(
    scenario_id: str,
    city_id: str = Query(..., description="City identifier for the stored scenario"),
    time: float = Query(..., description="Exact stored simulation time in seconds"),
) -> dict:
    """Return one stored snapshot. Exact time only; no interpolation."""
    try:
        record = _result_store.get(city_id, scenario_id)
        snapshot = record.get_snapshot(time)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RESULT_NOT_AVAILABLE", "message": str(exc)},
        ) from exc
    except TemporalResultError as exc:
        status = 404 if exc.error_code == "TIME_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail=exc.to_dict()) from exc

    return {
        "city_id": city_id,
        "scenario_id": scenario_id,
        "time": snapshot["time"],
        "depth": snapshot["depth"].tolist(),
        "velocity": snapshot["velocity"].tolist(),
        "maximum_depth": snapshot["maximum_depth"].tolist(),
        "available_times": list(record.available_times()),
        "modeled": True,
        "grid": record.grid.to_dict(),
        "crs": record.crs,
    }


@app.post("/api/scenario/compare")
def post_scenario_compare(payload: ComparisonPayload) -> dict:
    """Compare two completed scenarios without invoking the numerical solver."""
    try:
        request = ComparisonRequest(
            city_id=payload.city_id,
            scenario_a_id=payload.scenario_a_id,
            scenario_b_id=payload.scenario_b_id,
            selected_layer=payload.layer,
            selected_time=payload.time,
            comparison_mode=payload.comparison_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result_a = _result_store.get(payload.city_id, payload.scenario_a_id)
        result_b = _result_store.get(payload.city_id, payload.scenario_b_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        comparison = _comparison_engine.compare(request, result_a, result_b)
    except ComparisonError as exc:
        raise HTTPException(status_code=409, detail=exc.to_dict()) from exc

    city = _city_registry.get_city(payload.city_id)
    return {
        "city": city.to_dict(),
        "scenario_a": {
            "scenario_id": result_a.scenario_id,
            "city_id": result_a.city_id,
            "name": result_a.name,
        },
        "scenario_b": {
            "scenario_id": result_b.scenario_id,
            "city_id": result_b.city_id,
            "name": result_b.name,
        },
        "compatibility": comparison.compatibility,
        "comparison": comparison.to_dict(include_array=True),
    }
