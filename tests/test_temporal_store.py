"""Tests for the temporal result store and timeline APIs."""

import copy

import numpy as np
import pytest
from fastapi.testclient import TestClient

from floodlens.application.comparison import TemporalResultError
from floodlens.application.geospatial import GeographicBounds, GridReference, ScenarioSession
from floodlens.application.scenario_results import (
    ScenarioResultStore,
    empty_result_record,
)
from floodlens.application.service import SimulationService
from floodlens.application.web_server import app, get_result_store, reset_result_store, set_session
from floodlens.core.config import SimulationConfig


def _grid():
    return GridReference(nx=2, ny=2, dx=1.0, dy=1.0, origin_x=91.2, origin_y=24.8)


def _bounds():
    return GeographicBounds(west=91.2, south=24.8, east=91.5, north=25.1)


def _empty_record(city_id="sunamganj", scenario_id="moderate_rain"):
    return empty_result_record(
        scenario_id=scenario_id,
        city_id=city_id,
        name=scenario_id,
        grid=_grid(),
        bounds=_bounds(),
        crs="EPSG:4326",
        h_dry_threshold=1e-3,
    )


def test_temporal_result_creation_and_snapshot_insertion():
    record = _empty_record()
    record.add_snapshot(0.0, np.zeros((2, 2)), np.zeros((2, 2)))
    record.add_snapshot(0.1, np.ones((2, 2)) * 0.2, np.ones((2, 2)) * 0.1)
    assert record.available_times() == (0.0, 0.1)
    assert record.has_time(0.1)


def test_monotonically_increasing_times():
    record = _empty_record()
    record.add_snapshot(1.0, np.zeros((2, 2)), np.zeros((2, 2)))
    with pytest.raises(TemporalResultError) as exc:
        record.add_snapshot(0.5, np.ones((2, 2)), np.zeros((2, 2)))
    assert exc.value.error_code == "INVALID_TIME"


def test_duplicate_time_rejected_unless_replaced():
    record = _empty_record()
    record.add_snapshot(0.0, np.zeros((2, 2)), np.zeros((2, 2)))
    with pytest.raises(TemporalResultError) as exc:
        record.add_snapshot(0.0, np.ones((2, 2)), np.zeros((2, 2)))
    assert exc.value.error_code == "DUPLICATE_TIME"
    record.add_snapshot(0.0, np.ones((2, 2)), np.zeros((2, 2)), replace=True)
    np.testing.assert_array_equal(record.get_snapshot(0.0)["depth"], np.ones((2, 2)))


def test_invalid_time_rejection():
    record = _empty_record()
    with pytest.raises(TemporalResultError) as exc:
        record.add_snapshot(float("nan"), np.zeros((2, 2)), np.zeros((2, 2)))
    assert exc.value.error_code == "INVALID_TIME"
    with pytest.raises(TemporalResultError) as exc:
        record.add_snapshot(-1.0, np.zeros((2, 2)), np.zeros((2, 2)))
    assert exc.value.error_code == "INVALID_TIME"


def test_exact_time_lookup_and_missing_time():
    record = _empty_record()
    record.add_snapshot(0.0, np.zeros((2, 2)), np.zeros((2, 2)))
    record.add_snapshot(1.0, np.ones((2, 2)), np.zeros((2, 2)))
    snap = record.get_snapshot(1.0)
    assert snap["time"] == 1.0
    with pytest.raises(TemporalResultError) as exc:
        record.get_snapshot(0.5)
    assert exc.value.error_code == "TIME_NOT_FOUND"


def test_available_times_and_first_latest():
    record = _empty_record()
    record.add_snapshot(0.0, np.zeros((2, 2)), np.zeros((2, 2)))
    record.add_snapshot(2.0, np.ones((2, 2)), np.zeros((2, 2)))
    assert record.available_times() == (0.0, 2.0)
    assert record.first_snapshot()["time"] == 0.0
    assert record.latest_snapshot()["time"] == 2.0


def test_store_temporal_retrieval_and_isolation():
    store = ScenarioResultStore()
    store.put(_empty_record("sunamganj", "moderate_rain"))
    store.put(_empty_record("dhaka", "moderate_rain"))
    store.add_snapshot("sunamganj", "moderate_rain", 0.0, np.zeros((2, 2)), np.zeros((2, 2)))
    store.add_snapshot("sunamganj", "moderate_rain", 1.0, np.ones((2, 2)), np.zeros((2, 2)))
    store.add_snapshot("dhaka", "moderate_rain", 0.0, np.full((2, 2), 3.0), np.zeros((2, 2)))
    assert store.available_times("sunamganj", "moderate_rain") == (0.0, 1.0)
    assert store.get_snapshot("dhaka", "moderate_rain", 0.0)["depth"][0, 0] == 3.0
    with pytest.raises(TemporalResultError):
        store.get_snapshot("sunamganj", "moderate_rain", 9.0)


