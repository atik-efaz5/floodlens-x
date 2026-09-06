"""Labeled DEMO operational fixtures. Never REAL or LIVE. Solver DEM is never this data."""

from __future__ import annotations

import os
from datetime import timedelta
from typing import List, Optional

import numpy as np

from floodlens.application.canonical import RainfallObservation, RiverObservation, TerrainDataset
from floodlens.application.data_contracts import envelope
from floodlens.application.provenance import isoformat, utcnow

DEMO_REASON = (
    "DEMO operational fixture. Not a live feed. Never treat as REAL or LIVE."
)
DEMO_EVENT_ID = "demo-dhaka-monsoon-2020"
DEMO_EVENT_TIME = "2020-07-15T00:00:00+00:00"
DEMO_FORECAST_ARTIFACT = "demo-forecast-demo-dhaka-monsoon-2020"

_FALSE = {"0", "false", "off", "no"}


def demo_fixtures_enabled() -> bool:
    """Default on for uvicorn/localhost. Pytest sets FLOODLENS_DEMO_FIXTURES=0."""
    raw = os.environ.get("FLOODLENS_DEMO_FIXTURES", "1")
    return str(raw).strip().lower() not in _FALSE


def demo_envelope(*, provider: str, dataset: str, extra: Optional[dict] = None) -> dict:
    return envelope(
        data_status="DEMO",
        provider=provider,
        dataset=dataset,
        freshness="SNAPSHOT",
        fallback_used=True,
        simulated=True,
        extra={"reason": DEMO_REASON, **(extra or {})},
    )


def rainfall_overlay_id(city_id: str) -> str:
    return f"demo-rainfall-{city_id}"


def terrain_overlay_id(city_id: str) -> str:
    return f"demo-terrain-hillshade-{city_id}"


def demo_river_observations(river_id: str) -> List[RiverObservation]:
    now = utcnow()
    rows = []
    for hour in range(0, 25, 3):
        stamp = now - timedelta(hours=24 - hour)
        level = 2.4 + hour * 0.045
        discharge = 180.0 + hour * 6.5
        rows.append(
            RiverObservation(
                river_id=river_id,
                segment_id=None,
                observed_at=isoformat(stamp),
                water_level_m=round(level, 3),
                discharge_m3s=round(discharge, 2),
                source="demo-river-gauge",
                data_status="DEMO",
            )
        )
    return rows


def ensure_demo_rainfall(city_id: str) -> dict:
    """Seed Open-Meteo-style DEMO rows and a tiny heatmap PNG. Not a radar grid."""
    from floodlens.application.artifact_store import put_depth_artifact
    from floodlens.application.city_data import create_city_registry
    from floodlens.application.meteo import _synthetic_series
    from floodlens.application.repository import get_repository

    repo = get_repository()
    existing = repo.list_rainfall(city_id)
    if not existing:
        for row in _synthetic_series(city_id):
            repo.put_rainfall(row)
        existing = repo.list_rainfall(city_id)
    overlay_id = rainfall_overlay_id(city_id)
    from floodlens.application.artifact_store import get_artifact

    if get_artifact(overlay_id) is None:
        city = create_city_registry().get_city(city_id)
        seed = sum(ord(ch) for ch in city_id) or 1
        rng = np.random.RandomState(seed)
        yy, xx = np.mgrid[0:32, 0:32]
        field = 8.0 * np.exp(-((xx - 16.0) ** 2 + (yy - 12.0) ** 2) / 80.0)
        field = field + rng.uniform(0.0, 1.5, field.shape)
        put_depth_artifact(
            overlay_id,
            field,
            {
                "kind": "rainfall_heatmap",
                "city_id": city_id,
                "data_status": "DEMO",
                "simulated": True,
                "note": "DEMO uniform-field heatmap. Not a radar or satellite precipitation grid.",
                "bounds": city.bounds.to_dict() if city else None,
            },
        )
    latest = existing[-1] if existing else None
    return {
        "overlay_artifact_id": overlay_id,
        "n": len(existing),
        "latest_mm": latest.value_mm if latest else None,
    }


