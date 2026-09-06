"""Tests for read-only scenario comparison."""

import numpy as np
import pytest

from floodlens.application.city_data import create_city_registry
from floodlens.application.comparison import (
    COMPARISON_MODES,
    ComparisonEngine,
    ComparisonError,
    ComparisonRequest,
    ScenarioResultRecord,
    compute_difference_statistics,
    compare_extent,
    resolve_comparison_time,
    validate_spatial_compatibility,
)
from floodlens.application.geospatial import GeographicBounds, GridReference
from floodlens.application.scenario_results import ScenarioResultStore


def _grid(**overrides) -> GridReference:
    values = dict(
        nx=4,
        ny=3,
        dx=10.0,
        dy=10.0,
        origin_x=91.20,
        origin_y=24.80,
        crs="EPSG:4326",
        cell_center_convention="cell_center",
        row_orientation="south_to_north",
    )
    values.update(overrides)
    return GridReference(**values)


def _bounds(**overrides) -> GeographicBounds:
    values = dict(west=91.20, south=24.80, east=91.50, north=25.10)
    values.update(overrides)
    return GeographicBounds(**values)


def make_record(
    scenario_id: str,
    city_id: str = "sunamganj",
    depth=None,
    velocity=None,
    max_depth=None,
    time: float = 1.0,
    flooded_area_km2: float = 1.0,
    peak_velocity: float = 0.2,
    max_depth_value: float | None = None,
    grid: GridReference | None = None,
    bounds: GeographicBounds | None = None,
    crs: str = "EPSG:4326",
) -> ScenarioResultRecord:
    depth_arr = np.asarray(depth if depth is not None else [[0.1, 0.2, 0.3, 0.4], [0.2, 0.3, 0.4, 0.5], [0.3, 0.4, 0.5, 0.6]], dtype=np.float64)
    velocity_arr = np.asarray(
        velocity if velocity is not None else np.full_like(depth_arr, 0.1),
        dtype=np.float64,
    )
    max_arr = np.asarray(max_depth if max_depth is not None else depth_arr, dtype=np.float64)
    return ScenarioResultRecord(
        scenario_id=scenario_id,
        city_id=city_id,
        name=scenario_id,
        grid=grid or _grid(nx=depth_arr.shape[1], ny=depth_arr.shape[0]),
        bounds=bounds or _bounds(),
        crs=crs,
        times=(time,),
        depth_by_time={time: depth_arr},
        velocity_by_time={time: velocity_arr},
        max_depth=max_arr,
        flooded_area_km2=flooded_area_km2,
        peak_velocity=peak_velocity,
        max_depth_value=float(np.max(max_arr) if max_depth_value is None else max_depth_value),
    )


@pytest.fixture
def engine():
    return ComparisonEngine()


class TestValidComparison:
    def test_identical_scenarios_have_exact_zero_differences(self, engine):
        depth = np.array([[0.2, 0.4], [0.6, 0.8]], dtype=np.float64)
        record_a = make_record("a", depth=depth, velocity=depth * 0, flooded_area_km2=2.5, peak_velocity=0.4)
        record_b = make_record("b", depth=depth.copy(), velocity=depth * 0, flooded_area_km2=2.5, peak_velocity=0.4)
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="depth", selected_time=1.0),
            record_a,
            record_b,
        )
        assert np.all(result.difference_array == 0.0)
        assert result.statistics.minimum == 0.0
        assert result.statistics.maximum == 0.0
        assert result.statistics.mean == 0.0
        assert result.statistics.mean_absolute == 0.0
        assert result.statistics.rmse == 0.0
        assert result.statistics.maximum_absolute == 0.0


