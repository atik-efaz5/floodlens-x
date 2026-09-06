"""Terrain dataset ingest: windowed GeoTIFF metadata, never full-array in Postgres."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from floodlens.application.canonical import TerrainDataset
from floodlens.application.data_contracts import envelope
from floodlens.application.dem_manager import HAS_RASTERIO, DEMManager
from floodlens.application.repository import get_repository


def ingest_terrain(city_id: str, bounds: dict, path: Optional[str] = None) -> dict:
    uri = path or os.environ.get("FLOODLENS_DEM_PATH")
    repo = get_repository()
    if not uri or not Path(uri).exists():
        from floodlens.application.demo_fixtures import demo_fixtures_enabled, demo_terrain_dataset

        if demo_fixtures_enabled():
            dataset = demo_terrain_dataset(city_id, bounds)
            repo.put_terrain(dataset)
            public = dataset.to_dict()
            return {
                "city_id": city_id,
                "available": True,
                "reason": "DEMO hillshade preview. Elevations are not a GeoTIFF DEM and are not passed to the solver.",
                "dataset": public,
                "overlay_artifact_id": f"demo-terrain-hillshade-{city_id}",
                "provenance": envelope(
                    data_status="DEMO",
                    provider="demo-terrain-generator",
                    dataset="terrain",
                    freshness="SNAPSHOT",
                    simulated=True,
                    fallback_used=True,
                ),
            }
        dataset = TerrainDataset(
            id=f"terrain-{city_id}",
            city_id=city_id,
            uri=uri or "",
            crs="EPSG:4326",
            bounds=bounds,
            resolution_deg=None,
            nodata=None,
            min_elevation=None,
            max_elevation=None,
            source="unconfigured",
            data_status="UNAVAILABLE",
            freshness="STATIC",
            version=None,
        )
        repo.put_terrain(dataset)
        return {
            "city_id": city_id,
            "available": False,
            "reason": "FLOODLENS_DEM_PATH is unset or file missing. Elevations are not invented.",
            "dataset": dataset.to_dict(),
            "provenance": envelope(
                data_status="UNAVAILABLE",
                provider="DEM",
                dataset="terrain",
                freshness="STATIC",
            ),
        }

    if not HAS_RASTERIO:
        dataset = TerrainDataset(
            id=f"terrain-{city_id}",
            city_id=city_id,
            uri=str(Path(uri).resolve()),
            crs="EPSG:4326",
            bounds=bounds,
            resolution_deg=None,
            nodata=None,
            min_elevation=None,
            max_elevation=None,
            source="GeoTIFF",
            data_status="UNAVAILABLE",
            freshness="STATIC",
            version=Path(uri).name,
        )
        repo.put_terrain(dataset)
        return {
            "city_id": city_id,
            "available": False,
            "reason": "rasterio is required to read GeoTIFF metadata.",
            "dataset": dataset.to_dict(),
            "provenance": envelope(
                data_status="UNAVAILABLE",
                provider="DEM",
                dataset="terrain",
                freshness="STATIC",
            ),
        }

    stats = DEMManager.windowed_stats(uri)
    dataset = TerrainDataset(
        id=f"terrain-{city_id}",
        city_id=city_id,
        uri=stats["uri"],
        crs=stats["crs"],
        bounds=stats["bounds"],
        resolution_deg=stats["resolution_deg"],
        nodata=stats["nodata"],
        min_elevation=stats["min_elevation"],
        max_elevation=stats["max_elevation"],
        source="GeoTIFF",
        data_status="REAL",
        freshness="STATIC",
        version=Path(uri).name,
    )
    repo.put_terrain(dataset)
    return {
        "city_id": city_id,
        "available": True,
        "dataset": dataset.to_dict(),
        "window": {
            "shape": stats["window_shape"],
            "full_shape": stats["full_shape"],
        },
        "provenance": envelope(
            data_status="REAL",
            provider="GeoTIFF",
            dataset="terrain",
            freshness="STATIC",
            source_version=dataset.version,
        ),
        "note": "Full raster is not loaded into application memory; stats from a 64x64 window.",
    }