def ensure_demo_terrain(city_id: str, bounds: Optional[dict] = None) -> dict:
    """Metadata + tiny hillshade PNG. Elevation arrays are not a solver DEM."""
    from floodlens.application.artifact_store import get_artifact, put_depth_artifact
    from floodlens.application.city_data import create_city_registry

    city = create_city_registry().get_city(city_id)
    window_bounds = bounds or city.bounds.to_dict()
    overlay_id = terrain_overlay_id(city_id)
    ny, nx = 32, 32
    yy, xx = np.mgrid[0:ny, 0:nx]
    z = 12.0 + 8.0 * ((yy / max(ny - 1, 1)) ** 1.4) + 1.5 * np.sin(xx / 5.0)
    channel = 3.0 * np.exp(-((xx - nx * 0.45) ** 2) / 18.0)
    z = np.maximum(1.0, z - channel)
    gy, gx = np.gradient(z)
    slope = np.pi / 2.0 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    altitude = np.pi / 4.0
    azimuth = np.pi / 4.0
    shade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(
        azimuth - aspect
    )
    shade = np.clip((shade - float(np.min(shade))) / (float(np.max(shade) - np.min(shade)) or 1.0), 0.0, 1.0)
    if get_artifact(overlay_id) is None:
        put_depth_artifact(
            overlay_id,
            shade,
            {
                "kind": "hillshade",
                "city_id": city_id,
                "data_status": "DEMO",
                "simulated": True,
                "note": "DEMO hillshade preview. Not a GeoTIFF DEM and not passed to the solver.",
                "bounds": window_bounds,
            },
        )
    stats = {
        "min": float(np.min(z)),
        "max": float(np.max(z)),
        "mean": float(np.mean(z)),
    }
    return {
        "overlay_artifact_id": overlay_id,
        "statistics": stats,
        "min_elevation": stats["min"],
        "max_elevation": stats["max"],
        "bounds": window_bounds,
        "crs": city.crs or "EPSG:4326",
    }


def demo_terrain_dataset(city_id: str, bounds: dict) -> TerrainDataset:
    preview = ensure_demo_terrain(city_id, bounds)
    return TerrainDataset(
        id=f"terrain-{city_id}",
        city_id=city_id,
        uri=f"artifacts://{preview['overlay_artifact_id']}",
        crs=preview["crs"],
        bounds=preview["bounds"],
        resolution_deg=None,
        nodata=None,
        min_elevation=preview["min_elevation"],
        max_elevation=preview["max_elevation"],
        source="demo-terrain-generator",
        data_status="DEMO",
        freshness="SNAPSHOT",
        version="demo-hillshade-v0",
    )


def demo_population_expose(city_id: str, wet_mask: Optional[np.ndarray] = None) -> dict:
    base = {"dhaka": 128000, "sunamganj": 42000, "sylhet": 31000}
    n = int(base.get(city_id, 15000))
    if wet_mask is not None:
        arr = np.asarray(wet_mask)
        if arr.size:
            frac = float(np.mean(arr > 0))
            n = int(n * max(frac, 0.08))
    return {
        "city_id": city_id,
        "population_exposed": n,
        "available": True,
        "data_status": "DEMO",
        "simulated": True,
        "reason": "DEMO population exposure total. Not an authoritative census raster.",
    }


def demo_evac_route(city_id: str) -> dict:
    from floodlens.application.city_data import create_city_registry

    city = create_city_registry().get_city(city_id)
    lon, lat = city.center_lon, city.center_lat
    coordinates = [
        [lon - 0.06, lat - 0.05],
        [lon - 0.03, lat - 0.02],
        [lon, lat],
        [lon + 0.04, lat + 0.03],
    ]
    return {
        "status": "DEMO",
        "reason": (
            "DEMO planning polyline for UI walkthrough. Not an official evacuation order "
            "and not a verified safe route."
        ),
        "features": [
            {
                "id": f"demo-evac-{city_id}",
                "name": "DEMO planning corridor",
                "kind": "DEMO EVACUATION ROUTE",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "data_status": "DEMO",
            }
        ],
    }


def demo_resource_inventory() -> dict:
    values = {
        "rescue_boats": 6,
        "rescue_workers": 24,
        "medical_teams": 4,
        "pumps": 8,
        "food": 1200,
        "water": 800,
        "shelter_capacity": 450,
    }
    return {
        key: {
            "kind": "DEMO RESOURCE INVENTORY",
            "status": "DEMO",
            "value": value,
            "reason": DEMO_REASON,
        }
        for key, value in values.items()
    }


