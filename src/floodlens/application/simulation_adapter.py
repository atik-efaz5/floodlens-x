"""Translate canonical platform data into SimulationService inputs. Does not import numerical/."""

from __future__ import annotations

from typing import Optional

import numpy as np

from floodlens.application.artifact_store import put_depth_artifact
from floodlens.application.canonical import FloodState, ModelDomain
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import public_source_ref
from floodlens.application.flood_extent import extent_from_depth
from floodlens.application.geospatial import ScenarioSession
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.repository import get_repository
from floodlens.application.service import SimulationService
from floodlens.application.solver_validation import SolverValidationError, validate_inputs, validate_outputs
from floodlens.application.terrain_service import resample_window_to_grid
from floodlens.core.config import SimulationConfig

PHYSICS_BASELINE_MODEL_ID = "PHYSICS-BASELINE-v0.1"


def _synthetic_dem(nx: int, ny: int, lx: float, ly: float) -> np.ndarray:
    x = np.linspace(0, lx, nx)
    y = np.linspace(0, ly, ny)
    X, Y = np.meshgrid(x, y)
    z_regional = 30.0 * (1.0 - Y / ly) ** 1.5 + 2.0
    channel_center = lx * (0.5 + 0.15 * np.sin(2 * np.pi * Y / ly))
    channel_depth = 4.0 * np.exp(-((X - channel_center) ** 2) / (2 * (lx * 0.08) ** 2))
    z = np.maximum(1.0, z_regional - channel_depth)
    return np.maximum(0.8, z).astype(np.float64)


def build_domain(city_id: str, nx: int, ny: int) -> ModelDomain:
    city = create_city_registry().get_city(city_id)
    session = ScenarioSession.default_sunamganj()
    return ModelDomain(
        domain_id=f"domain_{city_id}_{nx}x{ny}",
        city_id=city_id,
        bounds=city.bounds.to_dict(),
        crs=city.crs or "EPSG:4326",
        nx=nx,
        ny=ny,
        lx_m=session.config.Lx,
        ly_m=session.config.Ly,
        terrain_source="pending",
        created_at=isoformat(),
        input_snapshot_ids=[],
        data_status="SIMULATED",
    )


