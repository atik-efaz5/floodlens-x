"""OSM ingest: Overpass adapter + fixture adapter + validation."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from floodlens.application.canonical import InfrastructureRecord
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.ingest import load_osm_fixture
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat
from floodlens.application.rate_limit import OVERPASS_BUCKET
from floodlens.application.repository import get_repository
from floodlens.application.validation import validate_coordinates

LOGGER = logging.getLogger("floodlens.ingest.osm")

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

_TYPE_MAP = {
    "hospital": "hospital",
    "clinic": "clinic",
    "school": "school",
    "college": "school",
    "university": "school",
    "shelter": "shelter",
    "fire_station": "emergency",
    "police": "emergency",
    "ambulance": "emergency",
}


def validate_lon_lat(lon: float, lat: float) -> bool:
    try:
        validate_coordinates(lat, lon)
        return True
    except ValueError:
        return False


def normalize_osm_element(element: dict, city_id: str, data_status: str, retrieved_at: str) -> Optional[InfrastructureRecord]:
    tags = element.get("tags") or {}
    osm_id = str(element.get("id", ""))
    name = tags.get("name")  # may be None; never invent
    lon = element.get("lon")
    lat = element.get("lat")
    if lon is None or lat is None:
        center = element.get("center") or {}
        lon = center.get("lon")
        lat = center.get("lat")
    coords = None
    if element.get("type") == "way" and element.get("geometry"):
        coords = []
        for pt in element["geometry"]:
            if not validate_lon_lat(pt["lon"], pt["lat"]):
                continue
            coords.append([pt["lon"], pt["lat"]])
        if len(coords) < 2:
            coords = None
        elif lon is None and coords:
            lon, lat = coords[0]
    if lon is None or lat is None:
        if not coords:
            return None
    else:
        if not validate_lon_lat(float(lon), float(lat)):
            return None
        lon, lat = float(lon), float(lat)

    asset_type = _classify(tags, bool(coords) and not tags.get("amenity"))
    if not asset_type:
        return None
    return InfrastructureRecord(
        id=f"osm_{osm_id}_{asset_type}",
        city_id=city_id,
        asset_type=asset_type,
        name=name,
        lon=lon,
        lat=lat,
        coordinates=coords,
        source="openstreetmap",
        source_osm_id=osm_id or None,
        retrieved_at=retrieved_at,
        data_status=data_status,
        properties={"osm_id": osm_id, "tags": {k: tags[k] for k in list(tags)[:20]}},
    )


def _classify(tags: dict, is_highway: bool) -> Optional[str]:
    if tags.get("bridge") in {"yes", "true"} or tags.get("man_made") == "bridge":
        return "bridge"
    amenity = tags.get("amenity")
    if amenity in _TYPE_MAP:
        return _TYPE_MAP[amenity]
    if tags.get("highway") and is_highway:
        return "road"
    if tags.get("highway"):
        return "road"
    return None


def _overpass_query(west: float, south: float, east: float, north: float) -> str:
    bbox = f"{south},{west},{north},{east}"
    return f"""
    [out:json][timeout:25];
    (
      node["amenity"~"hospital|clinic|school|college|university|shelter|fire_station|police"]({bbox});
      way["amenity"~"hospital|clinic|school|college|university|shelter"]({bbox});
      way["bridge"="yes"]({bbox});
      way["highway"]({bbox});
    );
    out center geom 200;
    """


class OsmFixtureAdapter:
    def fetch(self, city_id: str) -> List[InfrastructureRecord]:
        fixture = load_osm_fixture(city_id)
        retrieved = isoformat()
        records = []
        for asset in fixture.get("assets", []) + fixture.get("roads", []):
            lon = asset.get("lon")
            lat = asset.get("lat")
            coords = asset.get("coordinates")
            if lon is not None and lat is not None and not validate_lon_lat(lon, lat):
                continue
            records.append(
                InfrastructureRecord(
                    id=f"fixture_{asset['name']}_{asset['asset_type']}".replace(" ", "_"),
                    city_id=city_id,
                    asset_type=asset["asset_type"],
                    name=asset.get("name"),
                    lon=lon,
                    lat=lat,
                    coordinates=coords,
                    source="osm-fixture",
                    retrieved_at=retrieved,
                    data_status="DEMO",
                    properties={},
                )
            )
        return records


class OsmOverpassAdapter:
    def fetch(self, city_id: str) -> List[InfrastructureRecord]:
        city = create_city_registry().get_city(city_id)
        bounds = city.bounds
        query = _overpass_query(bounds.west, bounds.south, bounds.east, bounds.north)
        body = urlencode({"data": query}).encode()
        if not OVERPASS_BUCKET.allow():
            raise RuntimeError("overpass rate-limited")
        req = Request(OVERPASS_URL, data=body, method="POST")
        start = time.monotonic()
        with urlopen(req, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        LOGGER.info("overpass ok city=%s latency_ms=%.0f", city_id, (time.monotonic() - start) * 1000)
        retrieved = isoformat()
        records = []
        seen = set()
        for element in payload.get("elements", []):
            rec = normalize_osm_element(element, city_id, "REAL", retrieved)
            if rec is None or rec.source_osm_id in seen:
                continue
            if rec.source_osm_id:
                seen.add(rec.source_osm_id)
            records.append(rec)
        return records


def ingest_osm(city_id: str = "dhaka") -> dict:
    """Overpass first; fixture fallback is labeled DEMO with fallback_used."""
    repo = get_repository()
    store = get_platform_store()
    fallback_used = False
    data_status = "REAL"
    try:
        records = OsmOverpassAdapter().fetch(city_id)
        if not records:
            raise RuntimeError("overpass returned no elements")
        provider = "OpenStreetMap Overpass"
        freshness = "SNAPSHOT"
    except Exception as exc:
        LOGGER.warning("overpass failed city=%s err=%s; using fixture", city_id, exc)
        records = OsmFixtureAdapter().fetch(city_id)
        fallback_used = True
        data_status = "DEMO"
        provider = "OSM fixture"
        freshness = "SNAPSHOT"

    created = 0
    for rec in records:
        rec.data_status = data_status
        repo.put_infrastructure(rec)
        created += 1

    # rivers from fixture geometry (REAL snapshot if overpass later adds waterways)
    fixture = load_osm_fixture(city_id)
    for river in fixture.get("rivers", []):
        store.rivers[river["id"]] = {"id": river["id"], "name": river["name"], "city_id": city_id}
        for segment in river.get("segments", []):
            store.river_segments[segment["id"]] = {**segment, "river_id": river["id"], "city_id": city_id}

    store.ingest_runs.append(
        {
            "kind": "osm",
            "city_id": city_id,
            "count": created,
            "at": isoformat(),
            "fallback_used": fallback_used,
            "source": provider,
        }
    )
    prov = envelope(
        data_status=data_status,
        provider=provider,
        dataset="infrastructure",
        freshness=freshness,
        fallback_used=fallback_used,
        simulated=fallback_used,
        source_url=None if fallback_used else OVERPASS_URL,
    )
    return {"city_id": city_id, "assets": created, "provenance": prov, "fallback_used": fallback_used}