def test_stored_array_immutability_on_read():
    store = ScenarioResultStore()
    record = _empty_record()
    depth = np.array([[0.1, 0.2], [0.3, 0.4]])
    store.put(record)
    store.add_snapshot("sunamganj", "moderate_rain", 0.0, depth, np.zeros((2, 2)))
    depth[:, :] = 0.0
    before = copy.deepcopy(store.get_snapshot("sunamganj", "moderate_rain", 0.0)["depth"])
    store.get_snapshot("sunamganj", "moderate_rain", 0.0)
    after = store.get("sunamganj", "moderate_rain").depth_by_time[0.0]
    np.testing.assert_array_equal(before, after)
    assert after[0, 0] == pytest.approx(0.1)


def test_simulation_service_captures_application_snapshots():
    config = SimulationConfig(Nx=10, Ny=10, Lx=100.0, Ly=100.0, T_end=0.05, name="temporal")
    z = np.zeros((10, 10), dtype=np.float64)
    service = SimulationService(config)
    result = service.run_scenario(dem=z, rainfall_rate=0.0, steps=2, track_progress=False)
    assert result.success is True
    assert len(result.snapshots) == 3
    times = [snap.time for snap in result.snapshots]
    assert times == sorted(times)
    assert times[0] == pytest.approx(0.0)
    np.testing.assert_array_equal(result.snapshots[-1].depth, result.final_state.h)


@pytest.fixture
def client():
    set_session(ScenarioSession.default_sunamganj())
    reset_result_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_result_store()


def test_scenario_run_timeline_and_snapshot_api(client):
    run = client.post(
        "/api/scenario/run",
        json={
            "nx": 12,
            "ny": 12,
            "rainfall_rate": 1e-4,
            "duration_seconds": 0.5,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    assert run.status_code == 200
    data = run.json()
    assert data["success"] is True
    assert "available_times" in data
    assert len(data["available_times"]) >= 2
    assert data["start_time"] == pytest.approx(data["available_times"][0])
    assert data["end_time"] == pytest.approx(data["available_times"][-1])

    timeline = client.get(
        "/api/scenario/moderate_rain/timeline",
        params={"city_id": "sunamganj"},
    )
    assert timeline.status_code == 200
    assert timeline.json()["timestep_count"] == len(data["available_times"])

    snap = client.get(
        "/api/scenario/moderate_rain/snapshot",
        params={"city_id": "sunamganj", "time": data["available_times"][-1]},
    )
    assert snap.status_code == 200
    body = snap.json()
    assert body["time"] == pytest.approx(data["available_times"][-1])
    assert body["modeled"] is True
    assert len(body["depth"]) == 12

    missing = client.get(
        "/api/scenario/moderate_rain/snapshot",
        params={"city_id": "sunamganj", "time": 99.0},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["error_code"] == "TIME_NOT_FOUND"


def test_comparison_uses_stored_time_and_rejects_missing(client):
    for scenario_id in ("moderate_rain", "heavy_rain"):
        response = client.post(
            "/api/scenario/run",
            json={
                "nx": 10,
                "ny": 10,
                "rainfall_rate": 1e-4,
                "duration_seconds": 0.5,
                "city_id": "sunamganj",
                "scenario_id": scenario_id,
            },
        )
        assert response.status_code == 200
    times = response.json()["available_times"]
    ok = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
            "time": times[0],
        },
    )
    assert ok.status_code == 200
    assert ok.json()["comparison"]["time"] == pytest.approx(times[0])

    missing = client.post(
        "/api/scenario/compare",
        json={
            "city_id": "sunamganj",
            "scenario_a_id": "moderate_rain",
            "scenario_b_id": "heavy_rain",
            "layer": "depth",
            "time": 42.0,
        },
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["error_code"] == "TIME_NOT_FOUND"


def test_inspection_uses_stored_time_and_rejects_missing(client):
    run = client.post(
        "/api/scenario/run",
        json={
            "nx": 10,
            "ny": 10,
            "rainfall_rate": 1e-4,
            "duration_seconds": 0.5,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
        },
    )
    times = run.json()["available_times"]
    ok = client.get(
        "/api/cell/inspect",
        params={
            "lat": 24.95,
            "lon": 91.35,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
            "time": times[0],
        },
    )
    assert ok.status_code == 200
    assert ok.json()["time"] == pytest.approx(times[0])

    missing = client.get(
        "/api/cell/inspect",
        params={
            "lat": 24.95,
            "lon": 91.35,
            "city_id": "sunamganj",
            "scenario_id": "moderate_rain",
            "time": 77.0,
        },
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["error_code"] == "TIME_NOT_FOUND"