def run_physics(
    city_id: str,
    rainfall_rate_mps: float,
    *,
    nx: int = 16,
    ny: int = 16,
    duration_seconds: float = 0.5,
    steps: int = 1,
    rainfall_multiplier: float = 1.0,
    allow_synthetic_dem: bool = False,
    horizon_hours: Optional[int] = None,
    valid_at: Optional[str] = None,
    rain_snapshot_id: Optional[str] = None,
    rain_data_status: str = "UNAVAILABLE",
) -> dict:
    domain = build_domain(city_id, nx, ny)
    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=domain.lx_m,
        Ly=domain.ly_m,
        T_end=duration_seconds,
        name=f"physics_{city_id}",
    )
    fallback_used = False
    dem_pack = resample_window_to_grid(city_id, config)
    if dem_pack.get("available"):
        dem = dem_pack["elevation"]
        dem_source = public_source_ref(dem_pack.get("uri")) or "GeoTIFF"
        domain.terrain_source = dem_source
        domain.data_status = "REAL"
    elif allow_synthetic_dem:
        dem = _synthetic_dem(nx, ny, config.Lx, config.Ly)
        dem_source = "synthetic"
        fallback_used = True
        domain.terrain_source = "synthetic"
        domain.data_status = "SIMULATED"
    else:
        return {
            "available": False,
            "status": "failed",
            "reason": "Terrain unavailable. Refusing to invent elevations.",
            "validation_status": "FAIL",
        }

    rate = float(rainfall_rate_mps) * float(rainfall_multiplier)
    try:
        validate_inputs(config, dem, rate)
    except SolverValidationError as exc:
        return {
            "available": False,
            "status": "failed",
            "reason": str(exc),
            "validation_status": "FAIL",
        }

    service = SimulationService(config)
    pipeline = service.run_scenario(
        dem=dem,
        rainfall_rate=rate,
        steps=max(steps, 1),
        track_progress=False,
    )
    if not pipeline.success or not pipeline.snapshots:
        return {
            "available": False,
            "status": "failed",
            "reason": "Simulation FAILED",
            "validation_status": "FAIL",
        }

    depth = pipeline.snapshots[-1].depth
    dx = config.Lx / config.Nx
    dy = config.Ly / config.Ny
    area = config.Lx * config.Ly
    duration_total = duration_seconds * max(steps, 1)
    report = validate_outputs(depth, rate, duration_total, area, initial_volume=0.0)
    if report["validation_status"] == "FAIL":
        return {
            "available": False,
            "status": "failed",
            "reason": report.get("reason") or "Output validation failed",
            "validation_status": "FAIL",
        }

    extent = extent_from_depth(depth, dx, dy)
    generated = isoformat()
    valid = valid_at or generated
    artifact_id = f"art_physics_{city_id}_{horizon_hours or 'now'}_{generated}"
    data_status = "SIMULATED" if fallback_used else ("PARTIAL" if rain_data_status == "REAL" else "SIMULATED")
    snapshots = [sid for sid in [rain_snapshot_id, public_source_ref(dem_pack.get("uri"))] if sid]
    meta = {
        "city_id": city_id,
        "model_version": PHYSICS_MODEL_VERSION,
        "model_id": PHYSICS_BASELINE_MODEL_ID,
        "max_depth_m": extent["max_depth_m"],
        "flood_fraction": extent["flood_fraction"],
        "flooded_area_km2": extent["flooded_area_km2"],
        "clock": "simulation_seconds",
        "forcing_clock": "meteorological_hours",
        "data_status": data_status,
        "dem_source": public_source_ref(dem_source) or dem_source,
        "fallback_used": fallback_used,
        "validation_status": report["validation_status"],
        "validation_warnings": report.get("warnings") or [],
        "horizon_hours": horizon_hours,
        "valid_at": valid,
        "rainfall_rate_base_mps": float(rainfall_rate_mps),
        "rainfall_rate_applied_mps": rate,
        "rainfall_multiplier": rainfall_multiplier,
    }
    public = put_depth_artifact(artifact_id, depth, meta)
    state = FloodState(
        id=f"flood_{city_id}_{horizon_hours or 0}",
        city_id=city_id,
        horizon_hours=horizon_hours,
        timestamp=valid,
        valid_at=valid,
        generated_at=generated,
        source=PHYSICS_BASELINE_MODEL_ID,
        data_status=data_status,
        units="m",
        spatial_ref=domain.crs,
        artifact_uri=public["uri"],
        max_depth_m=extent["max_depth_m"],
        flooded_area_km2=extent["flooded_area_km2"],
        flood_fraction=extent["flood_fraction"],
        validation_status=report["validation_status"],
        model_id=PHYSICS_BASELINE_MODEL_ID,
        input_snapshot_ids=snapshots,
        expected_extent={"flood_fraction": extent["flood_fraction"], "threshold_m": extent["threshold_m"]},
        provenance={
            "data_status": data_status,
            "fallback_used": fallback_used,
            "dem_source": public_source_ref(dem_source) or dem_source,
            "solver_clock": "simulation_seconds",
            "forcing_clock": "meteorological_hours",
            "disclaimer": (
                "Depth is from a short SWE burst forced by the rainfall valid at this horizon. "
                "SWE seconds are not meteorological hours."
            ),
        },
    )
    repo = get_repository()
    repo.put_domain(domain)
    repo.put_flood_state(state)
    return {
        "available": True,
        "status": "completed",
        "flood_state": state.to_dict(),
        "artifact_id": artifact_id,
        "artifact_uri": public["uri"],
        "domain": domain.to_dict(),
        "max_depth_m": extent["max_depth_m"],
        "flood_fraction": extent["flood_fraction"],
        "flooded_area_km2": extent["flooded_area_km2"],
        "validation_status": report["validation_status"],
        "validation_warnings": report.get("warnings") or [],
        "fallback_used": fallback_used,
        "data_status": data_status,
        "model_id": PHYSICS_BASELINE_MODEL_ID,
        "model_version": PHYSICS_MODEL_VERSION,
        "available_times": [float(s.time) for s in pipeline.snapshots],
        "clock": "simulation_seconds",
        "nx": nx,
        "ny": ny,
        "rainfall_rate_base_mps": float(rainfall_rate_mps),
        "rainfall_rate_applied_mps": rate,
        "rainfall_rate_mps": rate,
        "rainfall_multiplier": rainfall_multiplier,
        "runoff_equation": "effective_mps = (precip_mm / 1000 / 3600) * runoff_coefficient * rainfall_multiplier",
        "river_level_applied_to_solver": False,
    }
