"""Layer catalog and data-source catalog with provenance. No unlabeled LIVE layers."""

from __future__ import annotations

from floodlens.application.data_contracts import envelope, public_source_ref
from floodlens.application.ingest import ingest_dem_metadata
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.repository import get_repository


def layer_catalog(city_id: str, bounds: dict) -> dict:
    store = get_platform_store()
    from floodlens.application.demo_fixtures import demo_fixtures_enabled, ensure_demo_rainfall
    from floodlens.application.population import get_population_provider

    if demo_fixtures_enabled():
        ensure_demo_rainfall(city_id)
    dem = store.artifacts.get(f"terrain-{city_id}") or store.artifacts.get(f"dem-{city_id}")
    if not dem:
        dem = ingest_dem_metadata(city_id, bounds)
    rain = store.observations_for("precipitation_mm", city_id)
    rain_fresh = "unavailable"
    rain_source = "none"
    rain_status = "UNAVAILABLE"
    rain_sim = True
    if rain:
        rain_sim = bool(rain[-1].get("simulated"))
        rain_fresh = "demo" if rain_sim else "recent"
        rain_source = rain[-1].get("source", "unknown")
        rain_status = rain[-1].get("data_status") or ("DEMO" if rain_sim else "REAL")
    osm_runs = [r for r in store.ingest_runs if r.get("kind") == "osm" and r.get("city_id") == city_id]
    osm_fallback = bool(osm_runs and osm_runs[-1].get("fallback_used"))
    osm_status = "DEMO" if osm_fallback or not store.assets_for_city(city_id) else "REAL"
    dem_status = dem.get("data_status") or ("UNAVAILABLE" if not dem.get("available", True) else "REAL")
    latest_fc = get_repository().get_latest_forecast(city_id)
    physics_on = bool(latest_fc and latest_fc.get("model_kind") == "PHYSICS_BASELINE" and latest_fc.get("available"))
    flood_status = latest_fc.get("data_status") if physics_on else "UNAVAILABLE"
    predicted = (
        _layer(
            "predicted_flood",
            "Predicted flood (physics baseline)",
            latest_fc.get("model_id") or "PHYSICS-BASELINE-v0.1",
            "snapshot",
            True,
            flood_status,
        )
        if physics_on
        else _layer("predicted_flood", "Predicted flood (heuristic)", "forecast-heuristic", "demo", True, "DEMO")
    )
    pop = get_population_provider().expose(city_id)
    pop_status = pop.get("data_status") or ("UNAVAILABLE" if not pop.get("available") else "REAL")
    gauge_status = "DEMO" if demo_fixtures_enabled() else "UNAVAILABLE"
    rain_reason = "No validated spatial rainfall layer is currently configured."
    if rain_status == "DEMO":
        rain_reason = "DEMO point/uniform field. Not a radar or satellite precipitation grid."
    elif rain_status != "UNAVAILABLE":
        rain_reason = None
    terrain_reason = "Terrain raster is UNAVAILABLE."
    if dem_status == "DEMO":
        terrain_reason = "DEMO hillshade preview. Not a GeoTIFF DEM and not passed to the solver."
    elif dem_status != "UNAVAILABLE":
        terrain_reason = "No browser DEM raster is loaded. Metadata only."
    layers = [
        _layer(
            "flood_extent",
            "Flood extent",
            "physics-baseline" if physics_on else "simulation-or-unavailable",
            "snapshot" if physics_on else "unavailable",
            True,
            flood_status if physics_on else "UNAVAILABLE",
            reason=None if physics_on else "No completed physics flood raster is attached.",
        ),
        _layer(
            "water_depth",
            "Water depth",
            "physics-snapshot",
            "snapshot" if physics_on else "unavailable",
            True,
            flood_status if physics_on else "UNAVAILABLE",
            reason=None if physics_on else "Depth is only available on a completed physics/scenario artifact.",
        ),
        _layer(
            "rainfall",
            "Rainfall",
            rain_source,
            rain_fresh,
            rain_sim,
            rain_status,
            reason=rain_reason,
            temporal_resolution="point observations when ingested",
            extra={"overlay_artifact_id": f"demo-rainfall-{city_id}"} if rain_status == "DEMO" else None,
        ),
        _layer("rivers", "Rivers", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer(
            "terrain",
            "Terrain / DEM",
            dem.get("source", "unconfigured"),
            "snapshot" if dem_status == "DEMO" else "stale",
            dem_status == "DEMO",
            dem_status,
            reason=terrain_reason,
            extra={"overlay_artifact_id": f"demo-terrain-hillshade-{city_id}"} if dem_status == "DEMO" else None,
        ),
        _layer("roads", "Roads", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer("hospitals", "Hospitals", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer("schools", "Schools", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer("bridges", "Bridges", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer(
            "population",
            "Population",
            "demo-population" if pop_status == "DEMO" else "not-ingested",
            "snapshot" if pop_status == "DEMO" else "unavailable",
            pop_status == "DEMO",
            pop_status,
            reason=pop.get("reason")
            or "Population grid is not ingested. Exposure totals are never invented.",
        ),
        _layer("shelters", "Shelters", "osm-or-fixture", "stale", osm_status == "DEMO", osm_status),
        _layer(
            "critical_infrastructure",
            "Critical infrastructure",
            "osm-or-fixture",
            "stale",
            osm_status == "DEMO",
            osm_status,
        ),
        predicted,
        _layer(
            "water_level",
            "Water level",
            "demo-river-gauge" if gauge_status == "DEMO" else "no-gauge-feed",
            "snapshot" if gauge_status == "DEMO" else "unavailable",
            gauge_status == "DEMO",
            gauge_status,
            reason=(
                "DEMO gauge series. Not a live river feed."
                if gauge_status == "DEMO"
                else "No public gauge series is configured. Water level is not invented."
            ),
        ),
        _layer(
            "ai_spatial",
            "Spatial AI flood map",
            "ai-spatial-forecast",
            "unavailable",
            False,
            "UNAVAILABLE",
            reason="Spatial AI is NOT_VALIDATED. POST /api/v1/forecast/ai-spatial stays UNAVAILABLE.",
        ),
    ]
    return {
        "city_id": city_id,
        "layers": layers,
        "legend": {
            "LOW": "green",
            "MODERATE": "yellow",
            "HIGH": "orange",
            "CRITICAL": "red",
        },
        "semantic_color_system": "risk-only",
    }


def data_source_catalog(city_id: str = "dhaka") -> dict:
    from floodlens.application.demo_fixtures import demo_fixtures_enabled, ensure_demo_rainfall

    store = get_platform_store()
    repo = get_repository()
    if demo_fixtures_enabled():
        ensure_demo_rainfall(city_id)
    rain = repo.list_rainfall(city_id)
    terrain = repo.get_terrain(city_id)
    assets = store.assets_for_city(city_id)
    osm_run = next((r for r in reversed(store.ingest_runs) if r.get("kind") == "osm"), None)
    rain_run = next((r for r in reversed(store.ingest_runs) if r.get("kind") == "rainfall"), None)
    sources = [
        {
            "id": "osm",
            "title": "OpenStreetMap",
            "provider": (osm_run or {}).get("source") or "OpenStreetMap Overpass",
            "data_status": "DEMO" if (osm_run or {}).get("fallback_used") else ("REAL" if assets else "UNAVAILABLE"),
            "freshness": "SNAPSHOT",
            "fallback_used": bool((osm_run or {}).get("fallback_used")),
            "feature_count": len(assets),
        },
        {
            "id": "dem",
            "title": "Digital elevation model",
            "provider": "demo-terrain-generator"
            if terrain and terrain.data_status == "DEMO"
            else ("GeoTIFF" if terrain and terrain.data_status == "REAL" else "unconfigured"),
            "data_status": terrain.data_status if terrain else "UNAVAILABLE",
            "freshness": "STATIC",
            "fallback_used": False,
            "uri": public_source_ref(terrain.uri) if terrain else None,
        },
        {
            "id": "open-meteo",
            "title": "Open-Meteo precipitation",
            "provider": rain[-1].provider if rain else "Open-Meteo",
            "data_status": rain[-1].data_status if rain else "UNAVAILABLE",
            "freshness": "RECENT" if rain and rain[-1].data_status == "REAL" else ("SNAPSHOT" if rain else "UNAVAILABLE"),
            "fallback_used": bool((rain_run or {}).get("fallback_used")),
            "observed": sum(1 for r in rain if r.kind == "OBSERVED"),
            "forecast": sum(1 for r in rain if r.kind == "FORECAST"),
        },
        {
            "id": "river-gauge",
            "title": "River gauge",
            "provider": "demo-river-gauge" if demo_fixtures_enabled() else "no-gauge-feed",
            "data_status": "DEMO" if demo_fixtures_enabled() else "UNAVAILABLE",
            "freshness": "SNAPSHOT" if demo_fixtures_enabled() else "UNAVAILABLE",
            "fallback_used": bool(demo_fixtures_enabled()),
            "note": (
                "DEMO gauge series. Not a live river feed."
                if demo_fixtures_enabled()
                else "No public Bangladesh gauge API is configured. Discharge is not invented."
            ),
        },
        {
            "id": "simulation-engine",
            "title": "Simulation engine",
            "provider": "SW-SOLVER",
            "data_status": "SIMULATED",
            "freshness": "SNAPSHOT",
            "fallback_used": False,
            "model_version": PHYSICS_MODEL_VERSION,
        },
    ]
    return {
        "city_id": city_id,
        "sources": sources,
        "provenance": envelope(
            data_status="PARTIAL",
            provider="floodlens-catalog",
            dataset="data-sources",
            freshness="SNAPSHOT",
        ),
        "fallback_used": any(s.get("fallback_used") for s in sources),
    }


def _layer(
    layer_id: str,
    title: str,
    source: str,
    freshness: str,
    simulated: bool,
    data_status: str,
    reason: str | None = None,
    spatial_resolution: str | None = None,
    temporal_resolution: str | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "id": layer_id,
        "title": title,
        "source": source,
        "timestamp": isoformat(),
        "freshness": freshness,
        "data_status": data_status,
        "simulated": simulated,
        "legend": "see catalog.legend for risk colors",
        "spatial_resolution": spatial_resolution,
        "temporal_resolution": temporal_resolution,
    }
    if reason:
        payload["reason"] = reason
    if extra:
        payload.update(extra)
    return payload
