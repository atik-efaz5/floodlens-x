"""Repository interface. APIs/services never talk SQL."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import List, Optional

from floodlens.application.canonical import (
    FloodState,
    InfrastructureRecord,
    ModelDomain,
    RainfallObservation,
    RiverObservation,
    ScenarioRecord,
    TerrainDataset,
)
from floodlens.application.platform_store import PlatformStore, get_platform_store, reset_platform_store


class PlatformRepository(ABC):
    @abstractmethod
    def put_infrastructure(self, record: InfrastructureRecord) -> InfrastructureRecord:
        raise NotImplementedError

    @abstractmethod
    def list_infrastructure(
        self,
        city_id: Optional[str] = None,
        asset_type: Optional[str] = None,
        bbox: Optional[tuple] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[InfrastructureRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_infrastructure(self, record_id: str) -> Optional[InfrastructureRecord]:
        raise NotImplementedError

    @abstractmethod
    def put_rainfall(self, observation: RainfallObservation) -> RainfallObservation:
        raise NotImplementedError

    @abstractmethod
    def list_rainfall(
        self,
        city_id: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[RainfallObservation]:
        raise NotImplementedError

    @abstractmethod
    def put_terrain(self, dataset: TerrainDataset) -> TerrainDataset:
        raise NotImplementedError

    @abstractmethod
    def get_terrain(self, city_id: str) -> Optional[TerrainDataset]:
        raise NotImplementedError

    @abstractmethod
    def put_river_observation(self, observation: RiverObservation) -> RiverObservation:
        raise NotImplementedError

    @abstractmethod
    def list_river_observations(self, river_id: str) -> List[RiverObservation]:
        raise NotImplementedError

    @abstractmethod
    def put_scenario(self, scenario: ScenarioRecord) -> ScenarioRecord:
        raise NotImplementedError

    @abstractmethod
    def get_scenario(self, scenario_id: str) -> Optional[ScenarioRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_scenarios(self, city_id: Optional[str] = None) -> List[ScenarioRecord]:
        raise NotImplementedError

    @abstractmethod
    def put_domain(self, domain: ModelDomain) -> ModelDomain:
        raise NotImplementedError

    @abstractmethod
    def put_flood_state(self, state: FloodState) -> FloodState:
        raise NotImplementedError

    @abstractmethod
    def list_flood_states(self, city_id: str, horizon_hours: Optional[int] = None) -> List[FloodState]:
        raise NotImplementedError

    @abstractmethod
    def put_forecast_run(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_latest_forecast(self, city_id: str) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def store(self) -> PlatformStore:
        """Legacy dict store used by Phase-1 services until fully migrated."""
        raise NotImplementedError


def _in_bbox(lon: Optional[float], lat: Optional[float], bbox: tuple) -> bool:
    west, south, east, north = bbox
    if lon is None or lat is None:
        return False
    return west <= lon <= east and south <= lat <= north


class InMemoryRepository(PlatformRepository):
    def __init__(self, store: Optional[PlatformStore] = None):
        self._store = store or get_platform_store()
        self._rainfall: List[RainfallObservation] = []
        self._terrain: dict = {}
        self._river_obs: List[RiverObservation] = []
        self._scenarios: dict = {}
        self._domains: dict = {}
        self._flood_states: list = []
        self._forecast_runs: list = []

    def store(self) -> PlatformStore:
        return self._store

    def put_infrastructure(self, record: InfrastructureRecord) -> InfrastructureRecord:
        self._store.put_asset(record.to_dict())
        return record

    def list_infrastructure(
        self,
        city_id: Optional[str] = None,
        asset_type: Optional[str] = None,
        bbox: Optional[tuple] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[InfrastructureRecord]:
        rows = list(self._store.assets.values())
        if city_id:
            rows = [r for r in rows if r.get("city_id") == city_id]
        if asset_type:
            rows = [r for r in rows if r.get("asset_type") == asset_type]
        records = [_asset_to_record(r) for r in rows]
        if bbox:
            records = [
                r
                for r in records
                if _in_bbox(r.lon, r.lat, bbox)
                or (r.coordinates and any(_in_bbox(c[0], c[1], bbox) for c in r.coordinates))
            ]
        return records[offset : offset + min(limit, 500)]

    def get_infrastructure(self, record_id: str) -> Optional[InfrastructureRecord]:
        row = self._store.assets.get(record_id)
        return _asset_to_record(row) if row else None

    def put_rainfall(self, observation: RainfallObservation) -> RainfallObservation:
        self._rainfall.append(observation)
        self._store.put_observation(
            {
                "city_id": observation.city_id,
                "variable": "precipitation_mm",
                "value": observation.value_mm,
                "observed_at": observation.observed_at,
                "kind": observation.kind,
                "source": observation.provider,
                "simulated": observation.kind == "SIMULATED" or observation.data_status == "DEMO",
                "data_status": observation.data_status,
            }
        )
        return observation

    def list_rainfall(self, city_id: Optional[str] = None, kind: Optional[str] = None):
        rows = self._rainfall
        if city_id:
            rows = [r for r in rows if r.city_id == city_id]
        if kind:
            rows = [r for r in rows if r.kind == kind]
        if rows:
            return rows
        legacy = self._store.observations_for("precipitation_mm", city_id)
        mapped = [
            RainfallObservation(
                city_id=row.get("city_id") or city_id or "",
                value_mm=float(row["value"]),
                unit="mm",
                observed_at=row["observed_at"],
                valid_at=row["observed_at"],
                kind=row.get("kind") or ("SIMULATED" if row.get("simulated") else "OBSERVED"),
                provider=row.get("source", "unknown"),
                data_status=row.get("data_status") or ("DEMO" if row.get("simulated") else "REAL"),
                retrieved_at=row["observed_at"],
            )
            for row in legacy
        ]
        if kind:
            mapped = [r for r in mapped if r.kind == kind]
        return mapped

    def put_terrain(self, dataset: TerrainDataset) -> TerrainDataset:
        self._terrain[dataset.city_id] = dataset
        self._store.artifacts[dataset.id] = dataset.to_dict()
        return dataset

    def get_terrain(self, city_id: str) -> Optional[TerrainDataset]:
        if city_id in self._terrain:
            return self._terrain[city_id]
        raw = self._store.artifacts.get(f"dem-{city_id}") or self._store.artifacts.get(f"terrain-{city_id}")
        if not raw:
            return None
        return TerrainDataset(
            id=raw.get("id", f"dem-{city_id}"),
            city_id=city_id,
            uri=raw.get("uri", ""),
            crs=raw.get("crs", "EPSG:4326"),
            bounds=raw.get("bounds") or {},
            resolution_deg=None,
            nodata=raw.get("nodata"),
            min_elevation=raw.get("min_elevation"),
            max_elevation=raw.get("max_elevation"),
            source=raw.get("source", "unknown"),
            data_status=raw.get("data_status", "UNAVAILABLE"),
            freshness=raw.get("freshness", "STATIC"),
            version=raw.get("version"),
        )

    def put_river_observation(self, observation: RiverObservation) -> RiverObservation:
        self._river_obs.append(observation)
        return observation

    def list_river_observations(self, river_id: str) -> List[RiverObservation]:
        return [o for o in self._river_obs if o.river_id == river_id]

    def put_scenario(self, scenario: ScenarioRecord) -> ScenarioRecord:
        self._scenarios[scenario.id] = scenario
        return scenario

    def get_scenario(self, scenario_id: str) -> Optional[ScenarioRecord]:
        return self._scenarios.get(scenario_id)

    def list_scenarios(self, city_id: Optional[str] = None):
        rows = list(self._scenarios.values())
        if city_id:
            rows = [s for s in rows if s.city_id == city_id]
        return rows

    def put_domain(self, domain: ModelDomain) -> ModelDomain:
        self._domains[domain.domain_id] = domain
        return domain

    def put_flood_state(self, state: FloodState) -> FloodState:
        self._flood_states = [s for s in self._flood_states if s.id != state.id]
        self._flood_states.append(state)
        return state

    def list_flood_states(self, city_id: str, horizon_hours: Optional[int] = None):
        rows = [s for s in self._flood_states if s.city_id == city_id]
        if horizon_hours is not None:
            rows = [s for s in rows if s.horizon_hours == horizon_hours]
        return rows

    def put_forecast_run(self, payload: dict) -> dict:
        self._forecast_runs.append(payload)
        return payload

    def get_latest_forecast(self, city_id: str) -> Optional[dict]:
        rows = [r for r in self._forecast_runs if r.get("city_id") == city_id]
        return rows[-1] if rows else None


def _asset_to_record(row: dict) -> InfrastructureRecord:
    return InfrastructureRecord(
        id=row["id"],
        city_id=row["city_id"],
        asset_type=row["asset_type"],
        name=row.get("name"),
        lon=row.get("lon"),
        lat=row.get("lat"),
        coordinates=row.get("coordinates"),
        source=row.get("source", "unknown"),
        source_osm_id=row.get("source_osm_id") or str(row.get("properties", {}).get("osm_id", "") or "") or None,
        retrieved_at=row.get("retrieved_at"),
        data_status=row.get("data_status", "DEMO"),
        properties=row.get("properties") or {},
    )


_REPO: Optional[PlatformRepository] = None


def get_repository() -> PlatformRepository:
    global _REPO
    if _REPO is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            try:
                from floodlens.application.postgis_repository import PostGISRepository

                _REPO = PostGISRepository(database_url)
            except Exception:
                _REPO = InMemoryRepository()
        else:
            _REPO = InMemoryRepository()
    return _REPO


def reset_repository() -> None:
    global _REPO
    reset_platform_store()
    _REPO = InMemoryRepository()
