"""Command-center aggregates. Cards only include computed or explicitly unavailable fields."""

from __future__ import annotations

from floodlens.application.forecast import forecast_for_city
from floodlens.application.jobs import job_public_view
from floodlens.application.platform_store import get_platform_store
from floodlens.application.population import get_population_provider
from floodlens.application.risk import risk_for_city


def _public_job(job: dict | None) -> dict | None:
    if not job:
        return None
    view = job_public_view(job)
    view.pop("result", None)
    return view


def command_snapshot(city_id: str) -> dict:
    store = get_platform_store()
    risk = risk_for_city(city_id)
    forecast = forecast_for_city(city_id)
    h24 = next(p for p in forecast["horizons"] if p["horizon_hours"] == 24)
    jobs = [j for j in store.jobs.values() if j.get("city_id") == city_id]
    latest_job = jobs[-1] if jobs else None
    ingest = store.ingest_runs[-1] if store.ingest_runs else None
    pop = get_population_provider().expose(city_id)
    unavailable = [
        "expected_depth_m (needs completed physics artifact)",
        "time_to_peak",
        "hospitals_at_risk (run impact after a flood raster exists)",
        "roads_affected_km",
    ]
    if pop.get("population_exposed") is None:
        unavailable.insert(2, "population_exposed")
    return {
        "city_id": city_id,
        "current_risk": risk["category"],
        "flood_probability": risk["probability"],
        "forecast_24h_probability": h24["flood_probability"],
        "forecast_confidence": h24["confidence"],
        "expected_depth_m": None,
        "time_to_peak": None,
        "population_exposed": pop.get("population_exposed"),
        "population_status": pop.get("data_status") or ("UNAVAILABLE" if not pop.get("available") else "REAL"),
        "hospitals_at_risk": None,
        "roads_affected_km": None,
        "unavailable": unavailable,
        "latest_job": _public_job(latest_job),
        "data_freshness": ingest,
        "alerts_active": len([a for a in store.alerts.values() if a.get("active")]),
        "disclaimer": "Null operational KPIs are withheld rather than fabricated.",
    }
