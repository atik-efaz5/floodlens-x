"""API tests for POST /api/scenario/compare."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from floodlens.application.comparison import ScenarioResultRecord
from floodlens.application.geospatial import GeographicBounds, GridReference, ScenarioSession
from floodlens.application.web_server import app, get_result_store, reset_result_store, set_session


@pytest.fixture
def client():
    set_session(ScenarioSession.default_sunamganj())
    reset_result_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_result_store()


def _put_pair(identical: bool = False):
    bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
    grid = GridReference(
        nx=2,
        ny=2,
        dx=240.0,
        dy=240.0,
        origin_x=91.20,
        origin_y=24.80,
        crs="EPSG:4326",
    )
    depth_a = np.array([[0.4, 0.2], [0.3, 0.1]], dtype=np.float64)
    depth_b = depth_a.copy() if identical else np.array([[0.1, 0.1], [0.1, 0.1]], dtype=np.float64)
    store = get_result_store()
    for scenario_id, depth, flooded in (
        ("moderate_rain", depth_a, 2.0),
        ("heavy_rain", depth_b, 4.0 if not identical else 2.0),
    ):
        store.put(
            ScenarioResultRecord(
                scenario_id=scenario_id,
                city_id="sunamganj",
                name=scenario_id,
                grid=grid,
                bounds=bounds,
                crs="EPSG:4326",
                times=(1.0,),
                depth_by_time={1.0: depth},
                velocity_by_time={1.0: depth * 0.5},
                max_depth=depth,
                flooded_area_km2=flooded,
                peak_velocity=float(np.max(depth) * 0.5),
                max_depth_value=float(np.max(depth)),
            )
        )


def test_compare_api_request_response_validation(client):
    _put_pair()
    response = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
            "time": 1.0,
            "comparison_mode": "DIFFERENCE",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city"]["city_id"] == "sunamganj"
    assert data["scenario_a"]["scenario_id"] == "moderate_rain"
    assert data["scenario_b"]["scenario_id"] == "heavy_rain"
    assert data["compatibility"]["compatible"] is True
    comparison = data["comparison"]
    assert comparison["layer"] == "depth"
    assert comparison["time"] == 1.0
    assert "summary_statistics" in comparison
    assert "scenario_summaries" in comparison
    assert comparison["difference_array"][0][0] == pytest.approx(0.3)


def test_compare_api_rejects_incompatible_grids(client):
    bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
    store = get_result_store()
    store.put(
        ScenarioResultRecord(
            scenario_id="moderate_rain",
            city_id="sunamganj",
            name="moderate_rain",
            grid=GridReference(nx=2, ny=2, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80),
            bounds=bounds,
            crs="EPSG:4326",
            times=(1.0,),
            depth_by_time={1.0: np.ones((2, 2))},
            velocity_by_time={1.0: np.zeros((2, 2))},
            max_depth=np.ones((2, 2)),
            flooded_area_km2=1.0,
            peak_velocity=0.0,
            max_depth_value=1.0,
        )
    )
    store.put(
        ScenarioResultRecord(
            scenario_id="heavy_rain",
            city_id="sunamganj",
            name="heavy_rain",
            grid=GridReference(nx=3, ny=2, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80),
            bounds=bounds,
            crs="EPSG:4326",
            times=(1.0,),
            depth_by_time={1.0: np.ones((2, 3))},
            velocity_by_time={1.0: np.zeros((2, 3))},
            max_depth=np.ones((2, 3)),
            flooded_area_km2=1.0,
            peak_velocity=0.0,
            max_depth_value=1.0,
        )
    )
    response = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
        },
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["compatible"] is False
    assert detail["error_code"] == "NX_MISMATCH"


def test_compare_api_missing_result_returns_404(client):
    response = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
        },
    )
    assert response.status_code == 404


def test_compare_api_identical_zero_difference(client):
    _put_pair(identical=True)
    response = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
            "time": 1.0,
        },
    )
    data = response.json()["comparison"]
    assert data["summary_statistics"]["rmse"] == 0.0
    assert data["summary_statistics"]["mean_absolute_difference"] == 0.0


def test_compare_api_invalid_layer_returns_400(client):
    response = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "not_a_layer",
        },
    )
    assert response.status_code == 400


def test_existing_run_endpoint_unchanged(client):
    response = client.post(
        "/api/scenario/run",
        json={"nx": 20, "ny": 20, "rainfall_rate": 1e-4, "duration_seconds": 1.0},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
