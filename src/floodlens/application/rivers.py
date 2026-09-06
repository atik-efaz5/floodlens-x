"""River network graph and observation series. Never invent gauges or arrival times."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.platform_store import get_platform_store
from floodlens.application.repository import get_repository
from floodlens.application.river_gauges import RiverGaugeAdapter
from floodlens.application.provenance import isoformat

_CITIES = create_city_registry()

FLOW_DIRECTION_STATUS = "UNAVAILABLE / TOPOLOGY ONLY"
TOPOLOGY_KIND = "NETWORK TOPOLOGY"
GRAPH_LIMIT = 80
SEARCH_LIMIT = 20
OBS_LIMIT = 200
NEIGHBOR_LIMIT = 50


def _fixture_fallback() -> bool:
    store = get_platform_store()
    runs = [r for r in store.ingest_runs if r.get("kind") == "osm"]
    return bool(runs and runs[-1].get("fallback_used"))


def _topology_status() -> str:
    return "DEMO"


def list_rivers(
    city_id: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = GRAPH_LIMIT,
) -> dict:
    store = get_platform_store()
    rivers = list(store.rivers.values())
    if city_id:
        rivers = [r for r in rivers if r.get("city_id") == city_id]
    cap = min(max(limit, 1), GRAPH_LIMIT)
    payload = []
    for river in rivers[:cap]:
        segments = [s for s in store.river_segments.values() if s.get("river_id") == river.get("id")]
        if bbox:
            west, south, east, north = bbox
            segments = [
                s
                for s in segments
                if any(
                    west <= float(pt[0]) <= east and south <= float(pt[1]) <= north
                    for pt in (s.get("coordinates") or [])
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2
                )
            ]
            if not segments:
                continue
        payload.append({
            **river,
            "segments": segments[:cap],
            "segment_count": len(segments),
            **_gauge_snapshot(river.get("id")),
        })
    return {
        "data": payload,
        "limit": cap,
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "kind": TOPOLOGY_KIND,
        "provenance": envelope(
            data_status="DEMO" if payload else "UNAVAILABLE",
            provider="osm-fixture",
            dataset="rivers",
            freshness="SNAPSHOT",
            simulated=True,
            fallback_used=_fixture_fallback(),
        ),
        "fallback_used": _fixture_fallback(),
        "note": "River centerlines currently come from the OSM-style fixture. FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY.",
    }


def _gauge_snapshot(river_id: Optional[str]) -> dict:
    if not river_id:
        return {}
    from floodlens.application.demo_fixtures import demo_fixtures_enabled

    if not demo_fixtures_enabled():
        return {}
    try:
        obs = river_observations(river_id)
    except KeyError:
        return {}
    return {
        "water_level_m": obs.get("current_water_level_m"),
        "discharge_m3s": obs.get("current_discharge_m3s"),
        "gauge_status": obs.get("water_level_status"),
    }


def _siblings(river_id: str) -> list[dict]:
    store = get_platform_store()
    return [s for s in store.river_segments.values() if s.get("river_id") == river_id]


def _neighbors(segment: dict, siblings: list[dict], direction: str) -> list[dict]:
    sid = segment.get("id")
    if direction == "upstream":
        return [
            {"id": s.get("id"), "from_node": s.get("from_node"), "to_node": s.get("to_node")}
            for s in siblings
            if s.get("to_node") == segment.get("from_node") and s.get("id") != sid
        ]
    return [
        {"id": s.get("id"), "from_node": s.get("from_node"), "to_node": s.get("to_node")}
        for s in siblings
        if s.get("from_node") == segment.get("to_node") and s.get("id") != sid
    ]


def _walk(segment_id: str, siblings: list[dict], direction: str, limit: int = NEIGHBOR_LIMIT) -> list[dict]:
    by_id = {s.get("id"): s for s in siblings}
    start = by_id.get(segment_id)
    if not start:
        return []
    seen = {segment_id}
    frontier = [start]
    ordered: list[dict] = []
    while frontier and len(ordered) < limit:
        current = frontier.pop(0)
        for row in _neighbors(current, siblings, direction):
            rid = row["id"]
            if rid in seen:
                continue
            seen.add(rid)
            ordered.append(row)
            if by_id.get(rid):
                frontier.append(by_id[rid])
            if len(ordered) >= limit:
                break
    return ordered


def river_segment_details(river_id: str, segment_id: str) -> dict:
    store = get_platform_store()
    river = store.rivers.get(river_id)
    if not river:
        raise KeyError(river_id)
    segment = store.river_segments.get(segment_id)
    if not segment or segment.get("river_id") != river_id:
        raise KeyError(segment_id)
    siblings = _siblings(river_id)
    upstream = _neighbors(segment, siblings, "upstream")
    downstream = _neighbors(segment, siblings, "downstream")
    coords = segment.get("coordinates") or []
    return {
        "river": {"id": river.get("id"), "name": river.get("name"), "city_id": river.get("city_id")},
        "segment": {
            "id": segment.get("id"),
            "from_node": segment.get("from_node"),
            "to_node": segment.get("to_node"),
            "coordinate_count": len(coords),
            "geometry": {"type": "LineString", "coordinates": coords} if len(coords) >= 2 else None,
        },
        "upstream": upstream,
        "downstream": downstream,
        "reachable_downstream": _walk(segment_id, siblings, "downstream"),
        "reachable_upstream": _walk(segment_id, siblings, "upstream"),
        "water_level_m": None,
        "discharge_m3s": None,
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "kind": TOPOLOGY_KIND,
        "hydrological_propagation": "NOT_COMPUTED",
        "estimated_arrival_time": None,
        "study_regions": _study_regions_for_coords(coords),
        "provenance": envelope(
            data_status=_topology_status() if coords else "PARTIAL",
            provider="osm-fixture",
            dataset="river-segment",
            freshness="SNAPSHOT",
            simulated=True,
            fallback_used=_fixture_fallback(),
        ),
        "data_status": _topology_status() if coords else "PARTIAL",
        "note": "WATER LEVEL: UNAVAILABLE. DISCHARGE: UNAVAILABLE. FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY.",
    }


def river_status(river_id: str) -> dict:
    store = get_platform_store()
    repo = get_repository()
    river = store.rivers.get(river_id)
    if not river:
        raise KeyError(river_id)
    segments = [s for s in store.river_segments.values() if s["river_id"] == river_id]
    graph = {
        "nodes": sorted({n for s in segments for n in (s["from_node"], s["to_node"])}),
        "edges": [
            {"id": s["id"], "from": s["from_node"], "to": s["to_node"]}
            for s in segments[:GRAPH_LIMIT]
        ],
    }
    from floodlens.application.demo_fixtures import demo_fixtures_enabled, demo_river_observations

    gauge_rows = repo.list_river_observations(river_id)
    if demo_fixtures_enabled() and (
        not gauge_rows or all(row.data_status == "UNAVAILABLE" or row.water_level_m is None for row in gauge_rows)
    ):
        gauge_rows = demo_river_observations(river_id)
        for row in gauge_rows:
            repo.put_river_observation(row)
    if not gauge_rows:
        empty = RiverGaugeAdapter().fetch(river_id)
        repo.put_river_observation(empty)
        gauge_rows = [empty]
    latest = gauge_rows[-1]
    if latest.data_status == "UNAVAILABLE" or latest.water_level_m is None:
        series = [
            {
                "t": latest.observed_at or isoformat(),
                "water_level_m": latest.water_level_m,
                "discharge_m3s": latest.discharge_m3s,
                "available": False,
                "data_status": latest.data_status,
            }
        ]
        freshness = "UNAVAILABLE"
        note = "No gauge series ingested for this river. Arrival times are unavailable."
        data_status = "UNAVAILABLE"
        simulated = False
    else:
        series = [
            {
                "t": row.observed_at,
                "water_level_m": row.water_level_m,
                "discharge_m3s": row.discharge_m3s,
                "available": True,
                "data_status": row.data_status,
            }
            for row in gauge_rows
            if row.data_status != "UNAVAILABLE"
        ][:OBS_LIMIT]
        data_status = latest.data_status if latest.data_status in {"DEMO", "REAL", "SIMULATED", "STALE", "PARTIAL"} else "REAL"
        if data_status == "DEMO":
            freshness = "SNAPSHOT"
            simulated = True
            note = "DEMO gauge series. Not a live river feed."
        else:
            freshness = "RECENT"
            simulated = False
            note = None
    return {
        "river": river,
        "graph": graph,
        "series": series,
        "flood_threshold_m": None,
        "time_to_threshold": None,
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "kind": TOPOLOGY_KIND,
        "hydrological_propagation": "NOT_COMPUTED",
        "estimated_arrival_time": None,
        "note": note,
        "provenance": envelope(
            data_status=data_status,
            provider="demo-river-gauge" if data_status == "DEMO" else "river-gauge",
            dataset="water_level",
            freshness=freshness if freshness in {"RECENT", "UNAVAILABLE", "SNAPSHOT"} else "UNAVAILABLE",
            simulated=simulated,
        ),
    }


def river_graph(river_id: str) -> dict:
    status = river_status(river_id)
    graph = status["graph"]
    store = get_platform_store()
    segments = [s for s in store.river_segments.values() if s.get("river_id") == river_id]
    return {
        **graph,
        "kind": TOPOLOGY_KIND,
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "flow_direction_verified": False,
        "hydrological_propagation": "NOT_COMPUTED",
        "estimated_arrival_time": None,
        "segment_count": len(segments),
        "limit": GRAPH_LIMIT,
        "note": "from_node/to_node is fixture/OSM topology, not verified hydrological flow direction.",
        "provenance": envelope(
            data_status=_topology_status(),
            provider="osm-fixture",
            dataset="river-graph",
            freshness="SNAPSHOT",
            simulated=True,
            fallback_used=_fixture_fallback(),
        ),
    }


def search_rivers(query: str, city_id: str | None = None, limit: int = SEARCH_LIMIT) -> dict:
    normalized = (query or "").strip().lower()
    if not normalized:
        raise ValueError("Search query must not be empty.")
    store = get_platform_store()
    cap = min(max(limit, 1), SEARCH_LIMIT)
    hits: list[dict] = []
    for river in store.rivers.values():
        if city_id and river.get("city_id") != city_id:
            continue
        name = f"{river.get('id', '')} {river.get('name', '')} {river.get('city_id', '')}".lower()
        if normalized in name:
            hits.append(
                {
                    "kind": "river",
                    "id": river.get("id"),
                    "river_id": river.get("id"),
                    "name": river.get("name") or river.get("id"),
                    "city_id": river.get("city_id"),
                    "display_name": f"{river.get('name') or river.get('id')} ({river.get('city_id')})",
                    "data_status": _topology_status(),
                }
            )
        for segment in _siblings(river.get("id")):
            hay = f"{segment.get('id', '')} {segment.get('from_node', '')} {segment.get('to_node', '')}".lower()
            if normalized in hay:
                hits.append(
                    {
                        "kind": "segment",
                        "id": segment.get("id"),
                        "river_id": river.get("id"),
                        "name": river.get("name") or river.get("id"),
                        "segment_id": segment.get("id"),
                        "city_id": river.get("city_id"),
                        "display_name": f"{river.get('name') or river.get('id')} · {segment.get('id')}",
                        "data_status": _topology_status(),
                    }
                )
    for city in _CITIES.list_cities():
        label = f"{city.city_id} {city.name} {city.region}".lower()
        if normalized in label:
            hits.append(
                {
                    "kind": "study_region",
                    "id": city.city_id,
                    "name": city.name,
                    "city_id": city.city_id,
                    "display_name": f"{city.name} (STUDY REGION)",
                    "note": "Study region from the city registry. Not an administrative district.",
                    "data_status": "REAL",
                }
            )
    seen = set()
    unique = []
    for hit in hits:
        key = (hit.get("kind"), hit.get("id"), hit.get("river_id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
        if len(unique) >= cap:
            break
    return {
        "query": query.strip(),
        "results": unique,
        "basin": {"available": False, "reason": "No basin dataset is configured."},
        "provenance": envelope(
            data_status="DEMO" if unique else "UNAVAILABLE",
            provider="osm-fixture",
            dataset="river-search",
            freshness="SNAPSHOT",
            simulated=True,
        ),
        "note": "DEMO fixture topology. FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY.",
    }


def compute_rate_of_change(series: list[dict], field: str = "water_level_m") -> dict:
    """d(field)/dt from available observations. Never treats missing as zero."""
    units = "m/h" if field == "water_level_m" else "m3/s/h"
    rows = []
    statuses = []
    for row in series or []:
        if not row.get("available"):
            continue
        value = row.get(field)
        stamp = row.get("t") or row.get("observed_at")
        if value is None or not stamp:
            continue
        parsed = _parse_time(stamp)
        if parsed is None:
            continue
        rows.append((parsed, float(value)))
        statuses.append(row.get("data_status") or "REAL")
    if len(rows) < 2:
        return {
            "status": "UNAVAILABLE",
            "value": None,
            "units": units,
            "interval": None,
            "reason": "Fewer than two observations with timestamps.",
        }
    rows.sort(key=lambda item: item[0])
    t0, v0 = rows[-2]
    t1, v1 = rows[-1]
    hours = (t1 - t0).total_seconds() / 3600.0
    if hours <= 0:
        return {
            "status": "UNAVAILABLE",
            "value": None,
            "units": units,
            "interval": None,
            "reason": "Non-positive time interval between observations.",
        }
    status = "DEMO" if any(item == "DEMO" for item in statuses) else "REAL"
    return {
        "status": status,
        "value": (v1 - v0) / hours,
        "units": units,
        "interval": f"{hours:.3f} h",
        "from": t0.isoformat(),
        "to": t1.isoformat(),
        "reason": "DEMO rate of change. Not a live gauge derivative." if status == "DEMO" else None,
    }


def _parse_time(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def river_observations(river_id: str) -> dict:
    status = river_status(river_id)
    series = (status.get("series") or [])[:OBS_LIMIT]
    real_level = [r for r in series if r.get("available") and r.get("water_level_m") is not None]
    real_q = [r for r in series if r.get("available") and r.get("discharge_m3s") is not None]
    current = real_level[-1] if real_level else None
    level_status = (status.get("provenance") or {}).get("data_status") or "UNAVAILABLE"
    if not real_level:
        level_status = "UNAVAILABLE"
    discharge_status = level_status if real_q else "UNAVAILABLE"
    return {
        "river_id": river_id,
        "observations": series,
        "water_level_status": level_status,
        "discharge_status": discharge_status,
        "current_water_level_m": current.get("water_level_m") if current else None,
        "current_discharge_m3s": real_q[-1].get("discharge_m3s") if real_q else None,
        "flood_threshold_m": status.get("flood_threshold_m"),
        "time_to_threshold": None,
        "rate_of_change_level": compute_rate_of_change(series, "water_level_m"),
        "rate_of_change_discharge": compute_rate_of_change(series, "discharge_m3s"),
        "estimated_arrival_time": None,
        "forecast": {
            "available": False,
            "reason": "No documented river forecast model. Discharge/level forecast is UNAVAILABLE.",
        },
        "provenance": status.get("provenance"),
        "note": status.get("note")
        or "WATER LEVEL: UNAVAILABLE. DISCHARGE: UNAVAILABLE. ESTIMATED ARRIVAL TIME: UNAVAILABLE.",
        "limit": OBS_LIMIT,
    }


def segment_neighbors(river_id: str, segment_id: str) -> dict:
    details = river_segment_details(river_id, segment_id)
    return {
        "river_id": river_id,
        "segment_id": segment_id,
        "upstream": details["upstream"],
        "downstream": details["downstream"],
        "reachable_downstream": details["reachable_downstream"],
        "reachable_upstream": details["reachable_upstream"],
        "kind": TOPOLOGY_KIND,
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "flow_direction_verified": False,
        "hydrological_propagation": "NOT_COMPUTED",
        "estimated_arrival_time": None,
        "study_regions": details["study_regions"],
        "limit": NEIGHBOR_LIMIT,
        "note": "Network topology only. HYDROLOGICAL PROPAGATION: NOT_COMPUTED.",
        "provenance": details["provenance"],
    }


def _study_regions_for_coords(coords: list) -> list[dict]:
    hits = []
    for city in _CITIES.list_cities():
        b = city.bounds
        if any(
            b.west <= float(pt[0]) <= b.east and b.south <= float(pt[1]) <= b.north
            for pt in coords
            if isinstance(pt, (list, tuple)) and len(pt) >= 2
        ):
            hits.append(
                {
                    "city_id": city.city_id,
                    "name": city.name,
                    "kind": "STUDY REGION",
                    "note": "Study region rectangle from the city registry. Not an administrative district.",
                    "source": "city-registry",
                }
            )
    return hits


def river_overview(river_id: str) -> dict:
    store = get_platform_store()
    river = store.rivers.get(river_id)
    if not river:
        raise KeyError(river_id)
    segments = _siblings(river_id)
    geom = sum(1 for s in segments if len(s.get("coordinates") or []) >= 2)
    obs = river_observations(river_id)
    all_coords = [pt for s in segments for pt in (s.get("coordinates") or [])]
    return {
        "river": {"id": river.get("id"), "name": river.get("name"), "city_id": river.get("city_id")},
        "segment_count": len(segments),
        "geometry_available": geom > 0,
        "observation_status": obs["water_level_status"],
        "discharge_status": obs["discharge_status"],
        "forecast_status": "UNAVAILABLE",
        "flow_direction_status": FLOW_DIRECTION_STATUS,
        "kind": TOPOLOGY_KIND,
        "hydrological_propagation": "NOT_COMPUTED",
        "estimated_arrival_time": None,
        "study_regions": _study_regions_for_coords(all_coords),
        "source": "osm-fixture",
        "timestamp": isoformat(),
        "freshness": "SNAPSHOT",
        "provenance": envelope(
            data_status=_topology_status(),
            provider="osm-fixture",
            dataset="river-overview",
            freshness="SNAPSHOT",
            simulated=True,
            fallback_used=_fixture_fallback(),
        ),
    }
