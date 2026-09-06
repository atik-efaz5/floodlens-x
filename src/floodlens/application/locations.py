"""Owner-scoped saved locations. Restore context, not stale live results."""

from __future__ import annotations

from typing import Optional

from floodlens.application.city_data import create_city_registry
from floodlens.application.forecast import forecast_for_city
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat
from floodlens.application.rate_limit import check_rate
from floodlens.application.risk import risk_for_city

LOCATION_TYPES = (
    "city",
    "district",
    "region",
    "river",
    "research_area",
    "emergency_area",
    "coordinate",
)
LOCATION_LIMIT = 50
_CITIES = create_city_registry()


class LocationError(Exception):
    def __init__(self, message: str, code: str = "INVALID"):
        super().__init__(message)
        self.code = code


def _coords_for_city(city_id: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    if not city_id:
        return None, None
    try:
        city = _CITIES.get_city(city_id)
    except KeyError:
        return None, None
    return city.center_lat, city.center_lon


def create_location(
    owner: str,
    name: str,
    location_type: str = "city",
    city_id: Optional[str] = None,
    river_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    zoom: Optional[float] = None,
    layers: Optional[list] = None,
    alert_configuration: Optional[dict] = None,
) -> dict:
    check_rate(owner, "location.create")
    kind = (location_type or "city").strip().lower().replace(" ", "_")
    if kind == "district/region":
        kind = "region"
    if kind not in LOCATION_TYPES:
        raise LocationError(f"Unknown location_type {location_type}", "INVALID_TYPE")
    if not name or not str(name).strip():
        raise LocationError("name is required", "INVALID_NAME")
    lat, lon = latitude, longitude
    if lat is None or lon is None:
        clat, clon = _coords_for_city(city_id)
        lat = lat if lat is not None else clat
        lon = lon if lon is not None else clon
    store = get_platform_store()
    owned = [p for p in store.places.values() if p.get("owner") == owner]
    if len(owned) >= LOCATION_LIMIT:
        raise LocationError("Too many saved locations", "LIMIT")
    return store.put_place(
        {
            "name": str(name).strip(),
            "label": str(name).strip(),
            "location_type": kind,
            "city_id": city_id,
            "river_id": river_id,
            "latitude": lat,
            "longitude": lon,
            "lat": lat,
            "lon": lon,
            "zoom": zoom,
            "layers": list(layers) if layers else None,
            "owner": owner,
            "user_id": owner,
            "alert_configuration": alert_configuration,
        }
    )


def list_locations(owner: str, limit: int = LOCATION_LIMIT) -> dict:
    store = get_platform_store()
    rows = [p for p in store.places.values() if p.get("owner") == owner]
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    cap = min(max(int(limit), 1), LOCATION_LIMIT)
    return {"locations": rows[:cap], "n": min(len(rows), cap), "total": len(rows)}


def get_location(location_id: str, owner: str) -> dict:
    store = get_platform_store()
    row = store.places.get(location_id)
    if not row:
        raise KeyError(location_id)
    if row.get("owner") != owner:
        raise PermissionError("not owner")
    return row


def update_location(location_id: str, owner: str, **fields) -> dict:
    row = get_location(location_id, owner)
    allowed = {
        "name",
        "label",
        "location_type",
        "city_id",
        "river_id",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "zoom",
        "layers",
        "alert_configuration",
    }
    for key, value in fields.items():
        if key in allowed and value is not None:
            row[key] = value
            if key == "name":
                row["label"] = value
            if key == "latitude":
                row["lat"] = value
            if key == "longitude":
                row["lon"] = value
    row["updated_at"] = isoformat()
    return row


def delete_location(location_id: str, owner: str) -> dict:
    row = get_location(location_id, owner)
    store = get_platform_store()
    del store.places[location_id]
    return {"deleted": True, "id": location_id, "name": row.get("name")}


def restore_context(location_id: str, owner: str) -> dict:
    row = get_location(location_id, owner)
    return {
        "location_id": row["id"],
        "city_id": row.get("city_id"),
        "river_id": row.get("river_id"),
        "latitude": row.get("latitude") if row.get("latitude") is not None else row.get("lat"),
        "longitude": row.get("longitude") if row.get("longitude") is not None else row.get("lon"),
        "zoom": row.get("zoom"),
        "layers": row.get("layers"),
        "note": "Restores map/region context only. Does not replay stale result snapshots as live data.",
    }


def location_dashboard(owner: str) -> dict:
    listed = list_locations(owner)
    cards = []
    store = get_platform_store()
    for row in listed["locations"]:
        city_id = row.get("city_id")
        risk = forecast = None
        freshness = "UNAVAILABLE"
        data_status = "UNAVAILABLE"
        if city_id:
            try:
                risk = risk_for_city(city_id)
                forecast = forecast_for_city(city_id)
                prov = (risk.get("provenance") or {}) if risk else {}
                freshness = str(prov.get("freshness") or "UNAVAILABLE").upper()
                if freshness == "LIVE":
                    freshness = "DEMO"
                data_status = "DEMO" if prov.get("simulated") else (prov.get("data_status") or "PARTIAL")
            except Exception:
                risk = None
                forecast = None
        alerts = [
            a
            for a in store.alerts.values()
            if a.get("owner") == owner
            and (a.get("location_id") == row["id"] or a.get("city_id") == city_id)
        ]
        alert_status = alerts[0].get("state") if alerts else "NONE"
        horizon = None
        if forecast:
            horizon = next((h for h in (forecast.get("horizons") or []) if h.get("horizon_hours") == 24), None)
        cards.append(
            {
                "location_id": row["id"],
                "name": row.get("name") or row.get("label"),
                "location_type": row.get("location_type"),
                "city_id": city_id,
                "current_status": data_status,
                "risk": (risk or {}).get("category") if risk else "UNAVAILABLE",
                "risk_score": (risk or {}).get("score") if risk else None,
                "latest_forecast": (horizon or {}).get("flood_probability") if horizon else None,
                "forecast_status": (horizon or {}).get("data_status") if horizon else "UNAVAILABLE",
                "data_freshness": freshness if city_id else "UNAVAILABLE",
                "alert_status": alert_status,
                "last_updated": row.get("updated_at") or row.get("created_at"),
                "coordinates": {
                    "latitude": row.get("latitude") if row.get("latitude") is not None else row.get("lat"),
                    "longitude": row.get("longitude") if row.get("longitude") is not None else row.get("lon"),
                },
            }
        )
    return {"cards": cards, "n": len(cards)}
