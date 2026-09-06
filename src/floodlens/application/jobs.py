"""Async-capable simulation jobs wrapping SimulationService only."""

from __future__ import annotations

from floodlens.application.canonical import ScenarioRecord, SimulationResultRef
from floodlens.application.ingest import fetch_open_meteo_precipitation
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.repository import get_repository
from floodlens.application.simulation_adapter import run_physics

OBJECT_STORE_PREFIX = "artifacts://"


def create_job(kind: str, city_id: str, payload: dict) -> dict:
    store = get_platform_store()
    return store.put_job(
        {
            "kind": kind,
            "status": "queued",
            "lifecycle": "CREATE",
            "progress": 0.0,
            "city_id": city_id,
            "payload": payload,
            "model_version": (
                PHYSICS_MODEL_VERSION
                if kind in {"simulation", "physics_forecast", "scenario"}
                else (
                    "FLOOD-OCCURRENCE-GBDT-v0.1"
                    if kind == "ai_forecast"
                    else ("AI-SPATIAL-OCCURRENCE-v0.1" if kind == "ai_spatial_forecast" else None)
                )
            ),
        }
    )


def enqueue_job(kind: str, city_id: str, payload: dict) -> dict:
    job = create_job(kind, city_id, payload)
    return run_job(job["id"])


def queue_job(kind: str, city_id: str, payload: dict) -> dict:
    """Return immediately with queued status. Caller schedules run_job."""
    return create_job(kind, city_id, payload)


def run_job(job_id: str) -> dict:
    store = get_platform_store()
    job = store.get_job(job_id)
    job["status"] = "running"
    job["lifecycle"] = "RUN"
    job["progress"] = 0.1
    job["started_at"] = isoformat()
    try:
        if job["kind"] in {"simulation", "scenario"}:
            result = _run_simulation(job)
        elif job["kind"] == "physics_forecast":
            from floodlens.application.physics_forecast import PhysicsBaselineForecastProvider

            payload = job["payload"]
            result = PhysicsBaselineForecastProvider().forecast(
                job["city_id"],
                allow_synthetic_dem=bool(payload.get("allow_synthetic_dem", False)),
                nx=int(payload.get("nx", 12)),
                ny=int(payload.get("ny", 12)),
                duration_seconds=float(payload.get("duration_seconds", 0.3)),
                steps=int(payload.get("steps", 1)),
            )
        elif job["kind"] == "ingest_osm":
            from floodlens.application.osm_ingest import ingest_osm

            result = ingest_osm(job["city_id"])
        elif job["kind"] == "ingest_rainfall":
            result = fetch_open_meteo_precipitation(job["city_id"])
        elif job["kind"] == "ai_forecast":
            from floodlens.application.ai_forecast import run_ai_forecast_job

            result = run_ai_forecast_job(job["city_id"])
        elif job["kind"] == "ai_spatial_forecast":
            from floodlens.ml.spatial.inference import run_spatial_forecast_job

            result = run_spatial_forecast_job(job["city_id"])
        else:
            raise ValueError(f"Unknown job kind: {job['kind']}")
        job["status"] = "completed"
        job["lifecycle"] = "STORE"
        job["progress"] = 1.0
        job["result"] = result
        job["result_reference"] = (result or {}).get("artifact_id") or (result or {}).get("model_id")
        job["validation_status"] = (result or {}).get("validation_status")
        job["error"] = None
    except Exception as exc:
        job["status"] = "failed"
        job["lifecycle"] = "STORE"
        job["progress"] = 1.0
        job["error"] = str(exc)
        job["result"] = None
        job["validation_status"] = "FAIL"
    job["finished_at"] = isoformat()
    job["completed_at"] = job["finished_at"]
    return job


