"""Meteorological-horizon forecast product. Independent of SWE simulation time."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from floodlens.application.canonical import ForecastPoint
from floodlens.application.data_contracts import envelope
from floodlens.application.provenance import FORECAST_MODEL_VERSION, demo_provenance, isoformat, utcnow
from floodlens.application.risk import categorize, risk_for_city

HORIZONS_H = (6, 12, 24, 48, 72)


class ForecastProvider(ABC):
    @abstractmethod
    def forecast(self, city_id: str) -> dict:
        raise NotImplementedError


def _horizon_probability(base: float, hours: int) -> float:
    growth = min(0.35, hours / 72.0 * 0.35)
    return min(0.95, base + growth)


class HeuristicForecastProvider(ForecastProvider):
    """Documented heuristic nowcast. Not a trained flood model."""

    model_id = FORECAST_MODEL_VERSION
    model_kind = "HEURISTIC"

    def forecast(self, city_id: str) -> dict:
        baseline = risk_for_city(city_id)
        generated = utcnow()
        points = []
        for hours in HORIZONS_H:
            probability = _horizon_probability(baseline["probability"], hours)
            severity = min(1.0, baseline["severity"] + hours / 240.0)
            score = probability * baseline["exposure"] * severity
            valid_at = isoformat(generated + timedelta(hours=hours))
            confidence = round(max(0.45, 0.9 - hours / 200.0), 3)
            point = ForecastPoint(
                horizon_hours=hours,
                timestamp=valid_at,
                valid_at=valid_at,
                generated_at=isoformat(generated),
                probability=round(probability, 3),
                severity=round(severity, 3),
                expected_depth=None,
                confidence=confidence,
                confidence_kind="heuristic",
                risk_category=categorize(score),
                model_id=self.model_id,
                data_status="DEMO",
            )
            row = point.to_dict()
            row["flood_probability"] = row["probability"]
            row["expected_severity"] = row["severity"]
            row["uncertainty"] = "moderate" if hours <= 24 else "high"
            row["uncertainty_sources"] = [
                "rainfall forecast uncertainty",
                "sparse observational data",
                "heuristic nowcast (not shallow-water hours)",
            ]
            points.append(row)
        simulated = True
        prov = demo_provenance("forecast-heuristic", FORECAST_MODEL_VERSION).to_dict()
        if baseline["provenance"]["freshness"] != "demo":
            prov = {
                **baseline["provenance"],
                "model_version": FORECAST_MODEL_VERSION,
                "simulated": True,
                "freshness": "demo",
            }
        envelope_meta = envelope(
            data_status="DEMO",
            provider="forecast-heuristic",
            dataset="flood-nowcast",
            freshness="SNAPSHOT",
            simulated=simulated,
            extra={"model_kind": self.model_kind, "model_id": self.model_id},
        )
        return {
            "city_id": city_id,
            "clock": "meteorological_hours",
            "not_simulation_time": True,
            "baseline_risk": baseline,
            "horizons": points,
            "model_kind": self.model_kind,
            "model_id": self.model_id,
            "provenance": {**prov, **{k: v for k, v in envelope_meta.items() if k not in prov}},
            "disclaimer": (
                "Forecast horizons are meteorological hours from a documented heuristic "
                "nowcast. They are not equal to shallow-water solver seconds. "
                "confidence is a heuristic score (confidence_kind=heuristic), not a calibrated probability. "
                "expected_depth is null until a physics/AI product computes it."
            ),
        }


class PhysicsForecastProvider(ForecastProvider):
    def forecast(self, city_id: str) -> dict:
        from floodlens.application.physics_forecast import PhysicsBaselineForecastProvider

        return PhysicsBaselineForecastProvider().forecast(city_id, allow_synthetic_dem=True)


class AIModelForecastProvider(ForecastProvider):
    def forecast(self, city_id: str) -> dict:
        from floodlens.application.ai_forecast import AIModelForecastProvider as _Provider

        return _Provider().forecast(city_id)


def forecast_for_city(city_id: str) -> dict:
    from floodlens.application.physics_forecast import latest_forecast_for_city

    return latest_forecast_for_city(city_id)