class TestSpatialCompatibility:
    def test_different_city_rejection(self, engine):
        a = make_record("a", city_id="dhaka")
        b = make_record("b", city_id="sunamganj")
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("dhaka", "a", "b"), a, b)
        assert exc.value.error_code == "CITY_ID_MISMATCH"

    def test_different_crs_rejection(self, engine):
        a = make_record("a", crs="EPSG:4326")
        b = make_record("b", crs="EPSG:3857")
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "CRS_MISMATCH"

    def test_different_nx_ny_rejection(self, engine):
        a = make_record("a", depth=np.ones((3, 4)))
        b = make_record("b", depth=np.ones((3, 5)))
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "NX_MISMATCH"

    def test_different_dx_dy_rejection(self, engine):
        a = make_record("a", grid=_grid(dx=10.0, dy=10.0))
        b = make_record("b", grid=_grid(dx=20.0, dy=10.0))
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "DX_MISMATCH"

    def test_different_origin_rejection(self, engine):
        a = make_record("a", grid=_grid(origin_x=91.20))
        b = make_record("b", grid=_grid(origin_x=91.21))
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "ORIGIN_MISMATCH"

    def test_different_bounds_rejection(self, engine):
        a = make_record("a", bounds=_bounds(east=91.50))
        b = make_record("b", bounds=_bounds(east=91.60))
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "BOUNDS_MISMATCH"

    def test_different_cell_center_convention_rejection(self, engine):
        a = make_record("a", grid=_grid(cell_center_convention="cell_center"))
        b = make_record("b", grid=_grid(cell_center_convention="cell_corner"))
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("sunamganj", "a", "b"), a, b)
        assert exc.value.error_code == "CELL_CENTER_CONVENTION_MISMATCH"

    def test_compatibility_payload_is_machine_readable(self):
        a = make_record("a")
        b = make_record("b", crs="EPSG:3857")
        with pytest.raises(ComparisonError) as exc:
            validate_spatial_compatibility(a, b, "sunamganj")
        payload = exc.value.to_dict()
        assert payload["compatible"] is False
        assert payload["error_code"] == "CRS_MISMATCH"
        assert "details" in payload


class TestTemporalCompatibility:
    def test_missing_time_rejection(self, engine):
        a = make_record("a", time=1.0)
        b = make_record("b", time=1.0)
        with pytest.raises(ComparisonError) as exc:
            engine.compare(
                ComparisonRequest("sunamganj", "a", "b", selected_time=9.0),
                a,
                b,
            )
        assert exc.value.error_code == "TIME_NOT_FOUND"

    def test_identical_timestep_comparison(self, engine):
        a = make_record("a", time=2.5, depth=np.ones((3, 4)))
        b = make_record("b", time=2.5, depth=np.zeros((3, 4)))
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="depth", selected_time=2.5),
            a,
            b,
        )
        assert result.time == 2.5
        assert np.allclose(result.difference_array, 1.0)

    def test_unspecified_time_uses_last_shared_timestamp(self):
        a = make_record("a", time=1.0)
        b = make_record("b", time=1.0)
        assert resolve_comparison_time(a, b, None) == 1.0


class TestLayerComparisons:
    def test_depth_difference_calculation(self, engine):
        a = make_record("a", depth=np.array([[2.0, 3.0], [4.0, 5.0]]))
        b = make_record("b", depth=np.array([[1.0, 1.0], [1.0, 1.0]]))
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="depth", selected_time=1.0),
            a,
            b,
        )
        expected = np.array([[1.0, 2.0], [3.0, 4.0]])
        np.testing.assert_array_equal(result.difference_array, expected)

    def test_velocity_difference_calculation(self, engine):
        field_a = np.array([[0.5, 0.4], [0.3, 0.2]])
        field_b = np.array([[0.1, 0.1], [0.1, 0.1]])
        a = make_record("a", depth=np.ones((2, 2)), velocity=field_a)
        b = make_record("b", depth=np.ones((2, 2)), velocity=field_b)
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="velocity", selected_time=1.0),
            a,
            b,
        )
        np.testing.assert_allclose(result.difference_array, [[0.4, 0.3], [0.2, 0.1]])

    def test_maximum_depth_comparison(self, engine):
        max_a = np.array([[1.0, 2.0], [3.0, 4.0]])
        max_b = np.array([[0.5, 0.5], [0.5, 0.5]])
        a = make_record("a", depth=max_a, max_depth=max_a)
        b = make_record("b", depth=max_b, max_depth=max_b)
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="max_depth", selected_time=1.0),
            a,
            b,
        )
        np.testing.assert_allclose(result.difference_array, [[0.5, 1.5], [2.5, 3.5]])

    def test_flood_extent_categorical_comparison(self, engine):
        a = make_record("a", depth=np.array([[0.01, 0.0], [0.01, 0.0]]))
        b = make_record("b", depth=np.array([[0.01, 0.01], [0.0, 0.0]]))
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="flood_extent", selected_time=1.0),
            a,
            b,
        )
        # 1 both, 2 only A, 3 only B, 0 neither
        np.testing.assert_array_equal(result.difference_array, [[1, 3], [2, 0]])
        assert result.extent_categories.flooded_in_both == 1
        assert result.extent_categories.flooded_only_in_a == 1
        assert result.extent_categories.flooded_only_in_b == 1
        assert result.extent_categories.flooded_in_neither == 1


