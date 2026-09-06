"""OSM/DEM/observation ingest. Network fetches are optional; fixtures always work."""

from __future__ import annotations

import json
from pathlib import Path

from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat

FIXTURE_PATH = Path(__file__).resolve().parent / "data" / "dhaka_osm.json"
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=23.81&longitude=90.41&hourly=precipitation"
    "&forecast_days=3&timezone=UTC"
)


def load_osm_fixture(city_id: str = "dhaka") -> dict:
    payload = json.loads(FIXTURE_PATH.read_text())
    if payload["city_id"] != city_id and city_id != "dhaka":
        payload = dict(payload)
        payload["city_id"] = city_id
        payload["source"] = "OpenStreetMap-style demo fixture (not a live extract)"
        payload["demo"] = True
    return payload


def ingest_osm_assets(city_id: str = "dhaka") -> dict:
    """Seed OSM if empty (fixture/overpass). Status endpoints use this to avoid repeat Overpass."""
    store = get_platform_store()
    existing = store.assets_for_city(city_id)
    if existing:
        return {"city_id": city_id, "assets": len(existing), "source": "already-ingested"}
    from floodlens.application.osm_ingest import ingest_osm

    return ingest_osm(city_id)


def fetch_open_meteo_precipitation(city_id: str = "dhaka") -> dict:
    from floodlens.application.meteo import fetch_open_meteo_precipitation as _fetch

    return _fetch(city_id)


def ingest_dem_metadata(city_id: str, bounds: dict) -> dict:
    """Record DEM catalog metadata. Raster bytes stay on disk / DEMManager."""
    from floodlens.application.terrain import ingest_terrain

    result = ingest_terrain(city_id, bounds)
    dataset = result.get("dataset") or {}
    artifact = {
        "id": dataset.get("id", f"dem-{city_id}"),
        "kind": "dem",
        "uri": dataset.get("uri", ""),
        "city_id": city_id,
        "bounds": dataset.get("bounds") or bounds,
        "crs": dataset.get("crs", "EPSG:4326"),
        "recorded_at": isoformat(),
        "source": dataset.get("source", "unconfigured"),
        "freshness": "unavailable" if not result.get("available") else "stale",
        "data_status": dataset.get("data_status", "UNAVAILABLE"),
        "simulated": False,
        "available": result.get("available", False),
        "note": result.get("reason") or result.get("note"),
        "provenance": result.get("provenance"),
        "min_elevation": dataset.get("min_elevation"),
        "max_elevation": dataset.get("max_elevation"),
        "nodata": dataset.get("nodata"),
        "version": dataset.get("version"),
        "resolution_deg": dataset.get("resolution_deg"),
    }
    get_platform_store().artifacts[artifact["id"]] = artifact
    return artifact
