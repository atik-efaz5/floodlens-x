"""Tool-calling assistant. Numbers come only from registered tools."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from floodlens.application.auth import has_permission
from floodlens.application.forecast import forecast_for_city
from floodlens.application.jobs import enqueue_job, job_public_view
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import FORMULA_ID, isoformat
from floodlens.application.risk import risk_for_city
from floodlens.application.rivers import river_status, segment_neighbors

TOOLS: Dict[str, Callable[..., dict]] = {}

TOOL_PERMISSIONS = {
    "get_current_risk": "risk.read",
    "explain_risk": "risk.read",
    "get_forecast": "forecast.read",
    "explain_forecast": "forecast.read",
    "get_spatial_ai_status": "forecast.read",
    "get_river_status": "map.read",
    "get_river_forecast": "map.read",
    "get_river_neighbors": "map.read",
    "get_infrastructure_risk": "impact.read",
    "get_impact": "impact.read",
    "get_shelters": "impact.read",
    "get_planning_priorities": "impact.read",
    "run_scenario": "jobs.write",
    "compare_scenarios": "map.read",
    "get_population_exposure": "impact.read",
    "get_data_source": "map.read",
    "get_data_freshness": "map.read",
    "get_region": "map.read",
    "generate_report": "reports.write",
    "share_analysis": "shares.write",
    "get_flood_extent": "map.read",
    "explain_physics": "map.read",
    "get_historical_events": "map.read",
    "get_historical_event": "map.read",
    "get_model_performance": "map.read",
    "compare_forecast_vs_reality": "map.read",
    "get_error_analysis": "map.read",
    "get_equilibrium_residual": "research.read",
    "get_lake_at_rest_status": "research.read",
    "get_nyquist_energy": "research.read",
    "get_run_failure": "research.read",
    "get_spectral_radius": "research.read",
    "generate_research_report": "research.read",
}

ACTIVITY_LABELS = {
    "get_region": "Checking region…",
    "get_current_risk": "Checking current risk…",
    "explain_risk": "Explaining risk formula…",
    "get_forecast": "Checking forecast…",
    "explain_forecast": "Explaining heuristic forecast…",
    "get_spatial_ai_status": "Checking spatial AI status…",
    "get_river_status": "Checking river topology…",
    "get_river_forecast": "Checking river observations…",
    "get_river_neighbors": "Checking river neighbors…",
    "get_infrastructure_risk": "Checking infrastructure exposure…",
    "get_impact": "Checking impact analysis…",
    "get_shelters": "Checking shelters…",
    "get_planning_priorities": "Checking planning priorities…",
    "run_scenario": "Running scenario…",
    "compare_scenarios": "Comparing results…",
    "get_population_exposure": "Checking population exposure…",
    "get_data_source": "Checking data sources…",
    "get_data_freshness": "Checking data freshness…",
    "generate_report": "Generating report…",
    "share_analysis": "Creating share snapshot…",
    "generate_research_report": "Generating research report…",
    "get_equilibrium_residual": "Reading equilibrium residual…",
    "get_lake_at_rest_status": "Reading Lake-at-Rest status…",
    "get_nyquist_energy": "Reading Nyquist-mode energy…",
    "get_run_failure": "Reading diagnostic failure…",
    "get_spectral_radius": "Reading local Jacobian spectral radius…",
    "share_analysis": "Creating share snapshot…",
    "get_flood_extent": "Checking flood extent…",
    "explain_physics": "Explaining physics job…",
    "get_historical_events": "Checking historical catalog…",
    "get_historical_event": "Checking historical event…",
    "get_model_performance": "Checking model performance…",
    "compare_forecast_vs_reality": "Comparing prediction and observation…",
    "get_error_analysis": "Checking spatial error analysis…",
}

INJECTION_PHRASES = (
    "pretend",
    "assume the",
    "ignore previous",
    "ignore your instructions",
    "you are now",
    "act as if",
    "override",
    "make the population",
    "population is ",
    "flood probability is",
    "set the risk",
    "the river is at",
    "water level is",
    "ignore the backend",
    "give me the admin",
    "admin information",
)


def tool(name: str):
    def decorator(fn):
        TOOLS[name] = fn
        return fn

    return decorator


def _copy_num(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    return json.dumps(value)


def parse_rainfall_multiplier(message: str) -> Optional[float]:
    text = message.lower()
    rainish = any(token in text for token in ("rain", "scenario", "simulate", "what if", "what happens", "multiplier"))
    match = re.search(
        r"(?:increase|rise|raise|increases).{0,48}?(?:rainfall|rain).{0,24}?(\d+(?:\.\d+)?)\s*(?:%|percent)",
        text,
    )
    if match:
        return 1.0 + float(match.group(1)) / 100.0
    match = re.search(r"(?:rainfall|rain).{0,20}?\+(\d+(?:\.\d+)?)\s*(?:%|percent)", text)
    if match:
        return 1.0 + float(match.group(1)) / 100.0
    match = re.search(r"multiplier\s*=\s*(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", text)
    if match and rainish:
        return 1.0 + float(match.group(1)) / 100.0
    return None


def injection_flags(message: str) -> List[str]:
    text = message.lower()
    return [phrase for phrase in INJECTION_PHRASES if phrase in text]


def compact_context(raw: dict | None, role: str) -> dict:
    raw = raw or {}
    coords = raw.get("selected_coordinates")
    if coords is not None and not isinstance(coords, dict):
        coords = None
    region = raw.get("selected_region") or raw.get("city_id")
    river = raw.get("selected_river") or raw.get("river_id")
    return {
        "selected_region": region or None,
        "selected_coordinates": coords,
        "selected_river": river or None,
        "selected_segment": raw.get("selected_segment"),
        "active_layers": raw.get("active_layers") if isinstance(raw.get("active_layers"), list) else None,
        "active_scenario": raw.get("active_scenario"),
        "baseline_id": raw.get("baseline_id"),
        "scenario_id": raw.get("scenario_id"),
        "forecast_horizon": raw.get("forecast_horizon"),
        "current_data_status": raw.get("current_data_status"),
        "selected_job": raw.get("selected_job") or raw.get("job_id"),
        "selected_event_id": raw.get("selected_event_id") or raw.get("event_id"),
        "role": role,
    }


def tool_catalog(role: Optional[str] = None) -> list[dict]:
    rows = []
    for name, permission in TOOL_PERMISSIONS.items():
        if role is not None and not has_permission(role, permission):
            continue
        fn = TOOLS.get(name)
        rows.append(
            {
                "name": name,
                "purpose": (fn.__doc__ or "").strip() if fn else "",
                "authorization": permission,
                "failure_states": ["UNAVAILABLE", "NOT_COMPUTED", "FORBIDDEN", "FAILED"],
            }
        )
    return rows


@tool("get_current_risk")
def get_current_risk(city_id: str, **_: Any) -> dict:
    """Current P×E×S heuristic risk for the study region."""
    return risk_for_city(city_id)


@tool("explain_risk")
def explain_risk(city_id: str, **_: Any) -> dict:
    """Rule/formula decomposition of Risk = P × E × S. Not SHAP."""
    risk = risk_for_city(city_id)
    return {
        "explanation_type": "RULE_FORMULA",
        "not": ["SHAP", "MODEL_FEATURE_IMPORTANCE", "MODEL_SPECIFIC_ATTRIBUTION"],
        "formula_id": risk.get("formula_id") or FORMULA_ID,
        "formula": "Risk = Probability × Exposure × Severity",
        "probability": risk.get("probability"),
        "exposure": risk.get("exposure"),
        "severity": risk.get("severity"),
        "score": risk.get("score"),
        "category": risk.get("category"),
        "drivers": risk.get("drivers") or [],
        "confidence": "NOT_CALIBRATED",
        "data_status": (risk.get("provenance") or {}).get("data_status") or risk.get("note"),
        "note": "Component decomposition of the published formula. Not feature-level causal attribution.",
        "provenance": risk.get("provenance"),
    }


@tool("get_forecast")
def get_forecast(city_id: str, **_: Any) -> dict:
    """Meteorological-horizon heuristic forecast product."""
    return forecast_for_city(city_id)


@tool("explain_forecast")
def explain_forecast(city_id: str, **_: Any) -> dict:
    """Heuristic forecast method notes. Not a trained model."""
    forecast = forecast_for_city(city_id)
    return {
        "explanation_type": "RULE_FORMULA",
        "method": "HEURISTIC",
        "model_kind": forecast.get("model_kind") or "HEURISTIC",
        "model_id": forecast.get("model_id") or forecast.get("model_version"),
        "factors_used": [
            "baseline heuristic risk probability",
            "horizon growth min(0.35, hours/72*0.35)",
            "city exposure prior",
            "severity increment hours/240",
        ],
        "trained_from_data": False,
        "confidence": "NOT_CALIBRATED",
        "confidence_kind": "heuristic",
        "horizons": forecast.get("horizons") or [],
        "disclaimer": forecast.get("disclaimer"),
        "provenance": forecast.get("provenance"),
        "data_status": forecast.get("data_status") or (forecast.get("provenance") or {}).get("data_status"),
    }


@tool("get_spatial_ai_status")
def get_spatial_ai_status(**_: Any) -> dict:
    """Spatial AI remains NOT_VALIDATED / UNAVAILABLE. Not an operational map."""
    return {
        "spatial_ai": "NOT_VALIDATED",
        "spatial_api": "UNAVAILABLE",
        "available": False,
        "reason": (
            "SPATIAL AI: NOT_VALIDATED / UNAVAILABLE. "
            "POST /api/v1/forecast/ai-spatial stays fail-closed. Not an operational prediction."
        ),
        "data_status": "UNAVAILABLE",
    }


@tool("get_river_status")
def get_river_status(river_id: str, **_: Any) -> dict:
    """River network topology. Flow direction is topology-only."""
    if not river_id:
        return {"available": False, "reason": "No river selected in application context.", "river_id": None}
    try:
        payload = river_status(river_id)
    except KeyError:
        return {"available": False, "reason": "Unknown river.", "river_id": river_id}
    payload["available"] = True
    return payload


@tool("get_infrastructure_risk")
def get_infrastructure_risk(city_id: str, **_: Any) -> dict:
    """Hospital/clinic flood flags from an attached physics raster when present."""
    store = get_platform_store()
    assets = store.assets_for_city(city_id)
    hospitals = [a for a in assets if a.get("asset_type") in {"hospital", "clinic"}]
    from floodlens.application.artifact_store import get_depth
    from floodlens.application.city_data import create_city_registry
    from floodlens.application.impact import assess_impact

    jobs = [j for j in store.jobs.values() if j.get("city_id") == city_id and (j.get("result") or {}).get("artifact_id")]
    if not jobs:
        return {
            "city_id": city_id,
            "available": False,
            "reason": "No physics flood raster; per-feature flood flags are NOT_COMPUTED.",
            "hospitals_listed": len(hospitals),
            "flooded_counts": None,
            "population_exposed": None,
            "assets": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "asset_type": a.get("asset_type"),
                    "flooded": None,
                    "depth_m": None,
                    "depth_note": "NOT_COMPUTED",
                }
                for a in hospitals[:20]
            ],
        }
    latest = jobs[-1]
    artifact_id = latest["result"]["artifact_id"]
    depth = get_depth(artifact_id)
    if depth is None:
        return {
            "city_id": city_id,
            "available": False,
            "reason": "Artifact depth missing; hospital flood flags NOT_COMPUTED.",
            "flooded_counts": None,
            "population_exposed": None,
        }
    city = create_city_registry().get_city(city_id)
    impact = assess_impact(
        city_id,
        city.bounds.to_dict(),
        {"nx": depth.shape[1], "ny": depth.shape[0]},
        depth,
    )
    return {
        "city_id": city_id,
        "available": True,
        "flooded_counts": impact.get("flooded_counts"),
        "population_exposed": impact.get("population_exposed"),
        "polygons_affected": impact.get("polygons_affected"),
        "accessibility": impact.get("accessibility"),
        "assets": [
            a
            for a in impact.get("assets") or []
            if a.get("asset_type") in {"hospital", "clinic"}
        ][:20],
        "note": "Point flood flags use raster sampling. Accessibility is NOT_COMPUTED.",
    }


@tool("run_scenario")
def run_scenario_tool(city_id: str, rainfall_multiplier: float = 1.3, **kwargs: Any) -> dict:
    """Run the existing physics scenario engine. Does not invent depths."""
    try:
        multiplier = float(rainfall_multiplier)
    except (TypeError, ValueError):
        return {
            "authorized": True,
            "available": False,
            "status": "failed",
            "error": "Malformed rainfall_multiplier.",
            "rainfall_multiplier": rainfall_multiplier,
        }
    if multiplier < 0 or multiplier > 10:
        return {
            "authorized": True,
            "available": False,
            "status": "failed",
            "error": "rainfall_multiplier must be in [0, 10].",
            "rainfall_multiplier": multiplier,
        }
    percent = int(round((multiplier - 1.0) * 100))
    name = "Baseline ×1.0" if percent == 0 else f"Rainfall {percent:+d}%"
    kwargs.pop("rainfall_multiplier", None)
    return enqueue_job(
        "simulation",
        city_id,
        {
            "rainfall_multiplier": multiplier,
            "nx": 12,
            "ny": 12,
            "duration_seconds": 0.3,
            "steps": 1,
            "name": name,
            **{k: v for k, v in kwargs.items() if k in {"baseline_id", "river_level_delta_m", "allow_synthetic_dem"}},
        },
    )


@tool("get_flood_extent")
def get_flood_extent(city_id: str, **_: Any) -> dict:
    """Latest stored physics flood-state metrics."""
    from floodlens.application.repository import get_repository

    states = get_repository().list_flood_states(city_id)
    if not states:
        return {
            "city_id": city_id,
            "available": False,
            "reason": "No physics flood state stored. Run a physics forecast or scenario first.",
            "max_depth_m": None,
            "flooded_area_km2": None,
        }
    latest = states[-1]
    return {
        "city_id": city_id,
        "available": True,
        "flood_state_id": latest.id,
        "horizon_hours": latest.horizon_hours,
        "max_depth_m": latest.max_depth_m,
        "flooded_area_km2": latest.flooded_area_km2,
        "flood_fraction": latest.flood_fraction,
        "validation_status": latest.validation_status,
        "data_status": latest.data_status,
        "artifact_uri": latest.artifact_uri,
        "threshold_m": 0.05,
    }


@tool("get_river_forecast")
def get_river_forecast(river_id: str, **_: Any) -> dict:
    """River water level / discharge if a gauge series exists."""
    from floodlens.application.river_state import river_state

    if not river_id:
        return {
            "available": False,
            "reason": "WATER LEVEL: UNAVAILABLE. DISCHARGE: UNAVAILABLE. No river selected.",
            "river_id": None,
            "discharge_m3s": None,
            "water_level_m": None,
        }
    try:
        state = river_state(river_id)
    except KeyError:
        return {
            "available": False,
            "reason": "Unknown river. WATER LEVEL: UNAVAILABLE. DISCHARGE: UNAVAILABLE.",
            "river_id": river_id,
            "discharge_m3s": None,
            "water_level_m": None,
        }
    forecast = state.get("forecast") or {}
    current = state.get("current") or {}
    water = current.get("water_level_m")
    discharge = current.get("discharge_m3s")
    if water is None and discharge is None:
        reason = forecast.get("reason") or "WATER LEVEL: UNAVAILABLE. DISCHARGE: UNAVAILABLE."
    else:
        reason = forecast.get("reason")
    return {
        "river_id": river_id,
        "available": bool(forecast.get("available")),
        "reason": reason,
        "current": current,
        "trend": state.get("trend"),
        "discharge_m3s": discharge,
        "water_level_m": water,
        "data_status": (state.get("provenance") or {}).get("data_status", "UNAVAILABLE"),
        "flow_direction_status": "UNAVAILABLE / TOPOLOGY ONLY",
    }


@tool("get_river_neighbors")
def get_river_neighbors(river_id: str, selected_segment: str | None = None, **_: Any) -> dict:
    """Upstream/downstream topology for the selected segment. Not hydrological flow."""
    if not river_id or not selected_segment:
        return {
            "available": False,
            "reason": "No river segment selected in application context.",
            "upstream": None,
            "downstream": None,
        }
    try:
        payload = segment_neighbors(river_id, selected_segment)
    except KeyError:
        return {"available": False, "reason": "Unknown river segment.", "river_id": river_id, "segment_id": selected_segment}
    payload["available"] = True
    return payload


@tool("compare_scenarios")
def compare_scenarios_tool(city_id: str, job_ids: List[str] | None = None, **_: Any) -> dict:
    """Compare completed physics jobs. Population delta stays null."""
    from floodlens.application.scenario_workspace import compare_scenario_jobs

    store = get_platform_store()
    ids = [job_id for job_id in (job_ids or []) if job_id]
    if len(ids) < 2:
        jobs = [j for j in store.jobs.values() if j.get("city_id") == city_id and j.get("result")]
        jobs = sorted(jobs, key=lambda j: j.get("completed_at") or j.get("created_at") or "")[-2:]
        ids = [j["id"] for j in jobs]
    return compare_scenario_jobs(ids)


@tool("get_population_exposure")
def get_population_exposure(city_id: str, **_: Any) -> dict:
    """Population exposure from the configured provider. Null until a provider exists."""
    from floodlens.application.population import get_population_provider

    return get_population_provider().expose(city_id)


@tool("get_data_source")
def get_data_source(city_id: str, **_: Any) -> dict:
    """Provenance catalog for configured sources."""
    from floodlens.application.catalog import data_source_catalog

    return data_source_catalog(city_id)


@tool("get_data_freshness")
def get_data_freshness(city_id: str, **_: Any) -> dict:
    """Freshness labels copied from the data-source catalog."""
    from floodlens.application.catalog import data_source_catalog

    catalog = data_source_catalog(city_id)
    rainfall = next((s for s in catalog["sources"] if s["id"] == "open-meteo"), {})
    return {
        "city_id": city_id,
        "sources": [
            {
                "id": s["id"],
                "title": s["title"],
                "data_status": s["data_status"],
                "freshness": s["freshness"],
                "fallback_used": s.get("fallback_used", False),
            }
            for s in catalog["sources"]
        ],
        "rainfall_freshness": rainfall.get("freshness"),
        "rainfall_data_status": rainfall.get("data_status"),
        "rainfall_fallback_used": rainfall.get("fallback_used"),
    }


@tool("get_region")
def get_region(city_id: str, **_: Any) -> dict:
    """Study-region lookup from the city registry."""
    from floodlens.application.city_data import create_city_registry

    if not city_id:
        return {"city_id": None, "available": False, "reason": "No location is selected in application context."}
    registry = create_city_registry()
    try:
        city = registry.get_city(city_id)
    except KeyError:
        return {"city_id": city_id, "available": False, "reason": "Unknown region."}
    return {
        "city_id": city.city_id,
        "name": city.name,
        "bounds": city.bounds.to_dict(),
        "center_lat": city.center_lat,
        "center_lon": city.center_lon,
        "available": True,
    }


@tool("generate_report")
def generate_report_tool(
    city_id: str,
    baseline_id: str | None = None,
    scenario_id: str | None = None,
    event_id: str | None = None,
    selected_event_id: str | None = None,
    **_: Any,
) -> dict:
    """Generate a region or historical report from verified products, not LLM numbers."""
    from floodlens.application.reports import generate_region_report

    return generate_region_report(
        city_id,
        baseline_job_id=baseline_id,
        scenario_job_id=scenario_id,
        event_id=event_id or selected_event_id,
        created_by=None,
    )


@tool("share_analysis")
def share_analysis_tool(
    city_id: str,
    baseline_id: str | None = None,
    scenario_id: str | None = None,
    event_id: str | None = None,
    selected_event_id: str | None = None,
    **_: Any,
) -> dict:
    """Share a frozen snapshot of a generated report. Does not invent numbers."""
    from floodlens.application.reports import generate_region_report, share_report

    chosen = event_id or selected_event_id
    report = generate_region_report(
        city_id,
        baseline_job_id=baseline_id,
        scenario_job_id=scenario_id,
        event_id=chosen,
    )
    share = share_report(report["id"], visibility="private")
    return {
        "share_id": share.get("id"),
        "report_id": report.get("id"),
        "banner": share.get("banner"),
        "live": False,
        "generated_at": share.get("generated_at") or report.get("generated_at"),
        "model_version": share.get("model_version") or report.get("model_version"),
        "note": "Historical snapshot. Current live data is not substituted.",
    }


@tool("get_impact")
def get_impact(city_id: str, selected_job: str | None = None, **_: Any) -> dict:
    """Phase 7.3 region impact summary. Population stays UNAVAILABLE."""
    from floodlens.application.impact_workspace import region_impact

    payload = region_impact(city_id, job_id=selected_job)
    cats = payload.get("categories") or {}
    return {
        "city_id": city_id,
        "available": True,
        "categories": {
            key: {
                "status": row.get("status"),
                "affected": row.get("affected"),
                "total": row.get("total"),
                "reason": row.get("reason"),
                "computation": row.get("computation"),
            }
            for key, row in cats.items()
        },
        "scenario": payload.get("scenario"),
        "safety": payload.get("safety"),
        "population_exposed": (cats.get("population") or {}).get("affected"),
        "provenance": payload.get("provenance"),
    }


@tool("get_shelters")
def get_shelters(city_id: str, selected_job: str | None = None, **_: Any) -> dict:
    """Shelter exposure vs accessibility/capacity/occupancy, kept separate."""
    from floodlens.application.impact_workspace import shelter_assessments

    payload = shelter_assessments(city_id, job_id=selected_job)
    compact = []
    for row in (payload.get("shelters") or [])[:20]:
        compact.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "flood_exposure": row.get("exposure_status"),
                "accessibility": row.get("accessibility_status"),
                "capacity": row.get("capacity"),
                "occupancy": row.get("occupancy"),
                "suitability": row.get("suitability"),
                "suitability_note": row.get("suitability_note"),
            }
        )
    return {
        "city_id": city_id,
        "shelters": compact,
        "capacity_status": payload.get("capacity_status"),
        "occupancy_status": payload.get("occupancy_status"),
        "accessibility_status": payload.get("accessibility_status"),
        "note": "Not labeled globally safe. CAPACITY/OCCUPANCY: UNAVAILABLE. ACCESSIBILITY: UNAVAILABLE/NOT_COMPUTED.",
        "safety": payload.get("safety"),
        "provenance": payload.get("provenance"),
    }


@tool("get_planning_priorities")
def get_planning_priorities(city_id: str, selected_job: str | None = None, **_: Any) -> dict:
    """Planning-support priorities from Phase 7.3. Inventories stay UNAVAILABLE."""
    from floodlens.application.impact_workspace import resource_priorities

    payload = resource_priorities(city_id, job_id=selected_job)
    return {
        "city_id": city_id,
        "kind": "AI-GENERATED PLANNING SUPPORT",
        "official_evacuation_order": False,
        "inventory": payload.get("inventory"),
        "planning_estimates": payload.get("planning_estimates"),
        "priorities": payload.get("priorities"),
        "safety": payload.get("safety"),
        "scenario": payload.get("scenario"),
        "provenance": payload.get("provenance"),
    }


@tool("explain_physics")
def explain_physics(city_id: str, selected_job: str | None = None, **_: Any) -> dict:
    """Computational chain for a physics/scenario job. The model does not 'understand' flooding."""
    store = get_platform_store()
    job = store.jobs.get(selected_job) if selected_job else None
    if job is None:
        jobs = [
            j
            for j in store.jobs.values()
            if j.get("city_id") == city_id and j.get("kind") in {"simulation", "scenario", "physics_forecast"}
        ]
        jobs.sort(key=lambda row: row.get("completed_at") or row.get("created_at") or "")
        job = jobs[-1] if jobs else None
    if job is None:
        return {
            "available": False,
            "reason": "No physics job in application context.",
            "explanation_type": "DATA_QUALITY",
            "river_level_applied_to_solver": False,
        }
    result = job.get("result") or {}
    return {
        "available": bool(result),
        "explanation_type": "RULE_FORMULA",
        "job_id": job.get("id"),
        "status": job.get("status"),
        "error": job.get("error"),
        "forcing": {
            "rainfall_multiplier": result.get("rainfall_multiplier"),
            "rainfall_rate_base_mps": result.get("rainfall_rate_base_mps"),
            "rainfall_rate_applied_mps": result.get("rainfall_rate_applied_mps"),
            "runoff_equation": result.get("runoff_equation"),
        },
        "terrain": result.get("dem_source") or "adapter DEM / synthetic if allowed",
        "initial_state": "Adapter default SWE state; not an observed restart.",
        "model": result.get("model_version") or job.get("model_version"),
        "scenario_parameters": {
            "rainfall_multiplier": result.get("rainfall_multiplier"),
            "river_level_delta_m": result.get("river_level_delta_m"),
            "river_level_applied_to_solver": False,
        },
        "simulation_time": {
            "clock": result.get("clock") or "simulation_seconds",
            "available_times": result.get("available_times") or [],
        },
        "note": "Computational chain only. The physics adapter does not 'understand' flooding.",
        "data_status": result.get("data_status") or "SIMULATED",
    }


@tool("get_historical_events")
def get_historical_events_tool(**_: Any) -> dict:
    """Historical event catalog (GFM + EMSR). Observed rasters are not invented."""
    from floodlens.application.historical_workspace import event_catalog

    catalog = event_catalog()
    return {
        "data": (catalog.get("data") or [])[:20],
        "n": catalog.get("n"),
        "observed_flood_extent": None,
        "forecast_accuracy": None,
        "data_status": "PARTIAL",
        "reason": catalog.get("note"),
        "provenance": catalog.get("provenance"),
    }


@tool("get_historical_event")
def get_historical_event_tool(event_id: str | None = None, selected_event_id: str | None = None, **_: Any) -> dict:
    """Replay metadata for one historical event. No fabricated forecasts."""
    from floodlens.application.historical_workspace import event_detail

    chosen = event_id or selected_event_id
    if not chosen:
        return {
            "available": False,
            "reason": "No historical event is selected. Browse /history/events and select an event_id.",
            "forecast_accuracy": None,
        }
    try:
        detail = event_detail(chosen)
    except KeyError:
        return {"available": False, "event_id": chosen, "reason": "Unknown historical event.", "forecast_accuracy": None}
    compare = detail.get("compare") or {}
    return {
        "available": True,
        "event_id": chosen,
        "event": detail.get("event"),
        "timeline": [
            {"timestamp": row.get("timestamp"), "source": row.get("source"), "semantic_type": row.get("semantic_type")}
            for row in (detail.get("timeline") or [])[:24]
        ],
        "n_observations": len(detail.get("timeline") or []),
        "observation_metrics": (detail.get("observation_metrics") or {}).get("metrics"),
        "comparison": compare.get("comparison"),
        "comparison_reason": compare.get("reason"),
        "forecast_accuracy": None if compare.get("comparison") != "COMPARABLE" else compare.get("metrics"),
        "limitations": detail.get("limitations"),
        "provenance": detail.get("provenance"),
    }


@tool("get_model_performance")
def get_model_performance_tool(model_id: str | None = None, **_: Any) -> dict:
    """Named metrics with dataset/split/horizon. Not a generic accuracy percentage."""
    from floodlens.application.historical_workspace import model_performance_payload

    payload = model_performance_payload(model_id)
    selected = payload.get("selected") or {}
    headline = selected.get("headline") or {}
    return {
        "available": True,
        "model_id": selected.get("id") or selected.get("model_id"),
        "task": selected.get("task") or headline.get("task"),
        "dataset": selected.get("training_dataset") or headline.get("dataset"),
        "splits": selected.get("splits") or selected.get("split_counts"),
        "metrics": {
            "auprc": headline.get("auprc"),
            "brier": headline.get("brier"),
            "iou": headline.get("iou"),
            "f1": headline.get("f1"),
            "n_test_samples": headline.get("n_test_samples"),
            "horizon": headline.get("horizon"),
            "target": headline.get("target"),
            "accuracy_claim": None,
        },
        "spatial_ai": payload.get("spatial_ai"),
        "uncertainty": payload.get("uncertainty"),
        "statistical_power_limited": headline.get("statistical_power_limited"),
        "limitations": selected.get("limitations"),
        "accuracy_claim": None,
        "note": payload.get("message"),
    }


@tool("compare_forecast_vs_reality")
def compare_forecast_vs_reality_tool(
    event_id: str | None = None,
    selected_event_id: str | None = None,
    prediction_id: str | None = None,
    **_: Any,
) -> dict:
    """Compare prediction and observation only when artifacts are compatible."""
    from floodlens.application.historical_workspace import compare_event

    chosen = event_id or selected_event_id
    if not chosen:
        return {
            "comparison": "UNAVAILABLE",
            "reason": "No historical event selected. Cannot compare prediction and reality.",
            "metrics": None,
        }
    try:
        return compare_event(chosen, prediction_id=prediction_id)
    except KeyError:
        return {"comparison": "UNAVAILABLE", "reason": "Unknown historical event.", "metrics": None}


@tool("get_error_analysis")
def get_error_analysis_tool(
    event_id: str | None = None,
    selected_event_id: str | None = None,
    prediction_id: str | None = None,
    **_: Any,
) -> dict:
    """Spatial/timing error only when a compatible prediction exists."""
    from floodlens.application.historical_workspace import compare_event

    chosen = event_id or selected_event_id
    if not chosen:
        return {
            "available": False,
            "reason": "No historical event selected.",
            "biggest_error": None,
        }
    try:
        compare = compare_event(chosen, prediction_id=prediction_id)
    except KeyError:
        return {"available": False, "reason": "Unknown historical event.", "biggest_error": None}
    if compare.get("comparison") != "COMPARABLE":
        return {
            "available": False,
            "comparison": compare.get("comparison"),
            "reason": compare.get("reason") or "Error analysis requires a compatible prediction and observation.",
            "biggest_error": None,
            "spatial_error": None,
            "timing_error": compare.get("timing_error"),
        }
    metrics = compare.get("metrics") or {}
    return {
        "available": True,
        "comparison": "COMPARABLE",
        "metrics": metrics,
        "spatial_error": compare.get("spatial_error"),
        "timing_error": compare.get("timing_error"),
        "biggest_error": None,
        "note": "Biggest-error ranking requires event-level comparable maps; arrays stay out of JSON.",
    }


@tool("get_equilibrium_residual")
def get_equilibrium_residual_tool(**_: Any) -> dict:
    from floodlens.application.research_center import latest_value

    payload = latest_value("equilibrium_residual")
    payload["note"] = "Value is from the last stored Lake-at-Rest / long-term experiment. Norms are L1/L2/L∞ of |p|."
    return payload


@tool("get_lake_at_rest_status")
def get_lake_at_rest_status_tool(**_: Any) -> dict:
    from floodlens.application.research_center import latest_value

    return latest_value("lake_at_rest")


@tool("get_nyquist_energy")
def get_nyquist_energy_tool(**_: Any) -> dict:
    from floodlens.application.research_center import latest_value

    payload = latest_value("nyquist")
    payload["note"] = "Nyquist-mode energy is observed. High-frequency content is not automatically UNSTABLE."
    return payload


@tool("get_run_failure")
def get_run_failure_tool(**_: Any) -> dict:
    from floodlens.application.research_center import latest_value

    return latest_value("failure")


@tool("get_spectral_radius")
def get_spectral_radius_tool(**_: Any) -> dict:
    from floodlens.application.research_center import latest_value

    payload = latest_value("spectral_radius")
    payload["global_stability_proof"] = False
    payload["methodological_note"] = (
        "LOCAL JACOBIAN SPECTRAL RADIUS IS NOT BY ITSELF PROOF OF GLOBAL LONG-TERM STABILITY."
    )
    return payload


@tool("generate_research_report")
def generate_research_report_tool(experiment_id: str | None = None, **_: Any) -> dict:
    from floodlens.application.research_center import generate_research_report

    return generate_research_report(experiment_id, created_by=None)


def _select_tools(message: str) -> List[str]:
    text = message.lower()
    selected: List[str] = []
    if "equilibrium residual" in text:
        selected.append("get_equilibrium_residual")
        return selected
    if "lake-at-rest" in text or "lake at rest" in text:
        selected.append("get_lake_at_rest_status")
        return selected
    if "nyquist" in text:
        selected.append("get_nyquist_energy")
        return selected
    if "spectral radius" in text or "jacobian" in text:
        selected.append("get_spectral_radius")
        return selected
    if "why did this run fail" in text or "why did the run fail" in text or "failed at step" in text:
        selected.append("get_run_failure")
        return selected
    if "research report" in text:
        selected.append("generate_research_report")
        return selected
    if any(phrase in text for phrase in ("spatial ai", "ai flood map", "ai-spatial", "spatial-ai")):
        selected.append("get_spatial_ai_status")
        return selected
    if any(
        phrase in text
        for phrase in (
            "prediction and reality",
            "forecast vs",
            "forecast versus",
            "predicted vs",
            "compare prediction",
            "forecast vs reality",
        )
    ):
        selected.append("compare_forecast_vs_reality")
        selected.append("get_historical_event")
    if any(
        phrase in text
        for phrase in ("how well did the model", "model perform", "model performance", "aoi gbdt")
    ):
        selected.append("get_model_performance")
    if any(
        phrase in text
        for phrase in ("biggest error", "spatial error", "error map", "false alarm", "missed flood")
    ):
        selected.append("get_error_analysis")
        selected.append("compare_forecast_vs_reality")
    if any(
        phrase in text
        for phrase in (
            "what happened during this flood",
            "this flood",
            "historical event",
            "historical",
            "flood progression",
            "observed state",
            "replay",
        )
    ):
        selected.append("get_historical_event")
        selected.append("get_historical_events")
    if "population" in text or "displaced" in text or "how many people" in text:
        selected.append("get_population_exposure")
        selected.append("get_impact")
    if any(word in text for word in ("why is this", "why is the area", "explain risk", "how bad", "high risk")):
        selected.append("get_region")
        selected.append("get_current_risk")
        selected.append("explain_risk")
    elif any(word in text for word in ("risk", "flood probability", "will this area", "current risk")):
        selected.append("get_current_risk")
        selected.append("explain_risk")
        if "forecast" in text or "24" in text or "hour" in text:
            selected.append("get_forecast")
            selected.append("explain_forecast")
    if "forecast" in text and "river" not in text and "compare_forecast_vs_reality" not in selected:
        selected.append("get_forecast")
        selected.append("explain_forecast")
    if "heuristic" in text:
        selected.append("explain_forecast")
    if "shelter" in text or "safest" in text:
        selected.append("get_shelters")
    if any(word in text for word in ("hospital", "school", "road", "infrastructure", "bridge")):
        selected.append("get_infrastructure_risk")
        selected.append("get_impact")
    if any(word in text for word in ("priorit", "what should", "planner", "emergency plan", "resource")):
        selected.append("get_planning_priorities")
        selected.append("get_current_risk")
    if "report" in text:
        selected.append("generate_report")
    if "share this" in text or "share the analysis" in text or "share this analysis" in text:
        selected.append("share_analysis")
    if parse_rainfall_multiplier(text) is not None or "what if" in text or "simulate" in text:
        selected.append("get_region")
        selected.append("run_scenario")
        selected.append("compare_scenarios")
        selected.append("explain_physics")
    elif "rainfall" in text and "fresh" not in text and "source" not in text:
        selected.append("run_scenario")
    if "extent" in text or "flooded area" in text or "how deep" in text:
        selected.append("get_flood_extent")
    if any(word in text for word in ("upstream", "downstream", "segment")):
        selected.append("get_river_neighbors")
        selected.append("get_river_status")
    if any(word in text for word in ("water level", "discharge", "gauge")):
        selected.append("get_river_forecast")
        selected.append("get_river_status")
    elif "river" in text:
        selected.append("get_river_status")
        selected.append("get_river_forecast")
    if any(word in text for word in ("historical", "this event", "flood progression", "observed state")):
        selected.append("get_historical_events")
        selected.append("get_historical_event")
    if any(
        phrase in text
        for phrase in ("real or simulated", "is this real", "data source", "provenance", "simulated")
    ):
        selected.append("get_data_source")
    if any(phrase in text for phrase in ("how fresh", "freshness", "how old", "rainfall fresh")):
        selected.append("get_data_freshness")
    if "region" in text or "which city" in text or "area of interest" in text or "here" in text:
        selected.append("get_region")
    if "physics" in text or "solver" in text or "why did the simulation" in text:
        selected.append("explain_physics")
    if not selected:
        selected = ["get_region", "get_current_risk"]
    return list(dict.fromkeys(selected))


def _forbidden(name: str, permission: str) -> dict:
    return {
        "authorized": False,
        "error_code": "FORBIDDEN",
        "permission": permission,
        "tool": name,
        "reason": "Natural-language requests cannot bypass role permissions.",
    }


def chat(message: str, context: dict | None = None, role: str = "general") -> dict:
    compact = compact_context(context, role)
    city_id = compact.get("selected_region")
    river_id = compact.get("selected_river")
    event_match = re.search(r"evt:\d{4}-\d{2}-\d{2}", message)
    event_id = compact.get("selected_event_id") or (event_match.group(0) if event_match else None)
    flags = injection_flags(message)
    tool_names = _select_tools(message)
    tool_results: dict = {}
    denied: List[str] = []
    baseline_job = None
    scenario_job = None
    multiplier = parse_rainfall_multiplier(message)

    for name in tool_names:
        permission = TOOL_PERMISSIONS.get(name, "assistant.chat")
        if not has_permission(role, permission):
            tool_results[name] = _forbidden(name, permission)
            denied.append(name)
            continue
        fn = TOOLS[name]
        kwargs = {
            "city_id": city_id,
            "river_id": river_id,
            "selected_job": compact.get("selected_job") or compact.get("scenario_id"),
            "selected_segment": compact.get("selected_segment"),
            "baseline_id": compact.get("baseline_id"),
            "scenario_id": compact.get("scenario_id"),
            "event_id": event_id,
            "selected_event_id": event_id,
        }
        if name == "run_scenario":
            if multiplier is None:
                kwargs["rainfall_multiplier"] = 1.0
            else:
                if compact.get("baseline_id"):
                    store = get_platform_store()
                    existing = store.jobs.get(compact["baseline_id"])
                    if existing:
                        baseline_job = job_public_view(existing)
                        tool_results["run_scenario_baseline"] = baseline_job
                else:
                    baseline_job = run_scenario_tool(city_id, rainfall_multiplier=1.0)
                    tool_results["run_scenario_baseline"] = baseline_job
                scenario_job = run_scenario_tool(city_id, rainfall_multiplier=multiplier)
                tool_results["run_scenario"] = scenario_job
                continue
        if name == "compare_scenarios":
            ids = [j["id"] for j in (baseline_job, scenario_job) if j and j.get("id")]
            if compact.get("baseline_id") and compact.get("scenario_id"):
                ids = [compact["baseline_id"], compact["scenario_id"]]
            kwargs["job_ids"] = ids
        tool_results[name] = fn(**kwargs)

    reply = _format_reply(message, tool_results, compact, flags, multiplier, role)
    evidence = _evidence_rows(tool_results, compact)
    sources = _source_rows(tool_results)
    job_ids = [
        (tool_results.get("run_scenario") or {}).get("id"),
        (tool_results.get("run_scenario_baseline") or {}).get("id"),
        compact.get("selected_job"),
    ]
    get_platform_store().audit(
        "assistant.chat",
        actor=role,
        detail={
            "city_id": city_id,
            "tools": tool_names,
            "denied": denied,
            "job_ids": [job_id for job_id in job_ids if job_id],
            "injection": bool(flags),
            "question_preview": (message or "")[:80],
        },
    )
    return {
        "reply": reply,
        "tools_called": tool_names,
        "tool_results": tool_results,
        "context": compact,
        "activity": [{"tool": name, "label": ACTIVITY_LABELS.get(name, name)} for name in tool_names],
        "evidence": evidence,
        "sources": sources,
        "injection_flags": flags,
        "authorized_denied": denied,
        "generated_at": isoformat(),
        "export": {
            "timestamp": isoformat(),
            "region": city_id,
            "scenario": compact.get("scenario_id") or compact.get("active_scenario"),
            "model_method": _method_label(tool_results),
            "evidence": evidence,
            "limitations": _limitations(tool_results, flags),
        },
        "policy": "Numbers below are copied from tools. Conversation claims are not a source of truth.",
        "disclaimer": (
            "AI-generated planning support. Not an official evacuation order. "
            "Review with official emergency guidance."
        ),
    }


def _method_label(tool_results: dict) -> str:
    if "explain_forecast" in tool_results:
        return "HEURISTIC"
    if "run_scenario" in tool_results or "explain_physics" in tool_results:
        return "PHYSICS-BASELINE"
    if "explain_risk" in tool_results:
        return "RULE_FORMULA P×E×S"
    return "TOOL"


def _evidence_rows(tool_results: dict, compact: dict) -> list[dict]:
    rows = []
    for name, payload in tool_results.items():
        if not isinstance(payload, dict):
            continue
        provenance = payload.get("provenance") or {}
        rows.append(
            {
                "tool": name,
                "source": provenance.get("provider") or provenance.get("source") or name,
                "timestamp": provenance.get("timestamp") or provenance.get("retrieved_at") or payload.get("generated_at"),
                "data_status": provenance.get("data_status") or payload.get("data_status") or compact.get("current_data_status"),
                "model": payload.get("model_kind") or payload.get("model_version") or payload.get("model_id") or provenance.get("model_version"),
                "dataset": provenance.get("dataset") or provenance.get("data_version"),
                "job_id": payload.get("id") or payload.get("job_id") or (payload.get("scenario") or {}).get("job_id"),
            }
        )
    return rows[:12]


def _source_rows(tool_results: dict) -> list[dict]:
    rows = []
    catalog = tool_results.get("get_data_source") or {}
    for item in catalog.get("sources") or []:
        rows.append(
            {
                "title": item.get("title"),
                "data_status": item.get("data_status"),
                "freshness": item.get("freshness"),
                "url": None,
            }
        )
    if not rows:
        for name, payload in tool_results.items():
            if isinstance(payload, dict) and payload.get("provenance"):
                prov = payload["provenance"]
                rows.append(
                    {
                        "title": name,
                        "data_status": prov.get("data_status"),
                        "freshness": prov.get("freshness"),
                        "url": None,
                    }
                )
    return rows


def _limitations(tool_results: dict, flags: list[str]) -> list[str]:
    lines = [
        "Unavailable fields stay unavailable.",
        "CONFIDENCE: NOT_CALIBRATED unless a calibrated product exists.",
        "river_level_delta_m is not applied to the SWE solver.",
        "Not an official evacuation order.",
    ]
    if flags:
        lines.insert(0, "Conversation claims were ignored; verified backend state was used.")
    if "get_spatial_ai_status" in tool_results:
        lines.append("SPATIAL AI: NOT_VALIDATED / UNAVAILABLE.")
    if "get_population_exposure" in tool_results:
        pop = tool_results["get_population_exposure"]
        if pop.get("available"):
            lines.append(
                f"Population exposure is {pop.get('data_status') or 'DEMO'}. {pop.get('reason') or ''}".strip()
            )
        else:
            lines.append(
                "Population exposure is unavailable because no authoritative population dataset is configured."
            )
    if "compare_forecast_vs_reality" in tool_results or "get_error_analysis" in tool_results:
        lines.append("Prediction vs observation is not computed when artifacts are missing or incompatible.")
    if "get_model_performance" in tool_results:
        lines.append("Do not quote a generic accuracy percentage. Spatial AI remains NOT_VALIDATED.")
    return lines


def _format_reply(
    message: str,
    tool_results: dict,
    compact: dict,
    flags: list[str],
    multiplier: Optional[float],
    role: str,
) -> str:
    sections: List[str] = []
    if flags:
        sections.append(
            "CONVERSATION CLAIM ignored. Verified application/backend state is the only source of numerical values."
        )
    if not compact.get("selected_region") and "get_region" in tool_results:
        region = tool_results["get_region"]
        if not region.get("available"):
            return (
                "ANSWER No location is selected in application context. "
                "Select a study region before asking about 'here'. "
                "LIMITATIONS The assistant does not guess a city from conversation. "
                "SOURCE application context"
            )

    planning = "get_planning_priorities" in tool_results
    scenario = "run_scenario" in tool_results
    scenario_ran = scenario and tool_results.get("run_scenario", {}).get("authorized") is not False
    if scenario_ran:
        sections.append(_scenario_block(tool_results, multiplier))
        if planning:
            sections.append(_planning_block(tool_results, role))
    elif planning:
        sections.append(_planning_block(tool_results, role))
    else:
        sections.append(_answer_block(tool_results, compact, role))

    sections.append("EVIDENCE " + _evidence_text(tool_results))
    sections.append("LIMITATIONS " + " ".join(_limitations(tool_results, flags)))
    sections.append("SOURCE " + _source_text(tool_results, compact))
    sections.append("All figures are copied from tool JSON; unavailable fields stay unavailable.")
    return " ".join(part for part in sections if part)


def _answer_block(tool_results: dict, compact: dict, role: str) -> str:
    bits = ["ANSWER"]
    if "get_spatial_ai_status" in tool_results:
        spatial = tool_results["get_spatial_ai_status"]
        bits.append(spatial.get("reason") or "SPATIAL AI: NOT_VALIDATED / UNAVAILABLE.")
        return " ".join(bits)
    if tool_results.get("get_region"):
        region = tool_results["get_region"]
        if region.get("authorized") is False:
            bits.append(region["reason"])
        elif region.get("available"):
            bits.append(f"Region {region['name']} ({region['city_id']}).")
        else:
            bits.append(region.get("reason", "Region UNAVAILABLE."))
    if "explain_risk" in tool_results:
        expl = tool_results["explain_risk"]
        if expl.get("authorized") is False:
            bits.append(expl["reason"])
        else:
            bits.append(
                f"Risk category {expl.get('category')} from RULE_FORMULA {expl.get('formula')} "
                f"(not SHAP). Flood probability P={_copy_num(expl.get('probability'))} "
                f"Exposure E={_copy_num(expl.get('exposure'))} (city prior, not population) "
                f"Severity S={_copy_num(expl.get('severity'))} score={_copy_num(expl.get('score'))}. "
                f"CONFIDENCE: {expl.get('confidence')}."
            )
    elif "get_current_risk" in tool_results:
        risk = tool_results["get_current_risk"]
        if risk.get("authorized") is False:
            bits.append(risk["reason"])
        else:
            bits.append(
                f"Current modeled risk category is {risk.get('category')} "
                f"(P={_copy_num(risk.get('probability'))}, E={_copy_num(risk.get('exposure'))}, "
                f"S={_copy_num(risk.get('severity'))}). CONFIDENCE: NOT_CALIBRATED."
            )
    if "explain_forecast" in tool_results:
        fc = tool_results["explain_forecast"]
        if fc.get("authorized") is not False:
            bits.append(
                f"METHOD: HEURISTIC. The heuristic is not trained from data. "
                f"CONFIDENCE: NOT_CALIBRATED (heuristic decay is not calibrated confidence)."
            )
            horizons = fc.get("horizons") or []
            h24 = next((p for p in horizons if p.get("horizon_hours") == 24), None)
            if h24 and h24.get("flood_probability") is not None:
                bits.append(f"24h flood_probability={_copy_num(h24.get('flood_probability'))}.")
    elif "get_forecast" in tool_results:
        fc = tool_results["get_forecast"]
        if fc.get("authorized") is False:
            bits.append(fc["reason"])
        else:
            horizons = fc.get("horizons") or []
            h24 = next((p for p in horizons if p.get("horizon_hours") == 24), None)
            if h24 and h24.get("flood_probability") is not None:
                bits.append(
                    f"24h METHOD: {fc.get('model_kind', 'HEURISTIC')} flood_probability="
                    f"{_copy_num(h24['flood_probability'])}. CONFIDENCE: NOT_CALIBRATED."
                )
            elif h24:
                bits.append(
                    f"24h expected_depth={_copy_num(h24.get('expected_depth'))} "
                    f"data_status={h24.get('data_status')}."
                )
            else:
                bits.append(fc.get("reason") or "Forecast product unavailable.")
    if "get_flood_extent" in tool_results:
        ext = tool_results["get_flood_extent"]
        if ext.get("available"):
            bits.append(
                f"Flood extent max_depth_m={_copy_num(ext['max_depth_m'])} "
                f"flooded_area_km2={_copy_num(ext['flooded_area_km2'])} (threshold {ext['threshold_m']} m)."
            )
        else:
            bits.append(ext.get("reason", "Flood extent unavailable."))
    if "get_river_forecast" in tool_results:
        rf = tool_results["get_river_forecast"]
        bits.append(
            rf.get("reason")
            or (
                f"WATER LEVEL: {_copy_num(rf.get('water_level_m'))}. "
                f"DISCHARGE: {_copy_num(rf.get('discharge_m3s'))}."
            )
        )
    if "get_river_status" in tool_results:
        rs = tool_results["get_river_status"]
        if rs.get("available"):
            river = rs.get("river") or {}
            bits.append(
                f"River {river.get('name') or rs.get('river_id') or compact.get('selected_river')}. "
                f"Flow direction {rs.get('flow_direction_status')}. "
                "Direction is not inferred from line ordering."
            )
        else:
            bits.append(rs.get("reason") or "River UNAVAILABLE.")
    if "get_river_neighbors" in tool_results:
        nb = tool_results["get_river_neighbors"]
        if nb.get("available"):
            bits.append(
                f"Upstream segments={len(nb.get('upstream') or [])} "
                f"downstream segments={len(nb.get('downstream') or [])} (NETWORK TOPOLOGY only)."
            )
        else:
            bits.append(nb.get("reason") or "River neighbors UNAVAILABLE.")
    if "get_infrastructure_risk" in tool_results:
        infra = tool_results["get_infrastructure_risk"]
        if infra.get("available"):
            bits.append(f"Hospital/clinic flood flags from impact tool: {infra.get('flooded_counts')}.")
        else:
            bits.append(infra.get("reason") or "Infrastructure flood flags NOT_COMPUTED.")
    if "get_impact" in tool_results:
        impact = tool_results["get_impact"]
        cats = impact.get("categories") or {}
        hospitals = cats.get("hospitals") or {}
        schools = cats.get("schools") or {}
        roads = cats.get("roads") or {}
        bits.append(
            f"Hospitals affected={_copy_num(hospitals.get('affected'))} "
            f"schools affected={_copy_num(schools.get('affected'))} "
            f"roads status={roads.get('status') or 'UNAVAILABLE'}."
        )
    if "get_shelters" in tool_results:
        shelters = tool_results["get_shelters"]
        bits.append(
            "Shelters are not labeled globally safe. "
            f"FLOOD EXPOSURE listed separately. ACCESSIBILITY: {shelters.get('accessibility_status')}. "
            f"CAPACITY: {shelters.get('capacity_status')}. OCCUPANCY: {shelters.get('occupancy_status')}."
        )
    if "get_population_exposure" in tool_results:
        pop = tool_results["get_population_exposure"]
        bits.append(pop.get("reason") or "POPULATION EXPOSURE: UNAVAILABLE.")
    if "get_data_source" in tool_results:
        catalog = tool_results["get_data_source"]
        labels = [f"{row['title']}={row['data_status']}" for row in catalog.get("sources", [])]
        bits.append("Data sources (from tools): " + "; ".join(labels) + ".")
    if "get_data_freshness" in tool_results:
        fresh = tool_results["get_data_freshness"]
        bits.append(
            f"Rainfall freshness is {fresh.get('rainfall_freshness')} "
            f"with data_status={fresh.get('rainfall_data_status')} "
            f"(fallback_used={fresh.get('rainfall_fallback_used')})."
        )
    if "get_historical_event" in tool_results:
        ev = tool_results["get_historical_event"]
        if ev.get("available"):
            event = ev.get("event") or {}
            bits.append(
                f"Historical event {ev.get('event_id')} start={event.get('start')} peak={event.get('peak')} "
                f"end={event.get('end')} n_observations={ev.get('n_observations')} "
                f"data_status={event.get('data_status')}. COMPARISON: {ev.get('comparison')}."
            )
            if ev.get("comparison") != "COMPARABLE":
                bits.append(ev.get("comparison_reason") or "Forecast-vs-reality is unavailable.")
        else:
            bits.append(ev.get("reason") or "Historical event UNAVAILABLE.")
    if "get_historical_events" in tool_results:
        hist = tool_results["get_historical_events"]
        bits.append(hist.get("reason") or "Historical catalog listed; observed rasters are not invented.")
    if "get_model_performance" in tool_results:
        perf = tool_results["get_model_performance"]
        metrics = perf.get("metrics") or {}
        bits.append(
            f"MODEL {perf.get('model_id')} task={perf.get('task')} "
            f"AUPRC={_copy_num(metrics.get('auprc'))} Brier={_copy_num(metrics.get('brier'))} "
            f"IoU={_copy_num(metrics.get('iou'))} n_test={_copy_num(metrics.get('n_test_samples'))} "
            f"horizon={metrics.get('horizon')} target={metrics.get('target')} "
            f"accuracy_claim=null. SPATIAL AI: {(perf.get('spatial_ai') or {}).get('status')}."
        )
    if "compare_forecast_vs_reality" in tool_results:
        cmp = tool_results["compare_forecast_vs_reality"]
        bits.append(
            f"FORECAST VS REALITY: {cmp.get('comparison')}. "
            f"{cmp.get('reason') or 'See tool JSON for compatibility reasons.'}"
        )
    if "get_error_analysis" in tool_results:
        err = tool_results["get_error_analysis"]
        if err.get("available"):
            bits.append("Error analysis available for a compatible prediction/observation pair.")
        else:
            bits.append(err.get("reason") or "Error analysis UNAVAILABLE.")
    if "get_spectral_radius" in tool_results:
        jac = tool_results["get_spectral_radius"]
        bits.append(
            f"Local Jacobian spectral radius={_copy_num(jac.get('spectral_radius'))} "
            f"status={jac.get('status')}. NOT a global stability proof."
        )
    if "get_equilibrium_residual" in tool_results:
        eq = tool_results["get_equilibrium_residual"]
        bits.append(f"Equilibrium residual status={eq.get('status')} value={eq.get('value')}.")
    if "get_lake_at_rest_status" in tool_results:
        lake = tool_results["get_lake_at_rest_status"]
        bits.append(f"Lake-at-Rest status={lake.get('status')} passed={lake.get('passed')}.")
    if "get_nyquist_energy" in tool_results:
        nq = tool_results["get_nyquist_energy"]
        bits.append(
            f"Nyquist-mode energy ratio={_copy_num(nq.get('nyquist_energy_ratio'))} "
            f"unstable_classified={nq.get('unstable_classified')}."
        )
    if "get_run_failure" in tool_results:
        fail = tool_results["get_run_failure"]
        bits.append(f"Diagnostic failure: {fail.get('status')} {fail.get('reason')}.")
    if "generate_research_report" in tool_results:
        rr = tool_results["generate_research_report"]
        bits.append(f"Research report {rr.get('id')} status={((rr.get('body') or {}).get('pass_fail'))}. SNAPSHOT.")
    if "generate_report" in tool_results:
        report = tool_results["generate_report"]
        if report.get("authorized") is False:
            bits.append(report["reason"])
        else:
            bits.append(f"Report {report.get('id')} generated at {report.get('generated_at')}. SNAPSHOT.")
    if "share_analysis" in tool_results:
        share = tool_results["share_analysis"]
        if share.get("authorized") is False:
            bits.append(share["reason"])
        else:
            bits.append(
                f"SHARE {share.get('share_id')} {share.get('banner')} live={share.get('live')}."
            )
    if role == "researcher":
        bits.append("RESEARCH: formula/method labels above are RULE_FORMULA or HEURISTIC, not model attribution.")
    if role == "admin":
        bits.append("ADMIN: spatial AI remains NOT_VALIDATED; solver unmodified.")
    return " ".join(bits)


def _scenario_block(tool_results: dict, multiplier: Optional[float]) -> str:
    job = tool_results.get("run_scenario") or {}
    if job.get("authorized") is False:
        return (
            f"SCENARIO Tool run_scenario denied ({job.get('permission')}). "
            "RESULT not executed. LIMITATIONS Natural language cannot bypass jobs.write."
        )
    result = job.get("result") or {}
    bits = ["SCENARIO"]
    if multiplier is not None:
        bits.append(f"Requested rainfall_multiplier={_copy_num(multiplier)}.")
    if job.get("status") == "failed" or job.get("available") is False:
        bits.append(
            f"SIMULATION FAILED job={job.get('id')} error={job.get('error')}. "
            "Do not treat this as a completed flood map. Suggested next action: provide rainfall forcing or inspect job error."
        )
        return " ".join(bits)
    bits.append(
        f"RESULT Physics job {job.get('id')} status={job.get('status')} "
        f"rainfall_multiplier={_copy_num(result.get('rainfall_multiplier'))} "
        f"rainfall_rate_base_mps={_copy_num(result.get('rainfall_rate_base_mps'))} "
        f"rainfall_rate_applied_mps={_copy_num(result.get('rainfall_rate_applied_mps'))} "
        f"max_depth_m={_copy_num(result.get('max_depth_m'))} "
        f"flooded_area_km2={_copy_num(result.get('flooded_area_km2'))} "
        f"river_level_applied_to_solver={_copy_num(result.get('river_level_applied_to_solver', False))} "
        f"population_exposed=null. SIMULATED physics output, not a live flood map. "
        "River-level forcing is not applied to the SWE solver."
    )
    cmp = tool_results.get("compare_scenarios") or {}
    diff = cmp.get("difference")
    if diff:
        bits.append(
            f"CHANGE depth delta={_copy_num(diff.get('max_depth_m'))} m, "
            f"area delta={_copy_num(diff.get('flooded_area_km2'))} km2, population_exposed=null."
        )
    else:
        bits.append("CHANGE Scenario compare did not have two completed jobs.")
    impact = tool_results.get("get_impact") or {}
    if impact:
        hospitals = (impact.get("categories") or {}).get("hospitals") or {}
        bits.append(f"IMPACT hospitals affected={_copy_num(hospitals.get('affected'))}. Population UNAVAILABLE.")
    else:
        bits.append("IMPACT not requested in this turn.")
    bits.append("LIMITATIONS Unsupported parameters remain unsupported. River-level parameter remains uncoupled.")
    return " ".join(bits)


def _planning_block(tool_results: dict, role: str) -> str:
    plan = tool_results.get("get_planning_priorities") or {}
    if plan.get("authorized") is False:
        return f"PRIORITY Tool denied ({plan.get('permission')})."
    bits = [
        "PRIORITY AI-GENERATED PLANNING SUPPORT. Potential planning priority only. "
        "Review with official emergency guidance. Not an official evacuation order."
    ]
    for row in (plan.get("priorities") or [])[:4]:
        bits.append(
            f"WHAT {row.get('what')} WHY {row.get('why')} "
            f"EVIDENCE {row.get('evidence')} LIMITATIONS {row.get('limitations')} "
            f"data_status={row.get('data_status')} priority={row.get('priority')}."
        )
    inventory = plan.get("inventory") or {}
    bits.append("RESOURCE INVENTORY: UNAVAILABLE for boats, workers, medical teams, pumps, food, water.")
    if inventory:
        bits.append("Observed inventory values remain null; quantities are not invented.")
    if role == "general":
        bits.append("GENERAL: this is a simple planning summary, not an operational assignment.")
    return " ".join(bits)


def _evidence_text(tool_results: dict) -> str:
    parts = []
    for name, payload in tool_results.items():
        if not isinstance(payload, dict):
            continue
        job_id = payload.get("id") or payload.get("job_id")
        status = payload.get("data_status") or (payload.get("provenance") or {}).get("data_status")
        parts.append(f"{name} job_id={job_id or 'none'} data_status={status or 'see tool JSON'}")
    return "; ".join(parts) if parts else "see tool_results"


def _source_text(tool_results: dict, compact: dict) -> str:
    bits = [f"application region={compact.get('selected_region')} river={compact.get('selected_river')}"]
    if "get_data_source" in tool_results:
        bits.append("catalog sources listed in tool JSON (no invented URLs)")
    return "; ".join(bits)
