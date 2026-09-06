"""Physics baseline forecast: SWE burst forced by Open-Meteo rainfall at each horizon."""

from __future__ import annotations

from datetime import timedelta

from floodlens.application.canonical import FloodForecast, ForecastPoint
from floodlens.application.data_contracts import envelope
from floodlens.application.forecast import HORIZONS_H, ForecastProvider, HeuristicForecastProvider
from floodlens.application.provenance import isoformat, utcnow
from floodlens.application.rainfall_service import rate_at_horizon_mps
from floodlens.application.repository import get_repository
from floodlens.application.risk import categorize, compute_risk, risk_from_physics
from floodlens.application.simulation_adapter import PHYSICS_BASELINE_MODEL_ID, run_physics


class PhysicsBaselineForecastProvider(ForecastProvider):
    model_id = PHYSICS_BASELINE_MODEL_ID
    model_kind = "PHYSICS_BASELINE"

    def forecast(self, city_id: str, allow_synthetic_dem: bool = False, **run_kwargs) -> dict:
        generated = utcnow()
        horizons = []
        snapshots = []
        any_ok = False
        rain_failed = False
        for hours in HORIZONS_H:
            forcing = rate_at_horizon_mps(city_id, hours)
            if not forcing.get("available"):
                rain_failed = True
                horizons.append(
                    {
                        "horizon_hours": hours,
                        "available": False,
                        "reason": forcing.get("reason") or "REAL rainfall unavailable",
                        "expected_depth": None,
                        "flood_probability": None,
                        "data_status": "UNAVAILABLE",
                    }
                )
                continue
            result = run_physics(
                city_id,
                forcing["rainfall_rate_mps"],
                horizon_hours=hours,
                valid_at=forcing.get("valid_at") or isoformat(generated + timedelta(hours=hours)),
                rain_snapshot_id=forcing.get("snapshot_id"),
                rain_data_status=forcing.get("data_status") or "DEMO",
                allow_synthetic_dem=allow_synthetic_dem,
                **run_kwargs,
            )
            if not result.get("available"):
                horizons.append(
                    {
                        "horizon_hours": hours,
                        "available": False,
                        "reason": result.get("reason"),
                        "expected_depth": None,
                        "data_status": "UNAVAILABLE",
                        "validation_status": result.get("validation_status"),
                    }
                )
                continue
            any_ok = True
            state = result["flood_state"]
            snapshots.extend(state.get("input_snapshot_ids") or [])
            risk = risk_from_physics(
                city_id,
                flood_fraction=state["flood_fraction"] or 0.0,
                max_depth_m=state["max_depth_m"] or 0.0,
            )
            point = ForecastPoint(
                horizon_hours=hours,
                timestamp=state["timestamp"],
                valid_at=state["valid_at"],
                generated_at=state["generated_at"],
                probability=risk["probability"],
                severity=risk["severity"],
                expected_depth=state["max_depth_m"],
                confidence=None,
                confidence_kind=None,
                risk_category=risk["category"],
                model_id=self.model_id,
                data_status=state["data_status"],
            )
            row = point.to_dict()
            row["flood_probability"] = row["probability"]
            row["expected_severity"] = row["severity"]
            row["expected_extent"] = state.get("expected_extent")
            row["flooded_area_km2"] = state.get("flooded_area_km2")
            row["artifact_id"] = result["artifact_id"]
            row["artifact_uri"] = result["artifact_uri"]
            row["validation_status"] = result["validation_status"]
            row["forcing_clock"] = "meteorological_hours"
            row["solver_clock"] = "simulation_seconds"
            row["available"] = True
            row["risk"] = risk
            horizons.append(row)

        data_status = "PARTIAL" if any_ok else "UNAVAILABLE"
        product = FloodForecast(
            city_id=city_id,
            model_kind=self.model_kind,
            model_id=self.model_id,
            generated_at=isoformat(generated),
            horizons=horizons,
            data_status=data_status,
            input_snapshot_ids=sorted(set(snapshots)),
            provenance=envelope(
                data_status=data_status,
                provider=self.model_id,
                dataset="flood-nowcast",
                freshness="SNAPSHOT",
                simulated=True,
                extra={"rain_unavailable": rain_failed},
            ),
        )
        payload = product.to_dict()
        payload["clock"] = "meteorological_hours"
        payload["not_simulation_time"] = True
        payload["available"] = any_ok
        payload["disclaimer"] = (
            "Physics Baseline v0.1 runs a short shallow-water burst forced by the rainfall "
            "valid at each meteorological horizon. Solver seconds are not forecast hours. "
            "This is not an ML model."
        )
        if rain_failed and not any_ok:
            payload["reason"] = "REAL rainfall unavailable"
        get_repository().put_forecast_run(payload)
        return payload


def latest_forecast_for_city(city_id: str) -> dict:
    stored = get_repository().get_latest_forecast(city_id)
    if stored and stored.get("horizons"):
        return stored
    return HeuristicForecastProvider().forecast(city_id)
