"""River state from the existing graph. Discharge is never invented."""

from __future__ import annotations

from floodlens.application.data_contracts import envelope
from floodlens.application.platform_store import get_platform_store
from floodlens.application.rivers import river_status


def river_state(river_id: str) -> dict:
    status = river_status(river_id)
    store = get_platform_store()
    segments = [s for s in store.river_segments.values() if s["river_id"] == river_id]
    upstream = sorted({s["from_node"] for s in segments})
    downstream = sorted({s["to_node"] for s in segments})
    series = status.get("series") or []
    available = [row for row in series if row.get("available")]
    trend = None
    if len(available) >= 2 and available[-1].get("water_level_m") is not None:
        a = available[-2].get("water_level_m")
        b = available[-1].get("water_level_m")
        if a is not None and b is not None:
            if b > a:
                trend = "rising"
            elif b < a:
                trend = "falling"
            else:
                trend = "steady"
    current = available[-1] if available else (series[-1] if series else None)
    return {
        "river": status["river"],
        "graph": status["graph"],
        "current": {
            "water_level_m": current.get("water_level_m") if current else None,
            "discharge_m3s": current.get("discharge_m3s") if current else None,
            "available": bool(current and current.get("available")),
            "t": current.get("t") if current else None,
        },
        "trend": trend,
        "forecast": {
            "available": False,
            "reason": "No documented river forecast model. Discharge/level forecast is UNAVAILABLE.",
        },
        "upstream": {"nodes": upstream, "influence": None, "note": "Topology only; no hydraulic routing."},
        "downstream": {"nodes": downstream, "influence": None, "note": "Topology only; no hydraulic routing."},
        "thresholds": {"flood_threshold_m": status.get("flood_threshold_m"), "time_to_threshold": None},
        "series": series,
        "note": status.get("note"),
        "provenance": status.get("provenance")
        or envelope(
            data_status="UNAVAILABLE",
            provider="river-gauge",
            dataset="water_level",
            freshness="UNAVAILABLE",
        ),
    }