def demo_event_row() -> dict:
    return {
        "event_id": DEMO_EVENT_ID,
        "name": "DEMO Dhaka monsoon (fixture)",
        "label": "DEMO Dhaka monsoon (fixture)",
        "start": DEMO_EVENT_TIME,
        "peak": DEMO_EVENT_TIME,
        "end": "2020-07-18T00:00:00+00:00",
        "regions": ["dhaka"],
        "basin_ids": [],
        "flood_mechanism": "monsoon",
        "observation_source": "demo-historical-fixture",
        "n_observations": 1,
        "data_status": "DEMO",
        "quality_status": "demo_fixture",
        "label_kind": "OBSERVED",
        "spatial_resolution_m": None,
        "dataset_version": "demo-history-v0",
        "catalog_family": "DEMO",
        "pixels_flood": 48,
        "pixels_dry": 16,
        "pixels_unknown": 0,
        "unknown_fraction": 0.0,
        "cube_eligible": False,
        "gfm_available": False,
        "observed_flood_extent": "DEMO binary extent artifact",
        "semantic_type": "OBSERVATION",
        "note": "DEMO paired event for forecast-vs-reality UI. Not a Copernicus product.",
    }


def demo_event_observation() -> dict:
    return {
        "observation_id": f"{DEMO_EVENT_ID}-obs",
        "timestamp": DEMO_EVENT_TIME,
        "source": "demo-historical-fixture",
        "resolution_m": None,
        "dataset_version": "demo-history-v0",
        "label_kind": "OBSERVED",
        "semantic_type": "OBSERVATION",
        "target_definition": "BINARY_FLOOD_EXTENT",
        "valid_coverage": 1.0,
        "unknown_coverage": 0.0,
        "flood_extent": {
            "n_flood": 48,
            "n_dry": 16,
            "n_unknown": 0,
            "units": "pixels",
            "unknown_code": 255,
        },
        "overlay_available": True,
        "resolution_note": "DEMO 8x8 binary extent. Not a SAR scene.",
        "city_ids": ["dhaka"],
        "data_status": "DEMO",
    }


def demo_forecast_prediction() -> dict:
    ensure_demo_history_artifact()
    return {
        "prediction_id": "demo-issued-forecast",
        "artifact_id": DEMO_FORECAST_ARTIFACT,
        "model": "DEMO issued flood-map forecast",
        "model_version": "demo-forecast-v0",
        "dataset": "demo-history-v0",
        "issue_time": DEMO_EVENT_TIME,
        "forecast_horizon": "24h",
        "target_definition": "BINARY_FLOOD_EXTENT",
        "spatial_resolution": None,
        "artifact": DEMO_FORECAST_ARTIFACT,
        "status": "DEMO",
        "semantic_type": "FORECAST",
        "kind": "FORECAST",
        "city_id": "dhaka",
        "units": "binary_flood_extent",
        "note": "DEMO issued forecast map for UI compare. Not a validated historical forecast.",
        "data_status": "DEMO",
    }


def demo_compare_metrics() -> dict:
    return {
        "iou": 0.5,
        "dice": 0.667,
        "precision": 0.667,
        "recall": 0.75,
        "data_status": "DEMO",
        "reason": "DEMO forecast-vs-reality pair. Not a validated model skill score.",
    }


def ensure_demo_history_artifact() -> str:
    from floodlens.application.artifact_store import get_artifact, put_depth_artifact

    if get_artifact(DEMO_FORECAST_ARTIFACT) is None:
        pred = np.array(
            [
                [1, 1, 1, 0, 0, 0, 0, 0],
                [1, 1, 0, 0, 0, 0, 0, 0],
                [1, 1, 1, 1, 0, 0, 0, 0],
                [0, 1, 1, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
            ],
            dtype=np.float64,
        )
        put_depth_artifact(
            DEMO_FORECAST_ARTIFACT,
            pred,
            {
                "kind": "extent_map",
                "event_id": DEMO_EVENT_ID,
                "data_status": "DEMO",
                "simulated": True,
                "semantic_type": "FORECAST",
                "note": "DEMO binary flood extent. Not a validated issued forecast.",
            },
        )
    return DEMO_FORECAST_ARTIFACT
