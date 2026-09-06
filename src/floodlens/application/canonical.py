"""Canonical FLOODLENS-X records (provider-independent)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def _dict(obj) -> dict:
    return {k: v for k, v in asdict(obj).items()}


@dataclass
class InfrastructureRecord:
    id: str
    city_id: str
    asset_type: str
    name: Optional[str]
    lon: Optional[float]
    lat: Optional[float]
    coordinates: Optional[List[List[float]]] = None
    source: str = "unknown"
    source_osm_id: Optional[str] = None
    retrieved_at: Optional[str] = None
    data_status: str = "DEMO"
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _dict(self)

    def to_geojson_feature(self) -> Optional[dict]:
        if self.lon is not None and self.lat is not None:
            geom = {"type": "Point", "coordinates": [self.lon, self.lat]}
        elif self.coordinates:
            geom = {"type": "LineString", "coordinates": self.coordinates}
        else:
            return None
        props = {
            "id": self.id,
            "name": self.name,
            "asset_type": self.asset_type,
            "city_id": self.city_id,
            "source": self.source,
            "source_osm_id": self.source_osm_id,
            "data_status": self.data_status,
            "retrieved_at": self.retrieved_at,
        }
        props.update(self.properties)
        return {"type": "Feature", "geometry": geom, "properties": props}


@dataclass
class RainfallObservation:
    city_id: str
    value_mm: float
    unit: str
    observed_at: str
    valid_at: str
    kind: str  # OBSERVED | FORECAST | SIMULATED
    provider: str
    data_status: str
    retrieved_at: str
    lon: Optional[float] = None
    lat: Optional[float] = None

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class RiverObservation:
    river_id: str
    segment_id: Optional[str]
    observed_at: Optional[str]
    water_level_m: Optional[float]
    discharge_m3s: Optional[float]
    width_m: Optional[float] = None
    slope: Optional[float] = None
    trend: Optional[str] = None
    source: str = "unavailable"
    data_status: str = "UNAVAILABLE"

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class TerrainDataset:
    id: str
    city_id: str
    uri: str
    crs: str
    bounds: Dict[str, float]
    resolution_deg: Optional[Tuple[float, float]]
    nodata: Optional[float]
    min_elevation: Optional[float]
    max_elevation: Optional[float]
    source: str
    data_status: str
    freshness: str = "STATIC"
    version: Optional[str] = None

    def to_dict(self) -> dict:
        payload = _dict(self)
        if payload["resolution_deg"]:
            payload["resolution_deg"] = list(payload["resolution_deg"])
        return payload


@dataclass
class ForecastPoint:
    horizon_hours: int
    timestamp: str
    valid_at: str
    generated_at: str
    probability: float
    severity: float
    expected_depth: Optional[float]
    confidence: Optional[float]
    confidence_kind: Optional[str]
    risk_category: str
    model_id: str
    data_status: str

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class ScenarioRecord:
    id: str
    city_id: str
    rainfall_multiplier: float
    river_level_delta_m: float
    upstream_discharge_multiplier: float
    created_at: str
    creator: str
    model_version: str
    simulation_version: str
    status: str
    base_state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class SimulationResultRef:
    id: str
    scenario_id: str
    artifact_uri: str
    model_version: str
    completed_at: str
    status: str
    max_depth_m: Optional[float] = None
    flood_fraction: Optional[float] = None

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class Location:
    lon: float
    lat: float
    label: Optional[str] = None
    crs: str = "EPSG:4326"

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class Region:
    id: str
    name: str
    city_id: str
    bounds: Dict[str, float]
    crs: str = "EPSG:4326"
    data_status: str = "REAL"

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class RainfallForecast:
    city_id: str
    value_mm: float
    unit: str
    timestamp: str
    valid_at: str
    generated_at: str
    source: str
    data_status: str
    interpolation: str = "NEAREST_STATION"
    lon: Optional[float] = None
    lat: Optional[float] = None

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class ModelDomain:
    domain_id: str
    city_id: str
    bounds: Dict[str, float]
    crs: str
    nx: int
    ny: int
    lx_m: float
    ly_m: float
    terrain_source: str
    created_at: str
    input_snapshot_ids: List[str] = field(default_factory=list)
    data_status: str = "SIMULATED"

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class FloodState:
    id: str
    city_id: str
    horizon_hours: Optional[int]
    timestamp: str
    valid_at: str
    generated_at: str
    source: str
    data_status: str
    units: str
    spatial_ref: str
    artifact_uri: str
    max_depth_m: Optional[float]
    flooded_area_km2: Optional[float]
    flood_fraction: Optional[float]
    validation_status: str
    model_id: str
    forcing_clock: str = "meteorological_hours"
    solver_clock: str = "simulation_seconds"
    input_snapshot_ids: List[str] = field(default_factory=list)
    expected_extent: Optional[Dict[str, Any]] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class FloodForecast:
    city_id: str
    model_kind: str
    model_id: str
    generated_at: str
    horizons: List[Dict[str, Any]]
    data_status: str
    forcing_clock: str = "meteorological_hours"
    solver_clock: str = "simulation_seconds"
    input_snapshot_ids: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class ImpactAssessment:
    city_id: str
    timestamp: str
    generated_at: str
    source: str
    data_status: str
    flooded_counts: Dict[str, int]
    roads_affected: Dict[str, Any]
    polygons_affected: Dict[str, Any]
    accessibility: Dict[str, Any]
    population_exposed: Optional[float]
    flood_state_id: Optional[str] = None

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class HistoricalEvent:
    event_id: str
    name: str
    region: str
    start_time: Optional[str]
    end_time: Optional[str]
    observations: Dict[str, Any] = field(default_factory=dict)
    observed_flood_extent: Optional[str] = None
    observed_water_levels: Optional[list] = None
    model_reconstruction: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "unconfigured"
    data_status: str = "UNAVAILABLE"

    def to_dict(self) -> dict:
        return _dict(self)


@dataclass
class SimulationJob:
    job_id: str
    kind: str
    status: str
    city_id: str
    progress: float
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    result_reference: Optional[str]
    validation_status: Optional[str] = None

    def to_dict(self) -> dict:
        return _dict(self)
