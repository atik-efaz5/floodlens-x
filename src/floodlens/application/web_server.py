"""FastAPI backend for FloodLens-X scenario execution and geospatial inspection."""

from __future__ import annotations

from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from floodlens.application.geospatial import (
    DEFAULT_VISUALIZATION_LAYERS,
    ScenarioRunRequest,
    ScenarioRunResponse,
    ScenarioSession,
)
from floodlens.application.service import SimulationService
from floodlens.core.config import SimulationConfig
from floodlens.visualization.layer import VisualizationLayer

app = FastAPI(
    title="FloodLens-X API",
    description="Hydrodynamic flood simulation web backend",
    version="0.1.0",
)

_session: Optional[ScenarioSession] = None


class ScenarioRunPayload(BaseModel):
    """HTTP request body for scenario execution."""

    nx: int = Field(default=50, ge=5, le=300)
    ny: int = Field(default=50, ge=5, le=300)
    rainfall_rate: float = Field(default=1.0e-5, ge=0.0)
    duration_seconds: float = Field(default=5.0, gt=0.0)
    scenario: str = Field(default="sunamganj")


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


def _generate_synthetic_dem(nx: int, ny: int, lx: float, ly: float) -> np.ndarray:
    """Build a lightweight Sunamganj-like synthetic topography."""
    x = np.linspace(0, lx, nx)
    y = np.linspace(0, ly, ny)
    X, Y = np.meshgrid(x, y, indexing="ij")

    z_regional = 30.0 * (1.0 - Y / ly) ** 1.5 + 2.0
    channel_center = lx * (0.5 + 0.15 * np.sin(2 * np.pi * Y / ly))
    channel_depth = 4.0 * np.exp(-((X - channel_center) ** 2) / (2 * (lx * 0.08) ** 2))
    z = np.maximum(1.0, z_regional - channel_depth)

    haor_bowl = 2.5 * np.exp(
        -((X - lx * 0.45) ** 2 + (Y - ly * 0.25) ** 2) / (2 * (lx * 0.15) ** 2)
    )
    return np.maximum(0.8, z - haor_bowl).astype(np.float64)


def run_scenario_simulation(request: ScenarioRunRequest) -> ScenarioRunResponse:
    """Execute a simulation and update the active scenario session."""
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
    session.update_metadata_time_range(request.duration_seconds)

    return ScenarioRunResponse(
        status="completed",
        success=True,
        max_depth_m=max_depth_m,
        flooded_area_km2=flooded_area_km2,
        simulation_time_s=float(result.final_state.time),
        nx=request.nx,
        ny=request.ny,
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
    response = run_scenario_simulation(request)
    return response.to_dict()


@app.get("/api/cell/inspect")
def get_cell_inspect(
    latitude: float = Query(..., description="WGS84 latitude"),
    longitude: float = Query(..., description="WGS84 longitude"),
) -> dict:
    """Map a geographic point to a simulation cell and return cell statistics."""
    session = get_session()
    if session.state is None:
        raise HTTPException(
            status_code=409,
            detail="No simulation results available. Run POST /api/scenario/run first.",
        )

    inspection = session.inspect_cell(latitude=latitude, longitude=longitude)
    return inspection.to_dict()
