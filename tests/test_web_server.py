"""FastAPI web server endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from floodlens.application.geospatial import (
    DEFAULT_VISUALIZATION_LAYERS,
    ScenarioSession,
)
from floodlens.application.web_server import app, set_session


@pytest.fixture
def client():
    set_session(ScenarioSession.default_sunamganj())
    with TestClient(app) as test_client:
        yield test_client


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


def test_cell_inspect_maps_geographic_point_to_matrix_cell(client):
    run_response = client.post(
        "/api/scenario/run",
        json={
            "nx": 30,
            "ny": 30,
            "rainfall_rate": 1.0e-4,
            "duration_seconds": 1.0,
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["success"] is True

    response = client.get(
        "/api/cell/inspect",
        params={"latitude": 24.95, "longitude": 91.35},
    )
    assert response.status_code == 200

    data = response.json()
    assert set(data.keys()) == {
        "latitude",
        "longitude",
        "row",
        "column",
        "depth_m",
        "velocity_m_s",
        "max_depth_m",
        "is_flooded",
        "within_bounds",
    }
    assert data["latitude"] == 24.95
    assert data["longitude"] == 91.35
    assert data["within_bounds"] is True
    assert 0 <= data["row"] < 30
    assert 0 <= data["column"] < 30
    assert data["depth_m"] >= 0.0
    assert data["velocity_m_s"] >= 0.0
    assert data["max_depth_m"] >= 0.0
    assert isinstance(data["is_flooded"], bool)


def test_cell_inspect_requires_prior_simulation(client):
    response = client.get(
        "/api/cell/inspect",
        params={"latitude": 24.95, "longitude": 91.35},
    )
    assert response.status_code == 409