def _run_simulation(job: dict) -> dict:
    payload = job["payload"]
    nx = int(payload.get("nx", 20))
    ny = int(payload.get("ny", 20))
    multiplier = float(payload.get("rainfall_multiplier", 1.0))
    duration = float(payload.get("duration_seconds", 1.0))
    steps = int(payload.get("steps", 2))
    allow_synthetic = bool(payload.get("allow_synthetic_dem", True))
    rain_status = "SIMULATED"
    rain_sid = None
    valid_at = None
    horizon_hours = payload.get("horizon_hours")
    if job["kind"] == "scenario" and "rainfall_rate" not in payload:
        from floodlens.application.rainfall_service import rate_at_horizon_mps

        forcing = rate_at_horizon_mps(job["city_id"], int(horizon_hours or 24))
        if not forcing.get("available"):
            raise RuntimeError(forcing.get("reason") or "REAL rainfall unavailable")
        rainfall = float(forcing["rainfall_rate_mps"])
        rain_status = forcing.get("data_status") or "UNAVAILABLE"
        rain_sid = forcing.get("snapshot_id")
        valid_at = forcing.get("valid_at")
        horizon_hours = forcing.get("horizon_hours") or horizon_hours
    else:
        rainfall = float(payload.get("rainfall_rate", 1.0e-5))
    result = run_physics(
        job["city_id"],
        rainfall,
        nx=nx,
        ny=ny,
        duration_seconds=duration,
        steps=max(steps, 1),
        rainfall_multiplier=multiplier,
        allow_synthetic_dem=allow_synthetic,
        horizon_hours=int(horizon_hours) if horizon_hours is not None else None,
        valid_at=valid_at,
        rain_snapshot_id=rain_sid,
        rain_data_status=rain_status,
    )
    if not result.get("available"):
        raise RuntimeError(result.get("reason") or "Simulation job failed")
    scenario = ScenarioRecord(
        id=job["id"],
        city_id=job["city_id"],
        rainfall_multiplier=multiplier,
        river_level_delta_m=float(payload.get("river_level_delta_m", 0.0)),
        upstream_discharge_multiplier=float(payload.get("upstream_discharge_multiplier", 1.0)),
        created_at=job.get("created_at") or isoformat(),
        creator="jobs-service",
        model_version=PHYSICS_MODEL_VERSION,
        simulation_version=PHYSICS_MODEL_VERSION,
        status="STORE",
        base_state={"nx": nx, "ny": ny, "duration_seconds": duration},
    )
    get_repository().put_scenario(scenario)
    ref = SimulationResultRef(
        id=result["artifact_id"],
        scenario_id=scenario.id,
        artifact_uri=result["artifact_uri"],
        model_version=PHYSICS_MODEL_VERSION,
        completed_at=isoformat(),
        status="STORE",
        max_depth_m=result.get("max_depth_m"),
        flood_fraction=result.get("flood_fraction"),
    )
    return {
        "artifact_id": result["artifact_id"],
        "artifact_uri": result["artifact_uri"],
        "scenario_id": scenario.id,
        "available_times": result.get("available_times") or [],
        "max_depth_m": result.get("max_depth_m"),
        "flood_fraction": result.get("flood_fraction"),
        "flooded_area_km2": result.get("flooded_area_km2"),
        "model_version": PHYSICS_MODEL_VERSION,
        "rainfall_multiplier": multiplier,
        "rainfall_rate_base_mps": result.get("rainfall_rate_base_mps"),
        "rainfall_rate_applied_mps": result.get("rainfall_rate_applied_mps"),
        "runoff_equation": result.get("runoff_equation"),
        "river_level_delta_m": float(payload.get("river_level_delta_m", 0.0)),
        "river_level_applied_to_solver": False,
        "clock": "simulation_seconds",
        "data_status": result.get("data_status"),
        "validation_status": result.get("validation_status"),
        "fallback_used": result.get("fallback_used"),
        "result_ref": ref.to_dict(),
    }


def job_public_view(job: dict) -> dict:
    result = job.get("result") or {}
    if isinstance(result, dict) and "depth" in result:
        result = {k: v for k, v in result.items() if k != "depth"}
    payload = job.get("payload") or {}
    started = job.get("started_at")
    finished = job.get("completed_at") or job.get("finished_at")
    duration = None
    if started and finished:
        try:
            from datetime import datetime

            t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            duration = max(0.0, (t1 - t0).total_seconds())
        except ValueError:
            duration = None
    return {
        "id": job.get("id"),
        "job_id": job.get("id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "progress": job.get("progress", 1.0 if job.get("status") == "completed" else 0.0),
        "city_id": job.get("city_id"),
        "name": payload.get("name"),
        "baseline_id": payload.get("baseline_id"),
        "created_at": job.get("created_at"),
        "started_at": started,
        "completed_at": finished,
        "duration_seconds": duration,
        "error": job.get("error"),
        "result_reference": job.get("result_reference") or (result.get("artifact_id") if isinstance(result, dict) else None),
        "validation_status": job.get("validation_status"),
        "result": result,
        "lifecycle": job.get("lifecycle"),
        "model_version": job.get("model_version"),
        "river_level_applied_to_solver": False,
    }


def list_jobs() -> list:
    return [job_public_view(j) for j in get_platform_store().jobs.values()]
