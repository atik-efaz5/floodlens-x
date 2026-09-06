"""Read-only comparison of completed FloodLens-X simulation results.

This module never invokes the numerical solver. It only validates spatial
compatibility and computes differences of already-produced arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from floodlens.application.geospatial import GeographicBounds, GridReference

SUPPORTED_LAYERS = ("depth", "velocity", "max_depth", "flood_extent")
COMPARISON_MODES = ("SIDE_BY_SIDE", "SWIPE", "DIFFERENCE")
TIME_MATCH_TOLERANCE = 1e-9
DEFAULT_DRY_THRESHOLD = 1e-3


class TemporalResultError(ValueError):
    """Machine-readable temporal store failure."""

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


def validate_simulation_time(time_value: float) -> float:
    """Require a finite, non-negative simulation time."""
    if not np.isfinite(time_value):
        raise TemporalResultError(
            "INVALID_TIME",
            "Simulation time must be a finite number",
            {"time": time_value},
        )
    if time_value < 0.0:
        raise TemporalResultError(
            "INVALID_TIME",
            "Simulation time must be non-negative",
            {"time": time_value},
        )
    return float(time_value)


def lookup_time_key(times, time_value: float) -> Optional[float]:
    """Exact lookup with the documented float tolerance TIME_MATCH_TOLERANCE=1e-9."""
    for existing in times:
        if abs(existing - time_value) <= TIME_MATCH_TOLERANCE:
            return float(existing)
    return None


class ComparisonError(ValueError):
    """Machine-readable comparison failure."""

    def __init__(self, error_code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "compatible": False,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class ComparisonRequest:
    """Request to compare two completed scenarios for one city."""

    city_id: str
    scenario_a_id: str
    scenario_b_id: str
    selected_layer: str = "depth"
    selected_time: Optional[float] = None
    comparison_mode: str = "DIFFERENCE"

    def __post_init__(self):
        if not self.city_id or not self.city_id.strip():
            raise ValueError("city_id must not be empty")
        if not self.scenario_a_id or not self.scenario_a_id.strip():
            raise ValueError("scenario_a_id must not be empty")
        if not self.scenario_b_id or not self.scenario_b_id.strip():
            raise ValueError("scenario_b_id must not be empty")
        if self.selected_layer not in SUPPORTED_LAYERS:
            raise ValueError(
                f"Unsupported layer {self.selected_layer}; expected one of {SUPPORTED_LAYERS}"
            )
        if self.comparison_mode not in COMPARISON_MODES:
            raise ValueError(
                f"Unsupported comparison_mode {self.comparison_mode}; expected one of {COMPARISON_MODES}"
            )


@dataclass
class ScenarioResultRecord:
    """Completed simulation result used as a comparison input."""

    scenario_id: str
    city_id: str
    name: str
    grid: GridReference
    bounds: GeographicBounds
    crs: str
    times: Tuple[float, ...]
    depth_by_time: Dict[float, np.ndarray]
    velocity_by_time: Dict[float, np.ndarray]
    max_depth: np.ndarray
    flooded_area_km2: float
    peak_velocity: float
    max_depth_value: float
    h_dry_threshold: float = DEFAULT_DRY_THRESHOLD

    def available_times(self) -> Tuple[float, ...]:
        return self.times

    def has_time(self, time_value: float) -> bool:
        return lookup_time_key(self.times, time_value) is not None

    def add_snapshot(
        self,
        time_value: float,
        depth: np.ndarray,
        velocity: np.ndarray,
        *,
        replace: bool = False,
    ) -> None:
        """Register a read-only snapshot. Duplicate times are rejected unless replace=True."""
        normalized = validate_simulation_time(time_value)
        depth_copy = np.asarray(depth, dtype=np.float64).copy()
        velocity_copy = np.asarray(velocity, dtype=np.float64).copy()
        expected_shape = (self.grid.ny, self.grid.nx)
        if depth_copy.shape != expected_shape or velocity_copy.shape != expected_shape:
            raise TemporalResultError(
                "METADATA_MISMATCH",
                f"Snapshot shape {depth_copy.shape} does not match grid {expected_shape}",
            )

        existing = lookup_time_key(self.times, normalized)
        if existing is not None:
            if not replace:
                raise TemporalResultError(
                    "DUPLICATE_TIME",
                    f"Snapshot already exists at time {existing}",
                    {"time": existing},
                )
            self.depth_by_time[existing] = depth_copy
            self.velocity_by_time[existing] = velocity_copy
            self._refresh_aggregates()
            return

        if self.times and normalized + TIME_MATCH_TOLERANCE < self.times[-1]:
            raise TemporalResultError(
                "INVALID_TIME",
                f"Snapshot time {normalized} is not monotonically increasing (last={self.times[-1]})",
                {"time": normalized, "last_time": self.times[-1]},
            )

        self.times = tuple(self.times) + (normalized,)
        self.depth_by_time[normalized] = depth_copy
        self.velocity_by_time[normalized] = velocity_copy
        self._refresh_aggregates()

    def get_snapshot(self, time_value: float) -> dict:
        key = lookup_time_key(self.times, time_value)
        if key is None:
            raise TemporalResultError(
                "TIME_NOT_FOUND",
                f"Requested simulation time {time_value} is not available",
                {"requested_time": time_value, "available_times": list(self.times)},
            )
        return {
            "time": key,
            "depth": self.depth_by_time[key],
            "velocity": self.velocity_by_time[key],
            "maximum_depth": self.max_depth,
        }

    def first_snapshot(self) -> dict:
        if not self.times:
            raise TemporalResultError("TIME_NOT_FOUND", "Scenario has no stored snapshots")
        return self.get_snapshot(self.times[0])

    def latest_snapshot(self) -> dict:
        if not self.times:
            raise TemporalResultError("TIME_NOT_FOUND", "Scenario has no stored snapshots")
        return self.get_snapshot(self.times[-1])

    def _refresh_aggregates(self) -> None:
        if not self.depth_by_time:
            return
        stacked = np.stack([self.depth_by_time[t] for t in self.times], axis=0)
        self.max_depth = np.max(stacked, axis=0)
        self.max_depth_value = float(np.max(self.max_depth))
        peak_vel = 0.0
        for t in self.times:
            peak_vel = max(peak_vel, float(np.max(self.velocity_by_time[t])))
        self.peak_velocity = peak_vel


@dataclass(frozen=True)
class DifferenceStatistics:
    """Summary statistics for a continuous difference field A - B."""

    minimum: float
    maximum: float
    mean: float
    mean_absolute: float
    rmse: float
    maximum_absolute: float

    def to_dict(self) -> dict:
        return {
            "minimum_difference": self.minimum,
            "maximum_difference": self.maximum,
            "mean_difference": self.mean,
            "mean_absolute_difference": self.mean_absolute,
            "rmse": self.rmse,
            "maximum_absolute_difference": self.maximum_absolute,
        }


@dataclass(frozen=True)
class ExtentCategories:
    """Categorical flood-extent comparison."""

    flooded_in_both: int
    flooded_only_in_a: int
    flooded_only_in_b: int
    flooded_in_neither: int

    def to_dict(self) -> dict:
        return {
            "flooded_in_both": self.flooded_in_both,
            "flooded_only_in_a": self.flooded_only_in_a,
            "flooded_only_in_b": self.flooded_only_in_b,
            "flooded_in_neither": self.flooded_in_neither,
            "legend": {
                "1": "flooded in both",
                "2": "flooded only in A",
                "3": "flooded only in B",
                "0": "flooded in neither",
            },
        }


@dataclass
class ComparisonResult:
    """Outcome of a successful scenario comparison."""

    city_id: str
    scenario_a_id: str
    scenario_b_id: str
    layer: str
    time: float
    comparison_mode: str
    compatibility: dict
    difference_array: np.ndarray
    statistics: Optional[DifferenceStatistics]
    extent_categories: Optional[ExtentCategories]
    scenario_summaries: dict
    grid: GridReference
    bounds: GeographicBounds

    def to_dict(self, include_array: bool = True) -> dict:
        payload = {
            "city_id": self.city_id,
            "scenario_a_id": self.scenario_a_id,
            "scenario_b_id": self.scenario_b_id,
            "layer": self.layer,
            "time": self.time,
            "comparison_mode": self.comparison_mode,
            "compatibility": self.compatibility,
            "summary_statistics": self.statistics.to_dict() if self.statistics else None,
            "extent_categories": (
                self.extent_categories.to_dict() if self.extent_categories else None
            ),
            "scenario_summaries": self.scenario_summaries,
            "grid": self.grid.to_dict(),
            "bounds": self.bounds.to_dict(),
        }
        if include_array:
            payload["difference_array"] = self.difference_array.tolist()
        return payload


def validate_spatial_compatibility(
    result_a: ScenarioResultRecord, result_b: ScenarioResultRecord, city_id: str
) -> dict:
    """Reject incompatible spatial references instead of resampling."""
    checks = [
        ("CITY_ID_MISMATCH", "city_id", result_a.city_id, result_b.city_id),
        ("CITY_ID_MISMATCH", "request_city_id", result_a.city_id, city_id),
        ("CITY_ID_MISMATCH", "request_city_id_b", result_b.city_id, city_id),
        ("CRS_MISMATCH", "crs", result_a.crs, result_b.crs),
        ("NX_MISMATCH", "nx", result_a.grid.nx, result_b.grid.nx),
        ("NY_MISMATCH", "ny", result_a.grid.ny, result_b.grid.ny),
        ("DX_MISMATCH", "dx", result_a.grid.dx, result_b.grid.dx),
        ("DY_MISMATCH", "dy", result_a.grid.dy, result_b.grid.dy),
        ("ORIGIN_MISMATCH", "origin_x", result_a.grid.origin_x, result_b.grid.origin_x),
        ("ORIGIN_MISMATCH", "origin_y", result_a.grid.origin_y, result_b.grid.origin_y),
        (
            "BOUNDS_MISMATCH",
            "bounds",
            result_a.bounds.to_dict(),
            result_b.bounds.to_dict(),
        ),
        (
            "ROW_ORIENTATION_MISMATCH",
            "row_orientation",
            result_a.grid.row_orientation,
            result_b.grid.row_orientation,
        ),
        (
            "CELL_CENTER_CONVENTION_MISMATCH",
            "cell_center_convention",
            result_a.grid.cell_center_convention,
            result_b.grid.cell_center_convention,
        ),
    ]

    for code, field, left, right in checks:
        if left != right:
            raise ComparisonError(
                code,
                f"Spatial incompatibility on {field}: {left} != {right}",
                {"field": field, "scenario_a": left, "scenario_b": right},
            )

    expected_shape = (result_a.grid.ny, result_a.grid.nx)
    for label, array in (
        ("a.max_depth", result_a.max_depth),
        ("b.max_depth", result_b.max_depth),
    ):
        if array.shape != expected_shape:
            raise ComparisonError(
                "ARRAY_SHAPE_MISMATCH",
                f"{label} shape {array.shape} != {expected_shape}",
                {"field": label, "shape": list(array.shape), "expected": list(expected_shape)},
            )

    return {
        "compatible": True,
        "city_id": city_id,
        "crs": result_a.crs,
        "nx": result_a.grid.nx,
        "ny": result_a.grid.ny,
        "dx": result_a.grid.dx,
        "dy": result_a.grid.dy,
        "origin_x": result_a.grid.origin_x,
        "origin_y": result_a.grid.origin_y,
        "bounds": result_a.bounds.to_dict(),
        "cell_center_convention": result_a.grid.cell_center_convention,
        "row_orientation": result_a.grid.row_orientation,
    }


def resolve_comparison_time(
    result_a: ScenarioResultRecord,
    result_b: ScenarioResultRecord,
    requested_time: Optional[float],
) -> float:
    """Require an identical timestamp; never interpolate."""

    def has_time(record: ScenarioResultRecord, time_value: float) -> bool:
        return any(abs(existing - time_value) <= TIME_MATCH_TOLERANCE for existing in record.times)

    if requested_time is not None:
        if not has_time(result_a, requested_time) or not has_time(result_b, requested_time):
            raise ComparisonError(
                "TIME_NOT_FOUND",
                f"Requested time {requested_time} is not present in both scenarios",
                {
                    "requested_time": requested_time,
                    "scenario_a_times": list(result_a.times),
                    "scenario_b_times": list(result_b.times),
                },
            )
        return float(requested_time)

    shared = [
        float(time_a)
        for time_a in result_a.times
        if has_time(result_b, time_a)
    ]
    if not shared:
        raise ComparisonError(
            "TIME_NOT_FOUND",
            "Scenarios have no identical timestamps to compare",
            {
                "scenario_a_times": list(result_a.times),
                "scenario_b_times": list(result_b.times),
            },
        )
    return shared[-1]


def _lookup_time_key(store: Dict[float, np.ndarray], time_value: float) -> float:
    key = lookup_time_key(store.keys(), time_value)
    if key is None:
        raise ComparisonError(
            "TIME_NOT_FOUND",
            f"Layer has no field at time {time_value}",
            {"requested_time": time_value, "available_times": list(store.keys())},
        )
    return key


def select_layer_array(
    record: ScenarioResultRecord, layer: str, time_value: float
) -> np.ndarray:
    if layer == "max_depth":
        return record.max_depth
    if layer == "depth":
        key = _lookup_time_key(record.depth_by_time, time_value)
        return record.depth_by_time[key]
    if layer == "velocity":
        key = _lookup_time_key(record.velocity_by_time, time_value)
        return record.velocity_by_time[key]
    if layer == "flood_extent":
        key = _lookup_time_key(record.depth_by_time, time_value)
        return record.depth_by_time[key] > record.h_dry_threshold
    raise ComparisonError("UNSUPPORTED_LAYER", f"Unsupported layer {layer}")


def compute_difference_statistics(delta: np.ndarray) -> DifferenceStatistics:
    abs_delta = np.abs(delta)
    return DifferenceStatistics(
        minimum=float(np.min(delta)),
        maximum=float(np.max(delta)),
        mean=float(np.mean(delta)),
        mean_absolute=float(np.mean(abs_delta)),
        rmse=float(np.sqrt(np.mean(delta * delta))),
        maximum_absolute=float(np.max(abs_delta)),
    )


def compare_extent(mask_a: np.ndarray, mask_b: np.ndarray) -> Tuple[np.ndarray, ExtentCategories]:
    """Encode extent comparison as categories: 0 neither, 1 both, 2 only A, 3 only B."""
    both = mask_a & mask_b
    only_a = mask_a & ~mask_b
    only_b = mask_b & ~mask_a
    neither = ~mask_a & ~mask_b
    encoded = np.zeros(mask_a.shape, dtype=np.int8)
    encoded[both] = 1
    encoded[only_a] = 2
    encoded[only_b] = 3
    categories = ExtentCategories(
        flooded_in_both=int(np.count_nonzero(both)),
        flooded_only_in_a=int(np.count_nonzero(only_a)),
        flooded_only_in_b=int(np.count_nonzero(only_b)),
        flooded_in_neither=int(np.count_nonzero(neither)),
    )
    return encoded, categories


def _scenario_summaries(
    result_a: ScenarioResultRecord, result_b: ScenarioResultRecord
) -> dict:
    return {
        "flooded_area_a_km2": result_a.flooded_area_km2,
        "flooded_area_b_km2": result_b.flooded_area_km2,
        "flooded_area_difference_km2": result_a.flooded_area_km2 - result_b.flooded_area_km2,
        "maximum_depth_a_m": result_a.max_depth_value,
        "maximum_depth_b_m": result_b.max_depth_value,
        "maximum_depth_difference_m": result_a.max_depth_value - result_b.max_depth_value,
        "peak_velocity_a_m_s": result_a.peak_velocity,
        "peak_velocity_b_m_s": result_b.peak_velocity,
        "peak_velocity_difference_m_s": result_a.peak_velocity - result_b.peak_velocity,
    }


class ComparisonEngine:
    """Read-only comparison engine for completed scenario results."""

    def compare(
        self,
        request: ComparisonRequest,
        result_a: ScenarioResultRecord,
        result_b: ScenarioResultRecord,
    ) -> ComparisonResult:
        compatibility = validate_spatial_compatibility(result_a, result_b, request.city_id)
        time_value = resolve_comparison_time(result_a, result_b, request.selected_time)

        array_a = select_layer_array(result_a, request.selected_layer, time_value)
        array_b = select_layer_array(result_b, request.selected_layer, time_value)

        statistics = None
        extent_categories = None
        if request.selected_layer == "flood_extent":
            difference_array, extent_categories = compare_extent(
                np.asarray(array_a, dtype=bool), np.asarray(array_b, dtype=bool)
            )
        else:
            difference_array = np.asarray(array_a, dtype=np.float64) - np.asarray(
                array_b, dtype=np.float64
            )
            statistics = compute_difference_statistics(difference_array)

        return ComparisonResult(
            city_id=request.city_id,
            scenario_a_id=request.scenario_a_id,
            scenario_b_id=request.scenario_b_id,
            layer=request.selected_layer,
            time=time_value,
            comparison_mode=request.comparison_mode,
            compatibility=compatibility,
            difference_array=difference_array,
            statistics=statistics,
            extent_categories=extent_categories,
            scenario_summaries=_scenario_summaries(result_a, result_b),
            grid=result_a.grid,
            bounds=result_a.bounds,
        )
