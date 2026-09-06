"""In-app alerts with explicit metric availability and a state machine.

UNAVAILABLE is never classified as FALSE. Only in-app delivery is implemented.
"""

from __future__ import annotations

import math
from typing import Optional

from floodlens.application.forecast import forecast_for_city
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat
from floodlens.application.rate_limit import check_rate
from floodlens.application.risk import risk_for_city

OPERATORS = ("gt", "gte", "lt", "lte", "eq")
CHANNELS = ("in-app",)
PREPARED_CHANNELS = ("email", "push")
STATES = ("ARMED", "TRIGGERED", "ACKNOWLEDGED", "RESET")
KINDS = ("personal", "operational", "experiment", "system")
ROLE_KINDS = {
    "general": {"personal"},
    "emergency": {"personal", "operational"},
    "researcher": {"personal", "experiment"},
    "admin": set(KINDS),
}

# Catalog: supported only when a legitimate product exists.
METRIC_CATALOG = {
    "flood_probability": {
        "supported": True,
        "units": "probability 0-1",
        "source": "heuristic risk/forecast (DEMO, NOT_CALIBRATED)",
        "value_type": "number",
    },
    "risk_score": {
        "supported": True,
        "units": "0-1",
        "source": "P×E×S heuristic",
        "value_type": "number",
    },
    "risk_level": {
        "supported": True,
        "units": "LOW|MODERATE|HIGH|CRITICAL",
        "source": "P×E×S category",
        "value_type": "category",
    },
    "forecast_confidence": {
        "supported": True,
        "units": "heuristic 0-1",
        "source": "HEURISTIC forecast confidence (NOT_CALIBRATED)",
        "value_type": "number",
        "note": "Heuristic decay, not calibrated model confidence.",
    },
    "rainfall_mm": {
        "supported": "conditional",
        "units": "mm",
        "source": "ingested precipitation observations",
        "value_type": "number",
    },
    "river_level": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: no gauge water level is ingested.",
        "value_type": "number",
    },
    "water_level": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: no gauge water level is ingested.",
        "value_type": "number",
    },
    "discharge": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: no discharge series is ingested.",
        "value_type": "number",
    },
    "flood_depth": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: expected_depth is null on the heuristic product.",
        "value_type": "number",
    },
    "population": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: population exposure is not ingested.",
        "value_type": "number",
    },
    "infrastructure_exposure": {
        "supported": False,
        "reason": "METRIC UNAVAILABLE: no numeric infrastructure-exposure threshold product.",
        "value_type": "number",
    },
}

CONDITION_ALIASES = {
    "flood_probability": "flood_probability",
    "risk": "risk_score",
    "risk_score": "risk_score",
    "risk_level": "risk_level",
    "rainfall": "rainfall_mm",
    "rainfall_mm": "rainfall_mm",
    "forecast_confidence": "forecast_confidence",
    "confidence": "forecast_confidence",
    "river_level": "river_level",
    "water_level": "water_level",
    "discharge": "discharge",
    "flood_depth": "flood_depth",
    "depth": "flood_depth",
    "population": "population",
    "infrastructure_exposure": "infrastructure_exposure",
}

CATEGORY_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}


class AlertError(Exception):
    def __init__(self, message: str, code: str = "INVALID"):
        super().__init__(message)
        self.code = code
        self.message = message


def metric_catalog() -> dict:
    rows = []
    for metric_id, meta in METRIC_CATALOG.items():
        rows.append({"metric": metric_id, **meta})
    return {
        "metrics": rows,
        "operators": list(OPERATORS),
        "channels": {"implemented": list(CHANNELS), "prepared_not_implemented": list(PREPARED_CHANNELS)},
        "states": list(STATES),
        "kinds": list(KINDS),
        "safety": (
            "Alerts describe threshold crossings of configured metrics. "
            "They are not official flood declarations or evacuation orders."
        ),
    }


def _normalize_metric(name: str) -> str:
    key = str(name or "").strip().lower().replace(" ", "_")
    if key not in CONDITION_ALIASES:
        raise AlertError(f"Unknown metric {name}", "UNKNOWN_METRIC")
    return CONDITION_ALIASES[key]


