"""Optional PostGIS repository. Used only when DATABASE_URL is set and psycopg works."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import uuid4

from floodlens.application.canonical import (
    FloodState,
    InfrastructureRecord,
    ModelDomain,
    RainfallObservation,
    RiverObservation,
    ScenarioRecord,
    TerrainDataset,
)
from floodlens.application.platform_store import get_platform_store
from floodlens.application.repository import InMemoryRepository, PlatformRepository


def _connect(url: str):
    import psycopg

    return psycopg.connect(url)


class PostGISRepository(PlatformRepository):
    """Parameterized SQL only. Rasters are URIs, not bytea blobs."""

    def __init__(self, database_url: str):
        self._url = database_url
        self._legacy = get_platform_store()
        self._mirror = InMemoryRepository(self._legacy)

    def store(self):
        return self._legacy

    def _conn(self):
        return _connect(self._url)

    def put_infrastructure(self, record: InfrastructureRecord) -> InfrastructureRecord:
        params = [
            record.id,
            record.city_id,
            record.asset_type,
            record.name,
            record.source,
            record.source_osm_id,
            record.retrieved_at,
            record.data_status,
        ]
        with self._conn() as conn:
            with conn.cursor() as cur:
                if record.lon is not None and record.lat is not None:
                    cur.execute(
                        """
                        INSERT INTO infrastructure
                        (id, city_id, asset_type, name, source, source_osm_id, retrieved_at, data_status, geom)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326))
                        ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, data_status=EXCLUDED.data_status
                        """,
                        params + [record.lon, record.lat],
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO infrastructure
                        (id, city_id, asset_type, name, source, source_osm_id, retrieved_at, data_status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
                        """,
                        params,
                    )
            conn.commit()
        return self._mirror.put_infrastructure(record)

    def list_infrastructure(
        self,
        city_id: Optional[str] = None,
        asset_type: Optional[str] = None,
        bbox: Optional[tuple] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[InfrastructureRecord]:
        return self._mirror.list_infrastructure(city_id, asset_type, bbox, limit, offset)

    def get_infrastructure(self, record_id: str) -> Optional[InfrastructureRecord]:
        return self._mirror.get_infrastructure(record_id)

    def put_rainfall(self, observation: RainfallObservation) -> RainfallObservation:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meteorological_observations
                    (id, city_id, value_mm, unit, observed_at, valid_at, kind, provider, data_status, retrieved_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET value_mm=EXCLUDED.value_mm, data_status=EXCLUDED.data_status
                    """,
                    (
                        f"met_{observation.city_id}_{observation.observed_at}_{observation.kind}",
                        observation.city_id,
                        observation.value_mm,
                        observation.unit,
                        observation.observed_at,
                        observation.valid_at,
                        observation.kind,
                        observation.provider,
                        observation.data_status,
                        observation.retrieved_at,
                    ),
                )
            conn.commit()
        return self._mirror.put_rainfall(observation)

    def list_rainfall(self, city_id=None, kind=None):
        return self._mirror.list_rainfall(city_id, kind)

    def put_terrain(self, dataset: TerrainDataset) -> TerrainDataset:
        bounds = dataset.bounds or {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO terrain_datasets
                    (id, city_id, uri, crs, west, south, east, north, nodata,
                     min_elevation, max_elevation, source, data_status, freshness, version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET uri=EXCLUDED.uri, data_status=EXCLUDED.data_status
                    """,
                    (
                        dataset.id,
                        dataset.city_id,
                        dataset.uri,
                        dataset.crs,
                        bounds.get("west"),
                        bounds.get("south"),
                        bounds.get("east"),
                        bounds.get("north"),
                        dataset.nodata,
                        dataset.min_elevation,
                        dataset.max_elevation,
                        dataset.source,
                        dataset.data_status,
                        dataset.freshness,
                        dataset.version,
                    ),
                )
            conn.commit()
        return self._mirror.put_terrain(dataset)

    def get_terrain(self, city_id: str):
        return self._mirror.get_terrain(city_id)

    def put_river_observation(self, observation: RiverObservation) -> RiverObservation:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO river_observations
                    (id, river_id, segment_id, observed_at, water_level_m, discharge_m3s, source, data_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET water_level_m=EXCLUDED.water_level_m,
                        discharge_m3s=EXCLUDED.discharge_m3s, data_status=EXCLUDED.data_status
                    """,
                    (
                        f"riv_{observation.river_id}_{observation.observed_at or 'none'}",
                        observation.river_id,
                        observation.segment_id,
                        observation.observed_at,
                        observation.water_level_m,
                        observation.discharge_m3s,
                        observation.source,
                        observation.data_status,
                    ),
                )
            conn.commit()
        return self._mirror.put_river_observation(observation)

    def list_river_observations(self, river_id: str):
        return self._mirror.list_river_observations(river_id)

    def put_scenario(self, scenario: ScenarioRecord) -> ScenarioRecord:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scenarios
                    (id, city_id, rainfall_multiplier, river_level_delta_m, upstream_discharge_multiplier,
                     created_at, creator, model_version, simulation_version, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status
                    """,
                    (
                        scenario.id,
                        scenario.city_id,
                        scenario.rainfall_multiplier,
                        scenario.river_level_delta_m,
                        scenario.upstream_discharge_multiplier,
                        scenario.created_at,
                        scenario.creator,
                        scenario.model_version,
                        scenario.simulation_version,
                        scenario.status,
                    ),
                )
            conn.commit()
        return self._mirror.put_scenario(scenario)

    def get_scenario(self, scenario_id: str):
        return self._mirror.get_scenario(scenario_id)

    def list_scenarios(self, city_id=None):
        return self._mirror.list_scenarios(city_id)

    def put_domain(self, domain: ModelDomain):
        bounds = domain.bounds or {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO model_domains
                    (domain_id, city_id, crs, nx, ny, lx_m, ly_m, west, south, east, north,
                     terrain_source, created_at, input_snapshot_ids, data_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (domain_id) DO UPDATE SET terrain_source=EXCLUDED.terrain_source
                    """,
                    (
                        domain.domain_id,
                        domain.city_id,
                        domain.crs,
                        domain.nx,
                        domain.ny,
                        domain.lx_m,
                        domain.ly_m,
                        bounds.get("west"),
                        bounds.get("south"),
                        bounds.get("east"),
                        bounds.get("north"),
                        domain.terrain_source,
                        domain.created_at,
                        json.dumps(domain.input_snapshot_ids),
                        domain.data_status,
                    ),
                )
            conn.commit()
        return self._mirror.put_domain(domain)

    def put_flood_state(self, state: FloodState):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO flood_states
                    (id, city_id, horizon_hours, timestamp, valid_at, generated_at, source,
                     data_status, artifact_uri, max_depth_m, flooded_area_km2, flood_fraction,
                     validation_status, model_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                        max_depth_m=EXCLUDED.max_depth_m,
                        validation_status=EXCLUDED.validation_status,
                        artifact_uri=EXCLUDED.artifact_uri
                    """,
                    (
                        state.id,
                        state.city_id,
                        state.horizon_hours,
                        state.timestamp,
                        state.valid_at,
                        state.generated_at,
                        state.source,
                        state.data_status,
                        state.artifact_uri,
                        state.max_depth_m,
                        state.flooded_area_km2,
                        state.flood_fraction,
                        state.validation_status,
                        state.model_id,
                    ),
                )
            conn.commit()
        return self._mirror.put_flood_state(state)

    def list_flood_states(self, city_id, horizon_hours=None):
        return self._mirror.list_flood_states(city_id, horizon_hours)

    def put_forecast_run(self, payload):
        run_id = payload.get("id") or f"frun_{uuid4().hex[:12]}"
        payload = {**payload, "id": run_id}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO forecast_runs (id, city_id, generated_at, model_id, data_status)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET data_status=EXCLUDED.data_status
                    """,
                    (
                        run_id,
                        payload.get("city_id"),
                        payload.get("generated_at"),
                        payload.get("model_id") or "PHYSICS-BASELINE-v0.1",
                        payload.get("data_status") or "UNAVAILABLE",
                    ),
                )
                for point in payload.get("horizons") or []:
                    if not isinstance(point, dict) or point.get("horizon_hours") is None:
                        continue
                    cur.execute(
                        """
                        INSERT INTO forecast_points
                        (id, run_id, horizon_hours, timestamp, valid_at, probability,
                         expected_depth, severity, confidence, confidence_kind)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            f"{run_id}_{point['horizon_hours']}",
                            run_id,
                            point["horizon_hours"],
                            point.get("timestamp") or payload.get("generated_at"),
                            point.get("valid_at") or payload.get("generated_at"),
                            point.get("probability") or point.get("flood_probability"),
                            point.get("expected_depth"),
                            point.get("severity") or point.get("expected_severity"),
                            point.get("confidence"),
                            point.get("confidence_kind"),
                        ),
                    )
            conn.commit()
        return self._mirror.put_forecast_run(payload)

    def get_latest_forecast(self, city_id):
        return self._mirror.get_latest_forecast(city_id)
