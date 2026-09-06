"""Transparent flood risk: Risk = Probability × Exposure × Severity."""

from __future__ import annotations

from typing import Optional

from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import FORMULA_ID, FORECAST_MODEL_VERSION, demo_provenance

RISK_THRESHOLDS = (
    (0.10, "LOW"),
    (0.30, "MODERATE"),
    (0.60, "HIGH"),
    (1.01, "CRITICAL"),
)


def categorize(score: float) -> str:
    for upper, label in RISK_THRESHOLDS:
        if score < upper:
            return label
    return "CRITICAL"


def compute_risk(
    probability: float,
    exposure: float,
    severity: float,
    city_id: str,
    drivers: Optional[list] = None,
    provenance=None,
) -> dict:
    if min(probability, exposure, severity) < 0 or max(probability, exposure, severity) > 1:
        raise ValueError("probability, exposure, and severity must be in [0, 1]")
    score = float(probability) * float(exposure) * float(severity)
    return {
        "city_id": city_id,
        "formula_id": FORMULA_ID,
        "probability": probability,
        "exposure": exposure,
        "severity": severity,
        "score": score,
        "category": categorize(score),
        "drivers": drivers or [],
        "provenance": (provenance or demo_provenance("risk-service", FORECAST_MODEL_VERSION)).to_dict()
        if hasattr(provenance or demo_provenance("risk-service", FORECAST_MODEL_VERSION), "to_dict")
        else provenance,
    }


def risk_for_city(city_id: str) -> dict:
    """Heuristic P/E/S from rainfall observations when present; otherwise demo."""
    store = get_platform_store()
    rain = store.observations_for("precipitation_mm", city_id)
    if rain:
        latest = rain[-1]
        intensity = min(1.0, float(latest["value"]) / 20.0)
        probability = min(0.95, 0.2 + intensity * 0.7)
        severity = min(1.0, 0.3 + intensity * 0.5)
        exposure = 0.6 if city_id == "dhaka" else 0.4
        drivers = [
            {"name": "recent_precipitation", "value": latest["value"], "unit": "mm"},
            {"name": "low_elevation_basin", "qualitative": True},
        ]
        simulated = bool(latest.get("simulated", True))
        provenance = {
            "source": latest.get("source", "risk-service"),
            "timestamp": latest["observed_at"],
            "data_version": "platform-v1",
            "model_version": FORECAST_MODEL_VERSION,
            "freshness": "demo" if simulated else "recent",
            "simulated": simulated,
        }
        result = compute_risk(probability, exposure, severity, city_id, drivers, provenance)
        result["provenance"] = provenance
        return result

    result = compute_risk(
        probability=0.35,
        exposure=0.5,
        severity=0.4,
        city_id=city_id,
        drivers=[{"name": "no_observation_feed", "qualitative": True}],
    )
    result["note"] = "Heuristic demo risk; no precipitation observations ingested."
    return result


def risk_from_physics(city_id: str, flood_fraction: float, max_depth_m: float) -> dict:
    """Deterministic P×E×S from physics flood stats. Backend-owned; no frontend math.

    Normalization (documented):
    - probability = min(1, flood_fraction)  # wet-cell fraction at 0.05 m
    - severity = min(1, max_depth_m / 2.0)  # 2 m maps to severity 1
    - exposure = 0.6 for dhaka else 0.4 (same city prior as heuristic risk)
    """
    probability = min(1.0, max(0.0, float(flood_fraction)))
    severity = min(1.0, max(0.0, float(max_depth_m) / 2.0))
    exposure = 0.6 if city_id == "dhaka" else 0.4
    provenance = {
        "source": "physics-baseline-risk",
        "timestamp": None,
        "data_version": "platform-v1",
        "model_version": "PHYSICS-BASELINE-v0.1",
        "freshness": "demo",
        "simulated": True,
        "data_status": "SIMULATED",
        "normalization": {
            "probability": "min(1, flood_fraction)",
            "severity": "min(1, max_depth_m / 2.0)",
            "exposure": "city prior 0.6 dhaka / 0.4 other",
        },
    }
    result = compute_risk(probability, exposure, severity, city_id, [
        {"name": "flood_fraction", "value": flood_fraction},
        {"name": "max_depth_m", "value": max_depth_m, "unit": "m"},
    ], provenance)
    result["provenance"] = provenance
    result["risk_score"] = result["score"]
    result["risk_level"] = result["category"]
    return result
