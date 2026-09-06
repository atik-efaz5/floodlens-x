"""Rainfall service: OBSERVED vs FORECAST, documented uniform-field interpolation."""

from __future__ import annotations

from typing import List, Optional

from floodlens.application.canonical import RainfallForecast, RainfallObservation
from floodlens.application.data_contracts import envelope
from floodlens.application.repository import get_repository
from floodlens.application.runoff import precip_mm_to_mps, runoff_metadata


INTERPOLATION = "NEAREST_STATION"


def get_observed_rainfall(city_id: str) -> List[RainfallObservation]:
    return get_repository().list_rainfall(city_id, kind="OBSERVED")


def get_forecast_rainfall(city_id: str) -> List[RainfallForecast]:
    rows = get_repository().list_rainfall(city_id, kind="FORECAST")
    return [
        RainfallForecast(
            city_id=row.city_id,
            value_mm=row.value_mm,
            unit=row.unit,
            timestamp=row.observed_at,
            valid_at=row.valid_at,
            generated_at=row.retrieved_at,
            source=row.provider,
            data_status=row.data_status,
            interpolation=INTERPOLATION,
            lon=row.lon,
            lat=row.lat,
        )
        for row in rows
    ]


def get_rainfall_timeseries(city_id: str, kind: Optional[str] = None) -> dict:
    from floodlens.application.demo_fixtures import demo_fixtures_enabled, ensure_demo_rainfall

    overlay_id = None
    if demo_fixtures_enabled():
        seeded = ensure_demo_rainfall(city_id)
        overlay_id = seeded.get("overlay_artifact_id")
    if kind == "FORECAST":
        data = [r.to_dict() for r in get_forecast_rainfall(city_id)]
    elif kind == "OBSERVED":
        data = [r.to_dict() for r in get_observed_rainfall(city_id)]
    else:
        data = [r.to_dict() for r in get_repository().list_rainfall(city_id)]
    fallback = any(r.get("data_status") == "DEMO" for r in data)
    return {
        "data": data,
        "interpolation": INTERPOLATION,
        "interpolation_note": (
            "City-center / nearest-station value applied uniformly across the domain. "
            "This is not a radar or satellite precipitation grid."
        ),
        "provenance": envelope(
            data_status="DEMO" if fallback else ("REAL" if data else "UNAVAILABLE"),
            provider="Open-Meteo" if data else "none",
            dataset="precipitation",
            freshness="SNAPSHOT" if fallback else ("RECENT" if data else "UNAVAILABLE"),
            fallback_used=fallback,
            simulated=fallback,
            extra={"kind": kind, "interpolation": INTERPOLATION},
        ),
        "fallback_used": fallback,
        "overlay_artifact_id": overlay_id,
        "note": "DEMO point/uniform field. Not a radar grid." if fallback else None,
    }


def uniform_field_mps(city_id: str, kind: str, runoff_coefficient: float = 1.0) -> dict:
    """Single rainfall rate (m/s) for the whole domain from the latest sample of `kind`."""
    rows = get_repository().list_rainfall(city_id, kind=kind)
    if not rows:
        return {
            "available": False,
            "rainfall_rate_mps": None,
            "reason": "REAL rainfall unavailable" if kind == "OBSERVED" else "Forecast rainfall unavailable",
            "runoff": runoff_metadata(runoff_coefficient),
            "interpolation": INTERPOLATION,
        }
    latest = rows[-1]
    rate = precip_mm_to_mps(latest.value_mm, runoff_coefficient)
    return {
        "available": True,
        "rainfall_rate_mps": rate,
        "precip_mm": latest.value_mm,
        "valid_at": latest.valid_at,
        "source": latest.provider,
        "data_status": latest.data_status,
        "kind": latest.kind,
        "interpolation": INTERPOLATION,
        "runoff": runoff_metadata(runoff_coefficient),
        "snapshot_id": f"rain_{city_id}_{latest.kind}_{latest.valid_at}",
    }


def rate_at_horizon_mps(city_id: str, horizon_hours: int, runoff_coefficient: float = 1.0) -> dict:
    """Pick the FORECAST sample whose valid_at is closest after now+horizon, else last forecast."""
    forecasts = get_forecast_rainfall(city_id)
    if not forecasts:
        observed = uniform_field_mps(city_id, "OBSERVED", runoff_coefficient)
        if observed["available"]:
            observed["note"] = "No FORECAST series; using latest OBSERVED as forcing (labeled)."
            observed["kind"] = "OBSERVED"
        return observed
    idx = min(len(forecasts) - 1, max(0, horizon_hours // 6))
    row = forecasts[idx]
    return {
        "available": True,
        "rainfall_rate_mps": precip_mm_to_mps(row.value_mm, runoff_coefficient),
        "precip_mm": row.value_mm,
        "valid_at": row.valid_at,
        "source": row.source,
        "data_status": row.data_status,
        "kind": "FORECAST",
        "interpolation": INTERPOLATION,
        "runoff": runoff_metadata(runoff_coefficient),
        "snapshot_id": f"rain_{city_id}_FORECAST_{row.valid_at}",
        "horizon_hours": horizon_hours,
    }
