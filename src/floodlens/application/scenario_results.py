"""In-memory store for completed, time-aware scenario results.

Time convention
---------------
- Times are finite and non-negative (seconds from simulation start).
- Times are stored in monotonically increasing order.
- Exact lookup uses TIME_MATCH_TOLERANCE = 1e-9 (same policy as comparison).
- Duplicate timestamps are rejected unless replace=True.
- Nearest-time substitution and interpolation are not supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from floodlens.application.comparison import ScenarioResultRecord
from floodlens.application.geospatial import GeographicBounds, GridReference


@dataclass(frozen=True)
class TemporalSnapshot:
    """Read-only hydrodynamic fields at one simulation time."""

    time: float
    depth: np.ndarray
    velocity: np.ndarray


class ScenarioResultStore:
    """Data-driven store of completed results keyed by (city_id, scenario_id)."""

    def __init__(self):
        self._results: Dict[Tuple[str, str], ScenarioResultRecord] = {}

    def put(self, record: ScenarioResultRecord) -> None:
        self._results[(record.city_id, record.scenario_id)] = record

    def get(self, city_id: str, scenario_id: str) -> ScenarioResultRecord:
        key = (city_id, scenario_id)
        if key not in self._results:
            raise KeyError(
                f"No completed result for city={city_id} scenario={scenario_id}"
            )
        return self._results[key]

    def has(self, city_id: str, scenario_id: str) -> bool:
        return (city_id, scenario_id) in self._results

    def clear(self) -> None:
        self._results.clear()

    def remove(self, city_id: str, scenario_id: str) -> None:
        self._results.pop((city_id, scenario_id), None)

    def add_snapshot(
        self,
        city_id: str,
        scenario_id: str,
        time_value: float,
        depth: np.ndarray,
        velocity: np.ndarray,
        *,
        replace: bool = False,
    ) -> None:
        record = self.get(city_id, scenario_id)
        record.add_snapshot(time_value, depth, velocity, replace=replace)

    def available_times(self, city_id: str, scenario_id: str) -> Tuple[float, ...]:
        return self.get(city_id, scenario_id).available_times()

    def has_time(self, city_id: str, scenario_id: str, time_value: float) -> bool:
        return self.get(city_id, scenario_id).has_time(time_value)

    def get_snapshot(self, city_id: str, scenario_id: str, time_value: float) -> dict:
        return self.get(city_id, scenario_id).get_snapshot(time_value)

    def first_snapshot(self, city_id: str, scenario_id: str) -> dict:
        return self.get(city_id, scenario_id).first_snapshot()

    def latest_snapshot(self, city_id: str, scenario_id: str) -> dict:
        return self.get(city_id, scenario_id).latest_snapshot()

    def timeline(self, city_id: str, scenario_id: str) -> dict:
        record = self.get(city_id, scenario_id)
        times = list(record.available_times())
        return {
            "scenario_id": scenario_id,
            "city_id": city_id,
            "available_times": times,
            "start_time": times[0] if times else None,
            "end_time": times[-1] if times else None,
            "timestep_count": len(times),
            "grid": record.grid.to_dict(),
            "crs": record.crs,
        }


def empty_result_record(
    *,
    scenario_id: str,
    city_id: str,
    name: str,
    grid: GridReference,
    bounds: GeographicBounds,
    crs: str,
    h_dry_threshold: float,
) -> ScenarioResultRecord:
    """Create a scenario shell that can receive snapshots."""
    zeros = np.zeros((grid.ny, grid.nx), dtype=np.float64)
    return ScenarioResultRecord(
        scenario_id=scenario_id,
        city_id=city_id,
        name=name,
        grid=grid,
        bounds=bounds,
        crs=crs,
        times=(),
        depth_by_time={},
        velocity_by_time={},
        max_depth=zeros,
        flooded_area_km2=0.0,
        peak_velocity=0.0,
        max_depth_value=0.0,
        h_dry_threshold=h_dry_threshold,
    )


def velocity_from_state(h: np.ndarray, hu: np.ndarray, hv: np.ndarray, h_dry_threshold: float) -> np.ndarray:
    """Application-layer velocity using the existing dry-cell convention."""
    velocity = np.zeros_like(h, dtype=np.float64)
    wet = h > h_dry_threshold
    velocity[wet] = np.sqrt((hu[wet] / h[wet]) ** 2 + (hv[wet] / h[wet]) ** 2)
    return velocity
