"""Geospatial contracts and coordinate bridge for web/API integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.state import SimulationState

DEFAULT_VISUALIZATION_LAYERS: Tuple[str, ...] = (
    "depth",
    "velocity",
    "max_depth",
    "flood_extent",
)

SUNAMGANJ_BOUNDS = {
    "west": 91.20,
    "south": 24.80,
    "east": 91.50,
    "north": 25.10,
}

SUNAMGANJ_CENTER = {
    "latitude": 24.95,
    "longitude": 91.35,
    "label": "Sunamganj",
}

DHAKA_CENTER = {
    "latitude": 23.8103,
    "longitude": 90.4125,
    "label": "Dhaka",
}


@dataclass(frozen=True)
class GeographicBounds:
    """Geographic bounding box in WGS84 degrees."""

    west: float
    south: float
    east: float
    north: float

    def to_dict(self) -> dict:
        return {
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
        }


@dataclass(frozen=True)
class CenterCoordinates:
    """Scenario center point in WGS84."""

    latitude: float
    longitude: float
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "label": self.label,
        }


@dataclass(frozen=True)
class TimeRange:
    """Simulation time window in seconds."""

    start_seconds: float
    end_seconds: float

    def to_dict(self) -> dict:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }


@dataclass(frozen=True)
class GridReference:
    """Grid-to-geographic coordinate mapping metadata.

    Convention:
    - origin_x, origin_y are the southwest corner of the domain.
    - cell_center_convention='cell_center' means matrix [0, 0] is the
      southernmost, westernmost cell center.
    - row_orientation='south_to_north' means row index increases northward.
    """

    nx: int
    ny: int
    dx: float
    dy: float
    origin_x: float
    origin_y: float
    crs: str = "EPSG:4326"
    cell_center_convention: str = "cell_center"
    row_orientation: str = "south_to_north"

    def __post_init__(self):
        """Validate grid parameters."""
        if self.nx <= 0 or self.ny <= 0:
            raise ValueError("Grid dimensions nx and ny must be positive")
        if self.dx <= 0 or self.dy <= 0:
            raise ValueError("Grid spacing dx and dy must be positive")
        if not self.crs:
            raise ValueError("CRS must not be empty")
        if self.cell_center_convention not in ("cell_center", "cell_corner"):
            raise ValueError(
                f"Unsupported cell_center_convention: {self.cell_center_convention}"
            )
        if self.row_orientation not in ("south_to_north", "north_to_south"):
            raise ValueError(f"Unsupported row_orientation: {self.row_orientation}")

    def to_dict(self) -> dict:
        return {
            "nx": self.nx,
            "ny": self.ny,
            "dx": self.dx,
            "dy": self.dy,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "crs": self.crs,
            "cell_center_convention": self.cell_center_convention,
            "row_orientation": self.row_orientation,
        }


@dataclass(frozen=True)
class CityMetadata:
    """Complete metadata for a supported city/region."""

    city_id: str
    name: str
    country: str
    region: str
    center_lat: float
    center_lon: float
    bounds: GeographicBounds
    crs: str = "EPSG:4326"
    default_zoom: int = 11
    min_zoom: int = 8
    max_zoom: int = 16
    supported_layers: Tuple[str, ...] = DEFAULT_VISUALIZATION_LAYERS
    grid_metadata: Optional[GridReference] = None
    is_default_city: bool = False

    def __post_init__(self):
        """Validate city metadata."""
        if not self.city_id or not self.city_id.strip():
            raise ValueError("city_id must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.country or not self.country.strip():
            raise ValueError("country must not be empty")
        if not self.region or not self.region.strip():
            raise ValueError("region must not be empty")
        if not np.isfinite(self.center_lat) or not np.isfinite(self.center_lon):
            raise ValueError("center_lat and center_lon must be finite numbers")
        if self.center_lat < -90 or self.center_lat > 90:
            raise ValueError("center_lat must be in range [-90, 90]")
        if self.center_lon < -180 or self.center_lon > 180:
            raise ValueError("center_lon must be in range [-180, 180]")
        if self.bounds.west >= self.bounds.east:
            raise ValueError("bounds.west must be < bounds.east")
        if self.bounds.south >= self.bounds.north:
            raise ValueError("bounds.south must be < bounds.north")
        if self.default_zoom < self.min_zoom or self.default_zoom > self.max_zoom:
            raise ValueError("default_zoom must be between min_zoom and max_zoom")
        if self.min_zoom < 0 or self.max_zoom > 28:
            raise ValueError("Zoom levels must be in range [0, 28]")
        if not self.crs or not self.crs.strip():
            raise ValueError("CRS must not be empty")
        if not self.supported_layers:
            raise ValueError("supported_layers must not be empty")

    def to_dict(self) -> dict:
        return {
            "city_id": self.city_id,
            "name": self.name,
            "country": self.country,
            "region": self.region,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "bounds": self.bounds.to_dict(),
            "crs": self.crs,
            "default_zoom": self.default_zoom,
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "supported_layers": list(self.supported_layers),
            "grid_metadata": self.grid_metadata.to_dict() if self.grid_metadata else None,
            "is_default_city": self.is_default_city,
        }


@dataclass(frozen=True)
class ScenarioMetadataV2:
    """Extended scenario metadata with city association."""

    scenario_id: str
    city_id: str
    name: str
    description: str = ""
    bounds: GeographicBounds = None
    center: CenterCoordinates = None
    crs: str = "EPSG:4326"
    time_range: TimeRange = None
    visualization_layers: Tuple[str, ...] = DEFAULT_VISUALIZATION_LAYERS
    grid_metadata: Optional[GridReference] = None
    modeled_status: bool = False
    simulated_status: bool = False

    def __post_init__(self):
        """Validate scenario metadata."""
        if not self.scenario_id or not self.scenario_id.strip():
            raise ValueError("scenario_id must not be empty")
        if not self.city_id or not self.city_id.strip():
            raise ValueError("city_id must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("name must not be empty")

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "city_id": self.city_id,
            "name": self.name,
            "description": self.description,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "center": self.center.to_dict() if self.center else None,
            "crs": self.crs,
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "visualization_layers": list(self.visualization_layers),
            "grid_metadata": self.grid_metadata.to_dict() if self.grid_metadata else None,
            "modeled_status": self.modeled_status,
            "simulated_status": self.simulated_status,
        }


@dataclass(frozen=True)
class ScenarioMetadata:
    """Published scenario metadata for map clients (legacy compatibility)."""

    bounds: GeographicBounds
    center: CenterCoordinates
    crs: str
    time_range: TimeRange
    visualization_layers: Tuple[str, ...] = DEFAULT_VISUALIZATION_LAYERS

    def to_dict(self) -> dict:
        return {
            "bounds": self.bounds.to_dict(),
            "center": self.center.to_dict(),
            "crs": self.crs,
            "time_range": self.time_range.to_dict(),
            "visualization_layers": list(self.visualization_layers),
        }


@dataclass
class ScenarioRunRequest:
    """API payload for launching a scenario simulation."""

    nx: int = 50
    ny: int = 50
    rainfall_rate: float = 1.0e-5
    duration_seconds: float = 5.0
    scenario: str = "sunamganj"


@dataclass
class ScenarioRunResponse:
    """Summary metrics returned after a scenario run."""

    status: str
    success: bool
    max_depth_m: float
    flooded_area_km2: float
    simulation_time_s: float
    nx: int
    ny: int
    available_times: Tuple[float, ...] = ()
    start_time: float = 0.0
    end_time: float = 0.0
    city_id: Optional[str] = None
    scenario_id: Optional[str] = None

    def to_dict(self) -> dict:
        payload = {
            "status": self.status,
            "success": self.success,
            "max_depth_m": self.max_depth_m,
            "flooded_area_km2": self.flooded_area_km2,
            "simulation_time_s": self.simulation_time_s,
            "nx": self.nx,
            "ny": self.ny,
        }
        if self.available_times:
            payload["available_times"] = list(self.available_times)
            payload["start_time"] = self.start_time
            payload["end_time"] = self.end_time
        if self.city_id is not None:
            payload["city_id"] = self.city_id
        if self.scenario_id is not None:
            payload["scenario_id"] = self.scenario_id
        return payload


@dataclass
class CellInspection:
    """Cell-level hydrodynamic statistics at a geographic point."""

    latitude: float
    longitude: float
    row: int
    column: int
    depth_m: float
    velocity_m_s: float
    max_depth_m: float
    is_flooded: bool
    within_bounds: bool

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "row": self.row,
            "column": self.column,
            "depth_m": self.depth_m,
            "velocity_m_s": self.velocity_m_s,
            "max_depth_m": self.max_depth_m,
            "is_flooded": self.is_flooded,
            "within_bounds": self.within_bounds,
        }


@dataclass
class ScenarioSession:
    """In-memory bridge between geographic coordinates and simulation grids."""

    metadata: ScenarioMetadata
    config: SimulationConfig
    state: SimulationState | None = None
    max_depth_map: np.ndarray | None = None
    h_dry_threshold: float = 1e-3

    @classmethod
    def default_sunamganj(cls) -> ScenarioSession:
        bounds = GeographicBounds(**SUNAMGANJ_BOUNDS)
        center = CenterCoordinates(**SUNAMGANJ_CENTER)
        metadata = ScenarioMetadata(
            bounds=bounds,
            center=center,
            crs="EPSG:4326",
            time_range=TimeRange(start_seconds=0.0, end_seconds=0.0),
        )
        config = SimulationConfig(
            Nx=50,
            Ny=50,
            Lx=12000.0,
            Ly=12000.0,
            T_end=1.0,
            CFL=0.8,
            manning_n=0.035,
            h_dry_threshold=1e-3,
            boundary_condition="transmissive",
            name="Sunamganj_Web_Scenario",
        )
        return cls(metadata=metadata, config=config)

    def update_metadata_time_range(self, end_seconds: float) -> None:
        self.metadata = ScenarioMetadata(
            bounds=self.metadata.bounds,
            center=self.metadata.center,
            crs=self.metadata.crs,
            time_range=TimeRange(start_seconds=0.0, end_seconds=end_seconds),
            visualization_layers=self.metadata.visualization_layers,
        )

    def latlon_to_cell(self, latitude: float, longitude: float) -> Tuple[int, int, bool]:
        """Map WGS84 coordinates to matrix row/column indices."""
        bounds = self.metadata.bounds
        within_bounds = (
            bounds.west <= longitude <= bounds.east
            and bounds.south <= latitude <= bounds.north
        )

        lon_span = bounds.east - bounds.west
        lat_span = bounds.north - bounds.south
        if lon_span <= 0.0 or lat_span <= 0.0:
            raise ValueError("Invalid geographic bounds span.")

        col = int((longitude - bounds.west) / lon_span * self.config.Nx)
        row = int((latitude - bounds.south) / lat_span * self.config.Ny)

        col = int(np.clip(col, 0, self.config.Nx - 1))
        row = int(np.clip(row, 0, self.config.Ny - 1))
        return row, col, within_bounds

    def inspect_cell(self, latitude: float, longitude: float) -> CellInspection:
        """Return hydrodynamic statistics for the cell at a geographic point."""
        row, col, within_bounds = self.latlon_to_cell(latitude, longitude)

        if self.state is None:
            return CellInspection(
                latitude=latitude,
                longitude=longitude,
                row=row,
                column=col,
                depth_m=0.0,
                velocity_m_s=0.0,
                max_depth_m=0.0,
                is_flooded=False,
                within_bounds=within_bounds,
            )

        h = float(self.state.h[row, col])
        hu = float(self.state.U[row, col, 1])
        hv = float(self.state.U[row, col, 2])
        if h > self.h_dry_threshold:
            velocity = float(np.sqrt((hu / h) ** 2 + (hv / h) ** 2))
        else:
            velocity = 0.0

        max_depth = float(self.max_depth_map[row, col]) if self.max_depth_map is not None else h
        is_flooded = h > self.h_dry_threshold

        return CellInspection(
            latitude=latitude,
            longitude=longitude,
            row=row,
            column=col,
            depth_m=h,
            velocity_m_s=velocity,
            max_depth_m=max_depth,
            is_flooded=is_flooded,
            within_bounds=within_bounds,
        )
