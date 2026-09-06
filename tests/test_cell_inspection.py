"""Tests for read-only cell inspection and coordinate mapping."""

import copy

import numpy as np
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from floodlens.application.cell_inspection import (
    CellInspectionService,
    InspectionError,
    latlon_to_grid_cell,
    validate_coordinates,
)
from floodlens.application.comparison import ScenarioResultRecord
from floodlens.application.geospatial import GeographicBounds, GridReference, ScenarioSession
from floodlens.application.scenario_results import ScenarioResultStore
from floodlens.application.web_server import (
    app,
    get_result_store,
    reset_result_store,
    set_session,
)


@pytest.fixture
def bounds():
    return GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)


@pytest.fixture
def grid():
    return GridReference(
        nx=4,
        ny=4,
        dx=240.0,
        dy=240.0,
        origin_x=91.20,
        origin_y=24.80,
        crs="EPSG:4326",
    )


@pytest.fixture
def record(bounds, grid):
    depth = np.array(
        [
            [0.1, 0.2, 0.3, 0.4],
            [0.2, 0.3, 0.4, 0.5],
            [0.3, 0.4, 0.5, 0.6],
            [0.4, 0.5, 0.6, 0.7],
        ],
        dtype=np.float64,
    )
    velocity = depth * 0.5
    return ScenarioResultRecord(
        scenario_id="moderate_rain",
        city_id="sunamganj",
        name="Moderate Rain",
        grid=grid,
        bounds=bounds,
        crs="EPSG:4326",
        times=(1.0, 2.0),
        depth_by_time={1.0: depth, 2.0: depth + 0.1},
        velocity_by_time={1.0: velocity, 2.0: velocity + 0.05},
        max_depth=depth + 0.2,
        flooded_area_km2=1.0,
        peak_velocity=float(np.max(velocity)),
        max_depth_value=float(np.max(depth + 0.2)),
        h_dry_threshold=1e-3,
    )


@pytest.fixture
def service(record):
    store = ScenarioResultStore()
    store.put(record)
    return CellInspectionService(store)


def test_known_coordinate_maps_to_expected_row_column(bounds, grid):
    row, col = latlon_to_grid_cell(24.815, 91.21, grid, bounds)
    assert row == 0
    assert col == 0


def test_known_grid_center_returns_exact_cell(service, bounds, grid):
    dx_geo = (bounds.east - bounds.west) / grid.nx
    dy_geo = (bounds.north - bounds.south) / grid.ny
    lat = bounds.south + (2 + 0.5) * dy_geo
    lon = bounds.west + (1 + 0.5) * dx_geo
    result = service.inspect("sunamganj", "moderate_rain", lat, lon, time=1.0)
    assert result.row == 2
    assert result.column == 1
    assert result.depth == pytest.approx(0.4)


def test_corner_boundary_coordinate_maps_to_last_cell(bounds, grid):
    row, col = latlon_to_grid_cell(bounds.north, bounds.east, grid, bounds)
    assert row == grid.ny - 1
    assert col == grid.nx - 1


def test_just_inside_domain_coordinate(service, bounds, grid):
    dx_geo = (bounds.east - bounds.west) / grid.nx
    dy_geo = (bounds.north - bounds.south) / grid.ny
    lat = bounds.south + dy_geo * 0.5
    lon = bounds.west + dx_geo * 0.5
    result = service.inspect("sunamganj", "moderate_rain", lat, lon, time=1.0)
    assert result.row == 0
    assert result.column == 0


def test_just_outside_domain_longitude(bounds, grid):
    with pytest.raises(InspectionError) as exc:
        latlon_to_grid_cell(24.95, bounds.east + 1e-6, grid, bounds)
    assert exc.value.error_code == "OUTSIDE_SIMULATION_DOMAIN"


def test_invalid_latitude():
    with pytest.raises(InspectionError) as exc:
        validate_coordinates(95.0, 90.0)
    assert exc.value.error_code == "INVALID_COORDINATES"


def test_invalid_longitude():
    with pytest.raises(InspectionError) as exc:
        validate_coordinates(24.0, 200.0)
    assert exc.value.error_code == "INVALID_COORDINATES"


def test_non_finite_coordinate():
    with pytest.raises(InspectionError) as exc:
        validate_coordinates(float("nan"), 90.0)
    assert exc.value.error_code == "INVALID_COORDINATES"


def test_result_not_available(service):
    with pytest.raises(InspectionError) as exc:
        service.inspect("sunamganj", "missing", 24.95, 91.35, time=1.0)
    assert exc.value.error_code == "RESULT_NOT_AVAILABLE"


def test_missing_time(service):
    with pytest.raises(InspectionError) as exc:
        service.inspect("sunamganj", "moderate_rain", 24.95, 91.35, time=9.9)
    assert exc.value.error_code == "TIME_NOT_FOUND"


