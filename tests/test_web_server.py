"""FastAPI web server endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from floodlens.application.geospatial import (
    DEFAULT_VISUALIZATION_LAYERS,
    ScenarioSession,
)
from floodlens.application.web_server import app, get_result_store, reset_result_store, set_session


@pytest.fixture
def client():
    set_session(ScenarioSession.default_sunamganj())
    reset_result_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_result_store()


def test_metadata_returns_geospatial_contract(client):
    response = client.get("/api/scenario/metadata")
    assert response.status_code == 200

    data = response.json()
    assert set(data.keys()) == {
        "bounds",
        "center",
        "crs",
        "time_range",
        "visualization_layers",
    }

    bounds = data["bounds"]
    assert {"west", "south", "east", "north"} <= set(bounds.keys())
    assert bounds["west"] < bounds["east"]
    assert bounds["south"] < bounds["north"]

    center = data["center"]
    assert {"latitude", "longitude", "label"} <= set(center.keys())
    assert center["label"] == "Sunamganj"

    assert data["crs"] == "EPSG:4326"
    assert data["time_range"]["start_seconds"] == 0.0
    assert data["time_range"]["end_seconds"] >= 0.0
    assert set(data["visualization_layers"]) == set(DEFAULT_VISUALIZATION_LAYERS)


def test_scenario_run_returns_inundation_metrics(client):
    response = client.post(
        "/api/scenario/run",
        json={
            "nx": 20,
            "ny": 20,
            "rainfall_rate": 1.0e-4,
            "duration_seconds": 1.0,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["nx"] == 20
    assert data["ny"] == 20
    assert data["max_depth_m"] >= 0.0
    assert data["flooded_area_km2"] >= 0.0
    assert data["simulation_time_s"] > 0.0


def test_scenario_run_accepts_unequal_nx_ny(client):
    response = client.post(
        "/api/scenario/run",
        json={
            "nx": 12,
            "ny": 8,
            "rainfall_rate": 1.0e-4,
            "duration_seconds": 0.5,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["nx"] == 12
    assert data["ny"] == 8


def test_cell_inspect_maps_geographic_point_to_matrix_cell(client):
    run_response = client.post(
        "/api/scenario/run",
        json={
            "nx": 30,
            "ny": 30,
            "rainfall_rate": 1.0e-4,
            "duration_seconds": 1.0,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    assert run_response.status_code == 200
    run_data = run_response.json()
    assert run_data["success"] is True

    response = client.get(
        "/api/cell/inspect",
        params={
            "lat": 24.95,
            "lon": 91.35,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
            "time": run_data["simulation_time_s"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["city_id"] == "sunamganj"
    assert data["scenario_id"] == "moderate_rain"
    assert data["modeled"] is True
    assert data["latitude"] == 24.95
    assert data["longitude"] == 91.35
    assert data["within_bounds"] is True
    assert 0 <= data["row"] < 30
    assert 0 <= data["column"] < 30
    assert data["depth"] >= 0.0
    assert data["velocity"] >= 0.0
    assert data["maximum_depth"] >= 0.0
    assert data["flood_status"] in {"flooded", "not_flooded"}


def test_cell_inspect_requires_stored_result(client):
    response = client.get(
        "/api/cell/inspect",
        params={
            "lat": 24.95,
            "lon": 91.35,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "RESULT_NOT_AVAILABLE"
