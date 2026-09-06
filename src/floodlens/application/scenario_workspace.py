"""Scenario / digital-twin workspace. Rainfall multipliers are applied; river level is not."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from floodlens.application.artifact_store import get_depth, put_depth_artifact
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.jobs import job_public_view
from floodlens.application.platform_store import get_platform_store
from floodlens.application.population import get_population_provider
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.risk import risk_from_physics

_CITIES = create_city_registry()
HISTORY_LIMIT = 50
WET_M = 0.05

PARAMETER_CAPABILITIES = [
    {
        "id": "rainfall_multiplier",
        "label": "Rainfall multiplier",
        "status": "SUPPORTED",
        "note": "Applied as effective_mps = base_rate_mps * rainfall_multiplier in the existing physics adapter.",
    },
    {
        "id": "river_level_delta_m",
        "label": "River level delta",
        "status": "PARTIAL",
        "note": "STORED SCENARIO PARAMETER. NOT CURRENTLY APPLIED TO SWE SOLVER. river_level_applied_to_solver=false.",
    },
    {
        "id": "upstream_discharge",
        "label": "Upstream discharge",
        "status": "NOT_IMPLEMENTED",
        "note": "No SWE discharge boundary coupling is configured.",
    },
    {
        "id": "drainage_degradation",
        "label": "Drainage degradation",
        "status": "NOT_IMPLEMENTED",
        "note": "No drainage network model is configured.",
    },
    {
        "id": "land_use",
        "label": "Land-use change",
        "status": "NOT_IMPLEMENTED",
        "note": "Land-use / roughness scenarios are not implemented.",
    },
    {
        "id": "terrain_modification",
        "label": "Terrain modification",
        "status": "NOT_IMPLEMENTED",
        "note": "DEM edits are not a scenario control.",
    },
    {
        "id": "dam_release",
        "label": "Dam release",
        "status": "NOT_IMPLEMENTED",
        "note": "No reservoir release forcing is configured.",
    },
]


def scenario_capabilities() -> dict:
    return {
        "parameters": PARAMETER_CAPABILITIES,
        "river_level_applied_to_solver": False,
        "note": "Only rainfall_multiplier changes simulated depth. River-level values are recorded, not forced.",
        "provenance": envelope(
            data_status="SIMULATED",
            provider="scenario-service",
            dataset="scenario-capabilities",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def _city(city_id: str):
    try:
        return _CITIES.get_city(city_id)
    except KeyError as exc:
        raise KeyError(city_id) from exc


def _job_row(job: dict) -> dict:
    view = job_public_view(job)
    payload = job.get("payload") or {}
    result = view.get("result") or {}
    started, finished = view.get("started_at"), view.get("completed_at")
    duration = None
    if started and finished:
        try:
            t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            duration = max(0.0, (t1 - t0).total_seconds())
        except ValueError:
            duration = None
    multiplier = result.get("rainfall_multiplier", payload.get("rainfall_multiplier"))
    name = payload.get("name") or (
        f"Rainfall ×{multiplier}" if multiplier is not None else job.get("kind")
    )
    return {
        **view,
        "name": name,
        "created_at": job.get("created_at"),
        "duration_seconds": duration,
        "baseline_id": payload.get("baseline_id"),
        "rainfall_multiplier": multiplier,
        "river_level_delta_m": result.get("river_level_delta_m", payload.get("river_level_delta_m", 0.0)),
        "river_level_applied_to_solver": False,
        "artifacts": {
            "overlay": result.get("artifact_id"),
            "depth": result.get("artifact_id"),
            "metadata": result.get("artifact_id"),
            "metrics": {
                "max_depth_m": result.get("max_depth_m"),
                "flood_fraction": result.get("flood_fraction"),
                "flooded_area_km2": result.get("flooded_area_km2"),
            }
            if result
            else None,
        }
        if result
        else None,
    }


def scenario_baseline(city_id: str) -> dict:
    _city(city_id)
    store = get_platform_store()
    jobs = [
        j
        for j in store.jobs.values()
        if j.get("city_id") == city_id
        and j.get("kind") in {"simulation", "scenario", "physics_forecast"}
        and j.get("status") == "completed"
        and (j.get("result") or {}).get("artifact_id")
    ]
    jobs.sort(key=lambda row: row.get("completed_at") or row.get("created_at") or "")
    ones = [
        j
        for j in jobs
        if (j.get("result") or {}).get("rainfall_multiplier") in (None, 1, 1.0)
    ]
    job = (ones or jobs)[-1] if jobs else None
    pop = get_population_provider().expose(city_id)
    result = (job or {}).get("result") or {}
    return {
        "city_id": city_id,
        "region": {"city_id": city_id, "kind": "STUDY REGION"},
        "job_id": (job or {}).get("id"),
        "forcing": {
            "rainfall_rate_base_mps": result.get("rainfall_rate_base_mps"),
            "rainfall_rate_applied_mps": result.get("rainfall_rate_applied_mps"),
            "rainfall_multiplier": result.get("rainfall_multiplier", 1.0 if job else None),
            "status": "SIMULATED" if job else "UNAVAILABLE",
        },
        "initial_state": {"status": "PARTIAL" if job else "UNAVAILABLE", "note": "Initial SWE state is the adapter default, not an observed restart."},
        "model": result.get("model_version") or PHYSICS_MODEL_VERSION,
        "method": "PHYSICS-BASELINE short SWE burst",
        "dataset": result.get("dem_source") or "scenario-service",
        "timestamp": (job or {}).get("completed_at") or (job or {}).get("created_at"),
        "configuration": {
            "nx": result.get("nx"),
            "ny": result.get("ny"),
            "clock": result.get("clock") or "simulation_seconds",
        },
        "population_exposed": pop.get("population_exposed"),
        "assumptions": [
            "SWE seconds are not meteorological hours.",
            "Rainfall multiplier is applied to the existing runoff rate.",
            "river_level_delta_m is stored and not applied to the solver.",
        ],
        "available": bool(job),
        "provenance": envelope(
            data_status="SIMULATED" if job else "UNAVAILABLE",
            provider="scenario-service",
            dataset="baseline",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def scenario_history(city_id: str, limit: int = HISTORY_LIMIT) -> dict:
    _city(city_id)
    cap = min(max(limit, 1), HISTORY_LIMIT)
    store = get_platform_store()
    rows = [
        _job_row(j)
        for j in store.jobs.values()
        if j.get("city_id") == city_id and j.get("kind") in {"simulation", "scenario", "physics_forecast"}
    ]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return {
        "city_id": city_id,
        "scenarios": rows[:cap],
        "limit": cap,
        "provenance": envelope(
            data_status="SIMULATED" if rows else "UNAVAILABLE",
            provider="scenario-service",
            dataset="scenario-history",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def _delta(a, b):
    if a is None or b is None:
        return None
    return b - a


def compare_scenario_jobs(job_ids: list[str]) -> dict:
    store = get_platform_store()
    rows = []
    for job_id in job_ids[:8]:
        job = store.jobs.get(job_id)
        if not job or not job.get("result"):
            rows.append({"job_id": job_id, "available": False, "population_exposed": None})
            continue
        result = job["result"]
        risk = None
        if result.get("flood_fraction") is not None and result.get("max_depth_m") is not None:
            risk = risk_from_physics(job.get("city_id") or "dhaka", result["flood_fraction"], result["max_depth_m"])
        rows.append(
            {
                "job_id": job_id,
                "name": (job.get("payload") or {}).get("name"),
                "available": True,
                "status": job.get("status"),
                "max_depth_m": result.get("max_depth_m"),
                "flood_fraction": result.get("flood_fraction"),
                "flooded_area_km2": result.get("flooded_area_km2"),
                "rainfall_multiplier": result.get("rainfall_multiplier"),
                "rainfall_rate_base_mps": result.get("rainfall_rate_base_mps"),
                "rainfall_rate_applied_mps": result.get("rainfall_rate_applied_mps"),
                "model_version": result.get("model_version"),
                "artifact_id": result.get("artifact_id"),
                "available_times": result.get("available_times") or [],
                "clock": result.get("clock"),
                "risk": risk,
                "population_exposed": None,
                "river_level_applied_to_solver": False,
                "data_status": result.get("data_status") or "SIMULATED",
            }
        )
    diffs = None
    if len(rows) >= 2 and rows[0].get("available") and rows[1].get("available"):
        a, b = rows[0], rows[1]
        ra, rb = a.get("risk") or {}, b.get("risk") or {}
        diffs = {
            "max_depth_m": _delta(a.get("max_depth_m"), b.get("max_depth_m")),
            "flooded_area_km2": _delta(a.get("flooded_area_km2"), b.get("flooded_area_km2")),
            "flood_fraction": _delta(a.get("flood_fraction"), b.get("flood_fraction")),
            "probability": _delta(ra.get("probability"), rb.get("probability")),
            "exposure": _delta(ra.get("exposure"), rb.get("exposure")),
            "severity": _delta(ra.get("severity"), rb.get("severity")),
            "risk_score": _delta(ra.get("score"), rb.get("score")),
            "population_exposed": None,
        }
    return {"comparisons": rows, "n": len(rows), "difference": diffs}


def difference_map(baseline_job_id: str, scenario_job_id: str) -> dict:
    store = get_platform_store()
    base = store.jobs.get(baseline_job_id)
    scen = store.jobs.get(scenario_job_id)
    if not base or not scen:
        raise KeyError("job")
    a_id = (base.get("result") or {}).get("artifact_id")
    b_id = (scen.get("result") or {}).get("artifact_id")
    depth_a = get_depth(a_id) if a_id else None
    depth_b = get_depth(b_id) if b_id else None
    if depth_a is None or depth_b is None:
        return {
            "available": False,
            "reason": "Difference map UNAVAILABLE: one or both jobs lack a depth raster.",
            "artifact_id": None,
            "kind": "difference",
        }
    if depth_a.shape != depth_b.shape:
        return {
            "available": False,
            "reason": "NOT_COMPUTED: baseline and scenario rasters have incompatible shapes.",
            "artifact_id": None,
            "kind": "difference",
        }
    delta = depth_b.astype(float) - depth_a.astype(float)
    wet_a = depth_a > WET_M
    wet_b = depth_b > WET_M
    artifact_id = f"diff_{baseline_job_id[-8:]}_{scenario_job_id[-8:]}"
    put_depth_artifact(
        artifact_id,
        delta,
        {
            "kind": "depth_difference",
            "baseline_job_id": baseline_job_id,
            "scenario_job_id": scenario_job_id,
            "model_version": PHYSICS_MODEL_VERSION,
            "note": "SCENARIO − BASELINE depth (m). Absolute difference raster; not a live map.",
        },
    )
    return {
        "available": True,
        "kind": "difference",
        "mode": "absolute",
        "artifact_id": artifact_id,
        "newly_flooded_cells": int((wet_b & ~wet_a).sum()),
        "reduced_flood_cells": int((wet_a & ~wet_b).sum()),
        "mean_delta_m": float(delta.mean()),
        "max_abs_delta_m": float(abs(delta).max()),
        "threshold_m": WET_M,
        "note": "SCENARIO − BASELINE. Compatible rasters only. Not interpolated frames.",
        "provenance": envelope(
            data_status="SIMULATED",
            provider="scenario-service",
            dataset="depth-difference",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def causal_chain(city_id: str, job_id: Optional[str] = None) -> dict:
    store = get_platform_store()
    job = store.jobs.get(job_id) if job_id else None
    result = (job or {}).get("result") or {}
    has = bool(result.get("artifact_id"))
    applied = result.get("rainfall_rate_applied_mps") is not None

    def link(name, status, note):
        return {"name": name, "status": status, "note": note}

    return {
        "city_id": city_id,
        "job_id": job_id,
        "links": [
            link("INPUT", "PARTIAL" if job else "UNAVAILABLE", "Study region, DEM, rainfall rate inputs."),
            link("RAINFALL", "SIMULATED" if applied else "UNAVAILABLE", "Multiplier applied to existing runoff rate when the job completed."),
            link("RUNOFF / WATER RESPONSE", "SIMULATED" if has else "NOT MODELED", "SIMPLE_RUNOFF_BASELINE × multiplier, then SWE."),
            link("RIVER / FLOOD STATE", "NOT MODELED", "River-level forcing is not applied to the SWE solver."),
            link("FLOOD EXTENT", "SIMULATED" if has else "UNAVAILABLE", "Wet cells at 0.05 m on the short SWE burst."),
            link("INFRASTRUCTURE IMPACT", "PARTIAL" if has else "NOT MODELED", "Available after Phase 7.3 impact on the scenario artifact."),
            link("RISK", "SIMULATED" if has else "UNAVAILABLE", "P×E×S from flood_fraction and max_depth when metrics exist. Population UNAVAILABLE."),
        ],
        "river_level_applied_to_solver": False,
        "provenance": envelope(
            data_status="SIMULATED" if has else "PARTIAL",
            provider="scenario-service",
            dataset="causal-chain",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }


def scenario_workspace(city_id: str, baseline_job: Optional[str] = None, scenario_job: Optional[str] = None) -> dict:
    baseline = scenario_baseline(city_id)
    history = scenario_history(city_id)
    compare = None
    diff = None
    if baseline_job and scenario_job:
        compare = compare_scenario_jobs([baseline_job, scenario_job])
        diff = difference_map(baseline_job, scenario_job)
    return {
        "city_id": city_id,
        "baseline": baseline,
        "history": history["scenarios"],
        "capabilities": PARAMETER_CAPABILITIES,
        "compare": compare,
        "difference": diff,
        "causal_chain": causal_chain(city_id, scenario_job or baseline_job or baseline.get("job_id")),
        "river_level_applied_to_solver": False,
        "generated_at": isoformat(),
        "provenance": envelope(
            data_status="SIMULATED",
            provider="scenario-service",
            dataset="scenario-workspace",
            freshness="SNAPSHOT",
            simulated=True,
        ),
    }