def _finite_number(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AlertError("Threshold must be a finite number", "MALFORMED_THRESHOLD") from exc
    if not math.isfinite(number):
        raise AlertError("NaN/infinity thresholds are rejected", "MALFORMED_THRESHOLD")
    return number


def read_metric(city_id: str, metric: str, river_id: Optional[str] = None) -> dict:
    metric_id = _normalize_metric(metric)
    meta = METRIC_CATALOG[metric_id]
    if meta.get("supported") is False:
        return {
            "metric": metric_id,
            "available": False,
            "status": "UNAVAILABLE",
            "value": None,
            "reason": meta.get("reason") or "METRIC UNAVAILABLE",
            "source": None,
            "freshness": "UNAVAILABLE",
        }
    if metric_id == "rainfall_mm":
        store = get_platform_store()
        rain = store.observations_for("precipitation_mm", city_id)
        if not rain:
            return {
                "metric": metric_id,
                "available": False,
                "status": "UNAVAILABLE",
                "value": None,
                "reason": "METRIC UNAVAILABLE: no precipitation observations ingested.",
                "source": None,
                "freshness": "UNAVAILABLE",
            }
        latest = rain[-1]
        return {
            "metric": metric_id,
            "available": True,
            "status": "STALE" if latest.get("simulated") else "DEMO",
            "value": float(latest["value"]),
            "source": latest.get("source") or "precipitation",
            "freshness": "demo" if latest.get("simulated") else "recent",
            "observed_at": latest.get("observed_at"),
            "unit": "mm",
        }
    risk = risk_for_city(city_id)
    forecast = forecast_for_city(city_id)
    horizon = next((h for h in (forecast.get("horizons") or []) if h.get("horizon_hours") == 24), None)
    provenance = risk.get("provenance") or forecast.get("provenance") or {}
    freshness = str(provenance.get("freshness") or "demo")
    if freshness.lower() == "live":
        freshness = "demo"
    status = "DEMO" if provenance.get("simulated", True) else (provenance.get("data_status") or "PARTIAL")
    if metric_id == "flood_probability":
        value = (horizon or {}).get("flood_probability")
        if value is None:
            value = risk.get("probability")
        return {
            "metric": metric_id,
            "available": value is not None,
            "status": "UNAVAILABLE" if value is None else status,
            "value": value,
            "source": forecast.get("model_id") or "heuristic-forecast",
            "freshness": freshness,
            "unit": "probability",
            "note": "Heuristic DEMO product. Not an official flood declaration.",
        }
    if metric_id == "risk_score":
        return {
            "metric": metric_id,
            "available": risk.get("score") is not None,
            "status": status,
            "value": risk.get("score"),
            "source": "risk-service",
            "freshness": freshness,
            "unit": "score",
        }
    if metric_id == "risk_level":
        return {
            "metric": metric_id,
            "available": bool(risk.get("category")),
            "status": status,
            "value": risk.get("category"),
            "source": "risk-service",
            "freshness": freshness,
            "unit": "category",
        }
    if metric_id == "forecast_confidence":
        value = (horizon or {}).get("confidence")
        return {
            "metric": metric_id,
            "available": value is not None,
            "status": "UNAVAILABLE" if value is None else status,
            "value": value,
            "source": "HEURISTIC",
            "freshness": freshness,
            "unit": "heuristic",
            "note": "NOT_CALIBRATED. Heuristic decay is not model confidence.",
        }
    return {
        "metric": metric_id,
        "available": False,
        "status": "UNAVAILABLE",
        "value": None,
        "reason": "METRIC UNAVAILABLE",
        "source": None,
        "freshness": "UNAVAILABLE",
    }


def _compare(value, operator: str, threshold, value_type: str) -> Optional[bool]:
    if value is None or threshold is None:
        return None
    if value_type == "category":
        left = CATEGORY_ORDER.get(str(value).upper())
        right = CATEGORY_ORDER.get(str(threshold).upper())
        if left is None or right is None:
            return str(value).upper() == str(threshold).upper() if operator == "eq" else None
        mapping = {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right, "eq": left == right}
        return mapping.get(operator)
    try:
        left = float(value)
        right = float(threshold)
    except (TypeError, ValueError):
        return None
    mapping = {
        "gt": left > right,
        "gte": left >= right,
        "lt": left < right,
        "lte": left <= right,
        "eq": left == right,
    }
    return mapping.get(operator)


def create_alert(
    owner: str,
    role: str,
    city_id: str,
    condition: str,
    threshold,
    channel: str = "in-app",
    operator: str = "gte",
    location_id: Optional[str] = None,
    kind: str = "personal",
    user_id: Optional[str] = None,
) -> dict:
    """Create an alert. `user_id` from the client is ignored."""
    check_rate(owner, "alert.create")
    if channel in PREPARED_CHANNELS:
        raise AlertError(f"{channel} delivery is not implemented. Use in-app.", "CHANNEL_NOT_IMPLEMENTED")
    if channel not in CHANNELS:
        raise AlertError("Only in-app channel is implemented", "CHANNEL_NOT_IMPLEMENTED")
    op = (operator or "gte").lower()
    if op not in OPERATORS:
        raise AlertError(f"Invalid operator {operator}", "INVALID_OPERATOR")
    alert_kind = (kind or "personal").lower()
    allowed = set(KINDS) if role == "admin" else ROLE_KINDS.get(role, {"personal"})
    if alert_kind not in allowed:
        raise AlertError(f"Role {role} cannot create {alert_kind} alerts", "FORBIDDEN_KIND")
    metric_id = _normalize_metric(condition)
    meta = METRIC_CATALOG[metric_id]
    reading = read_metric(city_id, metric_id)
    if meta.get("supported") is False or not reading.get("available"):
        raise AlertError(reading.get("reason") or "METRIC UNAVAILABLE", "METRIC_UNAVAILABLE")
    if location_id:
        store = get_platform_store()
        place = store.places.get(location_id)
        if not place:
            raise AlertError("location does not exist", "LOCATION_NOT_FOUND")
        if place.get("owner") != owner:
            raise AlertError("location does not exist", "LOCATION_NOT_FOUND")
    if meta.get("value_type") == "category":
        if str(threshold).upper() not in CATEGORY_ORDER:
            raise AlertError("risk_level threshold must be LOW, MODERATE, HIGH, or CRITICAL", "MALFORMED_THRESHOLD")
        stored_threshold = str(threshold).upper()
    else:
        stored_threshold = _finite_number(threshold)
        if metric_id in {"flood_probability", "risk_score", "forecast_confidence"}:
            if stored_threshold < 0 or stored_threshold > 1:
                raise AlertError("probability/score threshold must be in [0, 1]", "MALFORMED_THRESHOLD")
    store = get_platform_store()
    return store.put_alert(
        {
            "owner": owner,
            "user_id": owner,
            "role": role,
            "kind": alert_kind,
            "city_id": city_id,
            "location_id": location_id,
            "condition": metric_id,
            "metric": metric_id,
            "operator": op,
            "threshold": stored_threshold,
            "channel": channel,
            "active": True,
            "state": "ARMED",
            "acknowledged": False,
            "last_evaluation": None,
        }
    )


def _record_event(alert: dict, evaluation: dict) -> None:
    store = get_platform_store()
    store.put_alert_event(
        {
            "alert_id": alert["id"],
            "owner": alert.get("owner"),
            "trigger_time": isoformat(),
            "metric": alert.get("metric") or alert.get("condition"),
            "threshold": alert.get("threshold"),
            "actual_value": evaluation.get("value"),
            "source": evaluation.get("source"),
            "status": evaluation.get("condition_status"),
            "state": alert.get("state"),
            "acknowledged": bool(alert.get("acknowledged")),
        }
    )


def evaluate_alert(alert: dict) -> dict:
    reading = read_metric(alert["city_id"], alert.get("metric") or alert.get("condition"))
    meta = METRIC_CATALOG.get(reading["metric"]) or {}
    if not reading.get("available"):
        condition_status = "UNAVAILABLE"
        matched = None
    else:
        matched = _compare(reading.get("value"), alert.get("operator") or "gte", alert.get("threshold"), meta.get("value_type") or "number")
        if matched is None:
            condition_status = "ERROR"
        elif matched:
            condition_status = "CURRENTLY_TRUE"
        else:
            condition_status = "CURRENTLY_FALSE"
        if reading.get("status") == "STALE" and condition_status == "CURRENTLY_TRUE":
            condition_status = "STALE"
    previous = alert.get("state") or "ARMED"
    transition = None
    if condition_status == "UNAVAILABLE":
        # Do not treat as FALSE and do not trigger.
        pass
    elif condition_status == "CURRENTLY_TRUE" and previous == "ARMED":
        alert["state"] = "TRIGGERED"
        alert["acknowledged"] = False
        transition = "ARMED->TRIGGERED"
        _record_event(alert, {**reading, "condition_status": condition_status})
    elif condition_status in {"CURRENTLY_FALSE"} and previous in {"TRIGGERED", "ACKNOWLEDGED"}:
        alert["state"] = "RESET"
        transition = f"{previous}->RESET"
        _record_event(alert, {**reading, "condition_status": condition_status})
        alert["state"] = "ARMED"
        alert["acknowledged"] = False
        transition = f"{transition}->ARMED"
    alert["last_evaluation"] = {
        "at": isoformat(),
        "condition_status": condition_status,
        "value": reading.get("value"),
        "status": reading.get("status"),
    }
    alert["updated_at"] = isoformat()
    message = None
    if alert.get("state") == "TRIGGERED":
        message = (
            f"{reading.get('metric')} exceeded your configured threshold. "
            "This is a threshold notice, not a declaration that a flood is definitely happening. "
            "Not an official evacuation order."
        )
    return {
        **alert,
        "condition_status": condition_status,
        "current_value": reading.get("value") if reading.get("available") else None,
        "actual_value": reading.get("value") if reading.get("available") else None,
        "actual_value_status": "UNAVAILABLE" if not reading.get("available") else reading.get("status"),
        "source": reading.get("source"),
        "transition": transition,
        "message": message,
        "data_status": reading.get("status") or "UNAVAILABLE",
    }


def evaluate_alerts(city_id: str, owner: Optional[str] = None) -> list:
    store = get_platform_store()
    fired = []
    for alert in store.alerts.values():
        if not alert.get("active") or alert.get("city_id") != city_id:
            continue
        if owner and alert.get("owner") not in {owner, None}:
            # Legacy alerts without owner still evaluate for tests.
            if alert.get("owner"):
                continue
        row = evaluate_alert(alert)
        if row.get("state") == "TRIGGERED" and row.get("transition") == "ARMED->TRIGGERED":
            fired.append(row)
        elif row.get("state") == "TRIGGERED" and not row.get("transition"):
            # Already triggered; do not spam fired list.
            pass
    return fired


def evaluate_alerts_detailed(city_id: str, owner: Optional[str] = None) -> dict:
    store = get_platform_store()
    evaluations = []
    fired = []
    for alert in store.alerts.values():
        if not alert.get("active") or alert.get("city_id") != city_id:
            continue
        if owner and alert.get("owner") and alert.get("owner") != owner:
            continue
        row = evaluate_alert(alert)
        evaluations.append(row)
        if row.get("transition") == "ARMED->TRIGGERED":
            fired.append(row)
    return {"fired": fired, "evaluations": evaluations}


def list_alerts(owner: str) -> dict:
    store = get_platform_store()
    rows = [a for a in store.alerts.values() if a.get("owner") == owner]
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return {"alerts": rows, "n": len(rows)}


def acknowledge_alert(alert_id: str, owner: str) -> dict:
    store = get_platform_store()
    alert = store.alerts.get(alert_id)
    if not alert or alert.get("owner") != owner:
        raise KeyError(alert_id)
    if alert.get("state") == "TRIGGERED":
        alert["state"] = "ACKNOWLEDGED"
        alert["acknowledged"] = True
        alert["updated_at"] = isoformat()
        store.put_alert_event(
            {
                "alert_id": alert_id,
                "owner": owner,
                "trigger_time": isoformat(),
                "metric": alert.get("metric"),
                "threshold": alert.get("threshold"),
                "actual_value": (alert.get("last_evaluation") or {}).get("value"),
                "status": "ACKNOWLEDGED",
                "state": "ACKNOWLEDGED",
                "acknowledged": True,
            }
        )
    return alert


def alert_history(alert_id: str, owner: str) -> dict:
    store = get_platform_store()
    alert = store.alerts.get(alert_id)
    if not alert or alert.get("owner") != owner:
        raise KeyError(alert_id)
    events = [e for e in store.alert_events if e.get("alert_id") == alert_id]
    for event in events:
        if event.get("actual_value") is None:
            event["actual_value_display"] = "UNAVAILABLE"
    return {"alert": alert, "history": events, "n": len(events)}
