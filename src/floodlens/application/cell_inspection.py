"""Read-only cell inspection against stored scenario results.

Coordinate-to-grid convention
-----------------------------
- CRS: WGS84 (EPSG:4326); longitude is the X axis, latitude is the Y axis.
- ``GridReference.origin_x`` / ``origin_y`` are the southwest domain corner and
  align with ``GeographicBounds.west`` / ``south``.
- ``cell_center_convention='cell_center'``: matrix indices reference cell centers.
- ``row_orientation='south_to_north'``: row 0 is the southernmost row; row
  increases northward. Column 0 is the westernmost column; column increases
  eastward (longitude).
- Geographic cell spacing is derived from bounds and grid dimensions:
  ``dx_geo = (east - west) / nx``, ``dy_geo = (north - south) / ny``.
- Cell ``(row, col)`` center:
  ``lon = west + (col + 0.5) * dx_geo``,
  ``lat = south + (row + 0.5) * dy_geo``.
- Domain membership uses closed intervals on west/south and east/north edges;
  points on the east or north boundary map to the last column/row.
- Points outside the domain are rejected (no clamping or wrapping).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from floodlens.application.comparison import (
    DEFAULT_DRY_THRESHOLD,
    ScenarioResultRecord,
    TIME_MATCH_TOLERANCE,
)
from floodlens.application.geospatial import GeographicBounds, GridReference
from floodlens.application.scenario_results import ScenarioResultStore


class InspectionError(ValueError):
    """Machine-readable inspection failure."""

    def __init__(self, error_code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class CellInspectionResult:
    """Modeled hydrodynamic statistics for one simulation grid cell."""

    city_id: str
    scenario_id: str
    time: float
    latitude: float
    longitude: float
    row: int
    column: int
    depth: float
    velocity: float
    maximum_depth: float
    flood_status: str
    grid: GridReference
    bounds: GeographicBounds
    crs: str
    h_dry_threshold: float
    modeled: bool = True

    def to_dict(self) -> dict:
        return {
            "city_id": self.city_id,
            "scenario_id": self.scenario_id,
            "time": self.time,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "row": self.row,
            "column": self.column,
            "depth": self.depth,
            "velocity": self.velocity,
            "maximum_depth": self.maximum_depth,
            "flood_status": self.flood_status,
            "modeled": self.modeled,
            "grid": self.grid.to_dict(),
            "bounds": self.bounds.to_dict(),
            "crs": self.crs,
            "h_dry_threshold": self.h_dry_threshold,
            "depth_m": self.depth,
            "velocity_m_s": self.velocity,
            "max_depth_m": self.maximum_depth,
            "is_flooded": self.flood_status == "flooded",
            "within_bounds": True,
        }


def validate_coordinates(latitude: float, longitude: float) -> None:
    """Reject invalid or non-finite coordinates."""
    if not np.isfinite(latitude) or not np.isfinite(longitude):
        raise InspectionError(
            "INVALID_COORDINATES",
            "Latitude and longitude must be finite numbers",
            {"latitude": latitude, "longitude": longitude},
        )
    if latitude < -90.0 or latitude > 90.0:
        raise InspectionError(
            "INVALID_COORDINATES",
            f"Latitude {latitude} is outside [-90, 90]",
            {"latitude": latitude},
        )
    if longitude < -180.0 or longitude > 180.0:
        raise InspectionError(
            "INVALID_COORDINATES",
            f"Longitude {longitude} is outside [-180, 180]",
            {"longitude": longitude},
        )


def _validate_grid_metadata(grid: GridReference, bounds: GeographicBounds) -> None:
    if grid.crs != "EPSG:4326":
        raise InspectionError(
            "GRID_METADATA_ERROR",
            f"Unsupported CRS for inspection: {grid.crs}",
            {"crs": grid.crs},
        )
    if grid.cell_center_convention != "cell_center":
        raise InspectionError(
            "GRID_METADATA_ERROR",
            f"Unsupported cell_center_convention: {grid.cell_center_convention}",
            {"cell_center_convention": grid.cell_center_convention},
        )
    if abs(grid.origin_x - bounds.west) > 1e-9 or abs(grid.origin_y - bounds.south) > 1e-9:
        raise InspectionError(
            "GRID_METADATA_ERROR",
            "Grid origin does not match geographic bounds southwest corner",
            {
                "origin_x": grid.origin_x,
                "origin_y": grid.origin_y,
                "bounds": bounds.to_dict(),
            },
        )


def latlon_to_grid_cell(
    latitude: float,
    longitude: float,
    grid: GridReference,
    bounds: GeographicBounds,
) -> Tuple[int, int]:
    """Map WGS84 coordinates to matrix row/column indices."""
    _validate_grid_metadata(grid, bounds)

    lon_span = bounds.east - bounds.west
    lat_span = bounds.north - bounds.south
    if lon_span <= 0.0 or lat_span <= 0.0:
        raise InspectionError(
            "GRID_METADATA_ERROR",
            "Geographic bounds span must be positive",
            {"bounds": bounds.to_dict()},
        )

    if (
        longitude < bounds.west
        or longitude > bounds.east
        or latitude < bounds.south
        or latitude > bounds.north
    ):
        raise InspectionError(
            "OUTSIDE_SIMULATION_DOMAIN",
            "Coordinates are outside the simulation domain bounds",
            {
                "latitude": latitude,
                "longitude": longitude,
                "bounds": bounds.to_dict(),
            },
        )

    dx_geo = lon_span / grid.nx
    dy_geo = lat_span / grid.ny

    if longitude == bounds.east:
        column = grid.nx - 1
    else:
        column = int((longitude - bounds.west) / dx_geo)
        if column < 0 or column >= grid.nx:
            raise InspectionError(
                "OUTSIDE_SIMULATION_DOMAIN",
                "Longitude does not map to a valid column index",
                {"longitude": longitude, "column": column, "nx": grid.nx},
            )

    south_row = int((latitude - bounds.south) / dy_geo)
    if latitude == bounds.north:
        south_row = grid.ny - 1
    if south_row < 0 or south_row >= grid.ny:
        raise InspectionError(
            "OUTSIDE_SIMULATION_DOMAIN",
            "Latitude does not map to a valid row index",
            {"latitude": latitude, "row": south_row, "ny": grid.ny},
        )

    if grid.row_orientation == "south_to_north":
        row = south_row
    elif grid.row_orientation == "north_to_south":
        row = grid.ny - 1 - south_row
    else:
        raise InspectionError(
            "GRID_METADATA_ERROR",
            f"Unsupported row_orientation: {grid.row_orientation}",
            {"row_orientation": grid.row_orientation},
        )

    return row, column


def _lookup_time_key(times: Tuple[float, ...], time_value: float) -> float:
    for existing in times:
        if abs(existing - time_value) <= TIME_MATCH_TOLERANCE:
            return float(existing)
    raise InspectionError(
        "TIME_NOT_FOUND",
        f"Requested simulation time {time_value} is not available",
        {"requested_time": time_value, "available_times": list(times)},
    )


class CellInspectionService:
    """Read-only inspection service over completed scenario results."""

    def __init__(self, result_store: ScenarioResultStore):
        self._result_store = result_store

    def inspect(
        self,
        city_id: str,
        scenario_id: str,
        latitude: float,
        longitude: float,
        time: Optional[float] = None,
    ) -> CellInspectionResult:
        validate_coordinates(latitude, longitude)

        if not city_id or not scenario_id:
            raise InspectionError(
                "RESULT_NOT_AVAILABLE",
                "city_id and scenario_id are required for inspection",
                {"city_id": city_id, "scenario_id": scenario_id},
            )

        try:
            record = self._result_store.get(city_id, scenario_id)
        except KeyError as exc:
            raise InspectionError(
                "RESULT_NOT_AVAILABLE",
                str(exc),
                {"city_id": city_id, "scenario_id": scenario_id},
            ) from exc

        if not record.times:
            raise InspectionError(
                "RESULT_NOT_AVAILABLE",
                "Scenario result has no stored simulation times",
                {"city_id": city_id, "scenario_id": scenario_id},
            )

        if time is None:
            resolved_time = float(record.times[-1])
        else:
            resolved_time = _lookup_time_key(record.times, time)

        row, column = latlon_to_grid_cell(
            latitude=latitude,
            longitude=longitude,
            grid=record.grid,
            bounds=record.bounds,
        )

        depth_key = _lookup_time_key(tuple(record.depth_by_time.keys()), resolved_time)
        velocity_key = _lookup_time_key(tuple(record.velocity_by_time.keys()), resolved_time)
        depth = float(record.depth_by_time[depth_key][row, column])
        velocity = float(record.velocity_by_time[velocity_key][row, column])
        maximum_depth = float(record.max_depth[row, column])
        threshold = float(record.h_dry_threshold)
        flood_status = "flooded" if depth > threshold else "not_flooded"

        return CellInspectionResult(
            city_id=city_id,
            scenario_id=scenario_id,
            time=resolved_time,
            latitude=latitude,
            longitude=longitude,
            row=row,
            column=column,
            depth=depth,
            velocity=velocity,
            maximum_depth=maximum_depth,
            flood_status=flood_status,
            grid=record.grid,
            bounds=record.bounds,
            crs=record.crs,
            h_dry_threshold=threshold,
        )