def test_depth_velocity_max_depth_and_flood_status(service, bounds, grid):
    dx_geo = (bounds.east - bounds.west) / grid.nx
    dy_geo = (bounds.north - bounds.south) / grid.ny
    lat = bounds.south + (3 + 0.5) * dy_geo
    lon = bounds.west + (3 + 0.5) * dx_geo
    result = service.inspect("sunamganj", "moderate_rain", lat, lon, time=1.0)
    assert result.depth == pytest.approx(0.7)
    assert result.velocity == pytest.approx(0.35)
    assert result.maximum_depth == pytest.approx(0.9)
    assert result.flood_status == "flooded"


def test_active_city_scenario_time_selection(service):
    result = service.inspect("sunamganj", "moderate_rain", 24.95, 91.35, time=2.0)
    assert result.city_id == "sunamganj"
    assert result.scenario_id == "moderate_rain"
    assert result.time == 2.0


def test_inspection_does_not_mutate_stored_results(service, record):
    before = copy.deepcopy(record.depth_by_time[1.0])
    service.inspect("sunamganj", "moderate_rain", 24.95, 91.35, time=1.0)
    after = record.depth_by_time[1.0]
    np.testing.assert_array_equal(before, after)


@pytest.fixture
def api_client(record):
    set_session(ScenarioSession.default_sunamganj())
    reset_result_store()
    get_result_store().put(record)
    with TestClient(app) as client:
        yield client
    reset_result_store()


def test_api_inspection_contract(api_client):
    response = api_client.get(
        "/api/cell/inspect",
        params={
            "lat": 24.95,
            "lon": 91.35,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
            "time": 1.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city_id"] == "sunamganj"
    assert data["scenario_id"] == "moderate_rain"
    assert data["time"] == 1.0
    assert data["modeled"] is True
    assert "grid" in data
    assert data["flood_status"] in {"flooded", "not_flooded"}


def test_api_dhaka_interior_inspect_succeeds_sunamganj_point_rejected():
    dhaka_bounds = GeographicBounds(west=90.0, south=23.5, east=90.8, north=24.1)
    dhaka_grid = GridReference(
        nx=4,
        ny=4,
        dx=160.0,
        dy=160.0,
        origin_x=90.0,
        origin_y=23.5,
        crs="EPSG:4326",
    )
    depth = np.array(
        [
            [0.1, 0.2, 0.3, 0.4],
            [0.2, 0.3, 0.4, 0.5],
            [0.3, 0.4, 0.5, 0.6],
            [0.4, 0.5, 0.6, 0.7],
        ],
        dtype=np.float64,
    )
    velocity = depth * 0.5
    dhaka_record = ScenarioResultRecord(
        scenario_id="moderate_rain",
        city_id="dhaka",
        name="Moderate Rain",
        grid=dhaka_grid,
        bounds=dhaka_bounds,
        crs="EPSG:4326",
        times=(1.0, 5.0),
        depth_by_time={1.0: depth, 5.0: depth + 0.1},
        velocity_by_time={1.0: velocity, 5.0: velocity + 0.05},
        max_depth=depth + 0.2,
        flooded_area_km2=1.0,
        peak_velocity=float(np.max(velocity)),
        max_depth_value=float(np.max(depth + 0.2)),
        h_dry_threshold=1e-3,
    )
    set_session(ScenarioSession.default_sunamganj())
    reset_result_store()
    get_result_store().put(dhaka_record)
    try:
        with TestClient(app) as client:
            interior = client.get(
                "/api/cell/inspect",
                params={
                    "lat": 23.81,
                    "lon": 90.41,
                    "city_id": "dhaka",
                    "scenario_id": "moderate_rain",
                    "time": 5.0,
                },
            )
            assert interior.status_code == 200
            assert interior.json()["city_id"] == "dhaka"

            outside = client.get(
                "/api/cell/inspect",
                params={
                    "lat": 24.8075,
                    "lon": 91.2075,
                    "city_id": "dhaka",
                    "scenario_id": "moderate_rain",
                    "time": 5.0,
                },
            )
            assert outside.status_code == 422
            assert outside.json()["detail"]["error_code"] == "OUTSIDE_SIMULATION_DOMAIN"
    finally:
        reset_result_store()


def test_api_inspection_does_not_invoke_solver(api_client):
    with patch("floodlens.numerical.timestepper.run_shallow_water_simulation") as mock_run:
        response = api_client.get(
            "/api/cell/inspect",
            params={
                "lat": 24.95,
                "lon": 91.35,
                "city_id": "sunamganj",
                "scenario_id": "moderate_rain",
                "time": 1.0,
            },
        )
    assert response.status_code == 200
    mock_run.assert_not_called()