class TestStatistics:
    def test_rmse_and_mean_absolute_difference(self):
        delta = np.array([[1.0, -1.0], [3.0, -3.0]], dtype=np.float64)
        stats = compute_difference_statistics(delta)
        assert stats.mean_absolute == 2.0
        assert stats.rmse == pytest.approx(np.sqrt(5.0))
        assert stats.minimum == -3.0
        assert stats.maximum == 3.0
        assert stats.maximum_absolute == 3.0
        assert stats.mean == 0.0

    def test_scenario_level_aggregate_metrics(self, engine):
        a = make_record("a", flooded_area_km2=4.0, peak_velocity=1.5, max_depth_value=2.0, depth=np.ones((2, 2)))
        b = make_record("b", flooded_area_km2=1.0, peak_velocity=0.5, max_depth_value=0.5, depth=np.zeros((2, 2)))
        result = engine.compare(
            ComparisonRequest("sunamganj", "a", "b", selected_layer="depth", selected_time=1.0),
            a,
            b,
        )
        summaries = result.scenario_summaries
        assert summaries["flooded_area_a_km2"] == 4.0
        assert summaries["flooded_area_b_km2"] == 1.0
        assert summaries["flooded_area_difference_km2"] == 3.0
        assert summaries["maximum_depth_difference_m"] == 1.5
        assert summaries["peak_velocity_difference_m_s"] == 1.0


class TestExtentHelper:
    def test_compare_extent_counts(self):
        mask_a = np.array([[True, False], [True, False]])
        mask_b = np.array([[True, True], [False, False]])
        encoded, categories = compare_extent(mask_a, mask_b)
        assert categories.flooded_in_both == 1
        assert encoded[0, 0] == 1


class TestFrontendSelectionContract:
    def test_frontend_scenario_selection_requires_same_city(self, engine):
        a = make_record("moderate_rain", city_id="dhaka")
        b = make_record("heavy_rain", city_id="sylhet")
        with pytest.raises(ComparisonError) as exc:
            engine.compare(ComparisonRequest("dhaka", "moderate_rain", "heavy_rain"), a, b)
        assert exc.value.error_code == "CITY_ID_MISMATCH"

    def test_synchronized_map_state_uses_identical_bounds(self, engine):
        a = make_record("moderate_rain")
        b = make_record("heavy_rain", depth=np.zeros((3, 4)))
        result = engine.compare(
            ComparisonRequest("sunamganj", "moderate_rain", "heavy_rain", comparison_mode="SIDE_BY_SIDE"),
            a,
            b,
        )
        assert result.bounds == a.bounds
        assert result.compatibility["bounds"] == a.bounds.to_dict()
        assert result.comparison_mode == "SIDE_BY_SIDE"
        assert "SWIPE" in COMPARISON_MODES
        assert "DIFFERENCE" in COMPARISON_MODES


class TestResultStore:
    def test_store_round_trip(self):
        store = ScenarioResultStore()
        record = make_record("moderate_rain")
        store.put(record)
        assert store.has("sunamganj", "moderate_rain")
        assert store.get("sunamganj", "moderate_rain") is record

    def test_missing_result_raises(self):
        store = ScenarioResultStore()
        with pytest.raises(KeyError):
            store.get("sunamganj", "missing")


class TestCityRegistryScenarios:
    def test_modeled_scenarios_registered_for_each_city(self):
        registry = create_city_registry()
        for city_id in ("sunamganj", "dhaka", "sylhet"):
            ids = [s.scenario_id for s in registry.get_scenarios_for_city(city_id)]
            assert "moderate_rain" in ids
            assert "heavy_rain" in ids
            for scenario in registry.get_scenarios_for_city(city_id):
                assert scenario.modeled_status is True
                assert scenario.simulated_status is False
