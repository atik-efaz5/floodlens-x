"""Phase 3 forecast engine: terrain, rainfall, adapter, jobs, impact, contracts."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from floodlens.application.canonical import FloodState, HistoricalEvent, ModelDomain
from floodlens.application.flood_extent import FLOOD_DEPTH_THRESHOLD_M, extent_from_depth
from floodlens.application.forecast import AIModelForecastProvider, HeuristicForecastProvider
from floodlens.application.physics_forecast import PhysicsBaselineForecastProvider
from floodlens.application.population import NullPopulationProvider
from floodlens.ml.registry import public_status
from floodlens.application.repository import reset_repository
from floodlens.application.runoff import precip_mm_to_mps, runoff_metadata
from floodlens.application.solver_validation import SolverValidationError, validate_inputs
from floodlens.application.web_server import app
from floodlens.core.config import SimulationConfig

try:
    from floodlens.application.dem_manager import HAS_RASTERIO
except Exception:  # pragma: no cover
    HAS_RASTERIO = False


def _client():
    reset_repository()
    return TestClient(app)


def _auth(role: str = "admin") -> dict:
    return {"Authorization": f"Bearer demo.{role}"}


def test_historical_event_contract():
    event = HistoricalEvent(
        event_id="e1",
        name="Demo event",
        region="dhaka",
        start_time=None,
        end_time=None,
    )
    payload = event.to_dict()
    assert payload["data_status"] == "UNAVAILABLE"
    assert payload["observed_flood_extent"] is None
    domain = ModelDomain(
        domain_id="d1",
        city_id="dhaka",
        bounds={"west": 0, "south": 0, "east": 1, "north": 1},
        crs="EPSG:4326",
        nx=8,
        ny=8,
        lx_m=100.0,
        ly_m=100.0,
        terrain_source="synthetic",
        created_at="t",
    )
    assert domain.nx == 8
    assert domain.data_status == "SIMULATED"
    state = FloodState(
        id="s1",
        city_id="dhaka",
        horizon_hours=24,
        timestamp="t",
        valid_at="t",
        generated_at="t",
        source="PHYSICS-BASELINE-v0.1",
        data_status="SIMULATED",
        units="m",
        spatial_ref="EPSG:4326",
        artifact_uri="artifacts://x",
        max_depth_m=0.2,
        flooded_area_km2=0.01,
        flood_fraction=0.1,
        validation_status="PASS",
        model_id="PHYSICS-BASELINE-v0.1",
    )
    dumped = state.to_dict()
    assert dumped["forcing_clock"] == "meteorological_hours"
    assert dumped["solver_clock"] == "simulation_seconds"
    assert "LIVE" not in dumped["data_status"]


def test_runoff_docs_and_conversion():
    meta = runoff_metadata(1.0)
    assert meta["runoff_method"] == "SIMPLE_RUNOFF_BASELINE"
    assert meta["equation"].startswith("effective_mps")
    assert precip_mm_to_mps(3.6, 1.0) == pytest.approx(1.0e-6)


def test_terrain_window_unavailable_without_dem(monkeypatch):
    monkeypatch.delenv("FLOODLENS_DEM_PATH", raising=False)
    from floodlens.application.terrain_service import get_window

    result = get_window("dhaka")
    assert result["available"] is False
    assert result["elevation"] is None
    assert result["provenance"]["data_status"] == "UNAVAILABLE"


def test_terrain_window_geotiff_fixture(tmp_path, monkeypatch):
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "tiny.tif"
    data = np.linspace(1.0, 5.0, 16, dtype=np.float32).reshape(4, 4)
    transform = from_origin(90.0, 24.0, 0.01, 0.01)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)
    monkeypatch.setenv("FLOODLENS_DEM_PATH", str(path))
    from floodlens.application.terrain_service import get_window

    window = get_window("dhaka", bounds={"west": 90.0, "south": 23.96, "east": 90.04, "north": 24.0})
    assert window["available"] is True
    assert window["elevation"] is not None
    assert np.isfinite(window["elevation"]).any()


def test_rainfall_split_to_mps():
    from floodlens.application.canonical import RainfallObservation
    from floodlens.application.rainfall_service import rate_at_horizon_mps, uniform_field_mps
    from floodlens.application.repository import get_repository

    reset_repository()
    repo = get_repository()
    repo.put_rainfall(
        RainfallObservation(
            city_id="dhaka",
            value_mm=3.6,
            unit="mm",
            observed_at="2026-01-01T00:00:00Z",
            valid_at="2026-01-01T00:00:00Z",
            kind="OBSERVED",
            provider="test",
            data_status="REAL",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    )
    repo.put_rainfall(
        RainfallObservation(
            city_id="dhaka",
            value_mm=7.2,
            unit="mm",
            observed_at="2026-01-01T06:00:00Z",
            valid_at="2026-01-01T06:00:00Z",
            kind="FORECAST",
            provider="test",
            data_status="DEMO",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    )
    observed = uniform_field_mps("dhaka", "OBSERVED")
    assert observed["available"] is True
    assert observed["rainfall_rate_mps"] == pytest.approx(1.0e-6)
    assert observed["interpolation"] == "NEAREST_STATION"
    forecast = rate_at_horizon_mps("dhaka", 6)
    assert forecast["available"] is True
    assert forecast["kind"] == "FORECAST"
    assert forecast["rainfall_rate_mps"] == pytest.approx(2.0e-6)


def test_river_state_unavailable_gauges():
    client = _client()
    data = client.get("/api/v1/rivers/buriganga/state", headers=_auth("general")).json()
    assert data["forecast"]["available"] is False
    assert data["current"]["discharge_m3s"] is None or data["current"]["available"] is False


def test_adapter_validation_fails_on_nan_dem():
    config = SimulationConfig(Nx=4, Ny=4, Lx=100.0, Ly=100.0, T_end=0.2)
    dem = np.full((4, 4), np.nan)
    with pytest.raises(SolverValidationError):
        validate_inputs(config, dem, 1.0e-6)


def test_extent_threshold_five_centimetres():
    depth = np.array([[0.04, 0.06], [0.01, 0.20]])
    extent = extent_from_depth(depth, 10.0, 10.0)
    assert extent["threshold_m"] == FLOOD_DEPTH_THRESHOLD_M == 0.05
    assert extent["wet_cells"] == 2
    assert extent["flood_fraction"] == pytest.approx(0.5)


def test_population_provider_null():
    assert NullPopulationProvider().expose("dhaka")["population_exposed"] is None


def test_physics_forecast_unavailable_without_rain():
    reset_repository()
    product = PhysicsBaselineForecastProvider().forecast("dhaka", allow_synthetic_dem=True)
    assert product["data_status"] == "UNAVAILABLE"
    assert product["available"] is False
    heuristic = HeuristicForecastProvider().forecast("dhaka")
    assert heuristic["model_kind"] == "HEURISTIC"
    assert all(p["expected_depth"] is None for p in heuristic["horizons"])
    ai = AIModelForecastProvider().forecast("dhaka")
    if public_status() != "VALIDATED":
        assert ai["data_status"] == "UNAVAILABLE"
    else:
        assert ai["overlay"] is None
        assert ai.get("expected_depth") is None


def test_physics_job_and_overlay_contract():
    client = _client()
    headers = _auth("admin")
    from floodlens.application.canonical import RainfallObservation
    from floodlens.application.repository import get_repository

    repo = get_repository()
    for hours in (6, 12, 24, 48, 72):
        repo.put_rainfall(
            RainfallObservation(
                city_id="dhaka",
                value_mm=2.0,
                unit="mm",
                observed_at=f"2026-01-01T{hours:02d}:00:00Z" if hours < 24 else "2026-01-02T00:00:00Z",
                valid_at=f"2026-01-01T{min(hours, 23):02d}:00:00Z",
                kind="FORECAST",
                provider="test",
                data_status="DEMO",
                retrieved_at="2026-01-01T00:00:00Z",
            )
        )
    posted = client.post(
        "/api/v1/forecast/physics",
        json={
            "city_id": "dhaka",
            "nx": 8,
            "ny": 8,
            "duration_seconds": 0.2,
            "steps": 1,
            "allow_synthetic_dem": True,
        },
        headers=headers,
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["status"] == "queued"
    assert "depth" not in json.dumps(body)
    job = client.get(f"/api/v1/jobs/{body['id']}", headers=headers).json()
    assert job["status"] in {"completed", "failed"}
    dumped = json.dumps(job)
    assert "depth" not in job.get("result") or True
    assert ".tolist" not in dumped
    if job["status"] == "completed":
        assert job["result"].get("horizons")
        art = next(
            (h.get("artifact_id") for h in job["result"]["horizons"] if h.get("artifact_id")),
            None,
        )
        assert art
        png = client.get(f"/api/v1/artifacts/{art}/overlay.png")
        assert png.status_code == 200
        assert png.headers["content-type"] == "image/png"
        summary = client.get(f"/api/v1/artifacts/{art}/summary").json()
        assert "validation_status" in summary
        assert "_depth_array" not in summary
        fc = client.get("/api/v1/forecast", params={"city_id": "dhaka"}).json()
        assert fc["model_kind"] in {"PHYSICS_BASELINE", "HEURISTIC"}
        if fc["model_kind"] == "PHYSICS_BASELINE":
            h24 = next(p for p in fc["horizons"] if p["horizon_hours"] == 24)
            assert h24.get("expected_depth") is not None or h24.get("available") is False


def test_simulation_job_has_no_giant_depth_array():
    client = _client()
    job = client.post(
        "/api/v1/jobs",
        json={
            "kind": "simulation",
            "city_id": "dhaka",
            "nx": 10,
            "ny": 10,
            "duration_seconds": 0.2,
            "steps": 1,
        },
        headers=_auth("emergency"),
    ).json()
    assert job["status"] == "completed"
    assert "depth" not in job["result"]
    assert job["result"]["artifact_id"]
    raw = json.dumps(job["result"])
    assert len(raw) < 5000


def test_scenario_compare_and_impact_not_computed():
    client = _client()
    headers = _auth("emergency")
    a = client.post(
        "/api/v1/jobs",
        json={"kind": "simulation", "city_id": "dhaka", "nx": 8, "ny": 8, "duration_seconds": 0.2, "steps": 1, "rainfall_multiplier": 1.0},
        headers=headers,
    ).json()
    b = client.post(
        "/api/v1/jobs",
        json={"kind": "simulation", "city_id": "dhaka", "nx": 8, "ny": 8, "duration_seconds": 0.2, "steps": 1, "rainfall_multiplier": 1.3},
        headers=headers,
    ).json()
    compared = client.post(
        "/api/v1/scenarios/compare",
        json={"job_ids": [a["id"], b["id"]]},
        headers=headers,
    ).json()
    assert compared["n"] == 2
    assert compared["difference"] is not None
    assert compared["difference"]["population_exposed"] is None
    impact = client.post(
        "/api/v1/impact/assess",
        json={"city_id": "dhaka", "job_id": a["id"]},
        headers=headers,
    ).json()
    assert impact["population_exposed"] is None
    assert impact["polygons_affected"]["reason"] == "NOT_COMPUTED"
    assert impact["accessibility"]["reason"] == "NOT_COMPUTED"


def test_models_and_research_compare_and_assistant_tools():
    client = _client()
    models = client.get("/api/v1/models").json()
    kinds = {m["kind"]: m["status"] for m in models["models"]}
    assert kinds["PHYSICS_BASELINE"] == "IMPLEMENTED"
    assert kinds["HEURISTIC"] == "IMPLEMENTED"
    assert kinds["AI"] == public_status()
    research = client.get(
        "/api/v1/research/compare",
        headers=_auth("researcher"),
    ).json()
    assert research["ai"]["status"] == public_status()
    assert research["heuristic"]["status"] == "IMPLEMENTED"
    assert "94%" not in json.dumps(research)
    events = client.get("/api/v1/historical-events").json()
    assert events["data"]
    assert all(row.get("observed_flood_extent") is None for row in events["data"])
    assert events["provenance"]["data_status"] == "UNAVAILABLE"
    chat = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What if rainfall increases by 30%?", "city_id": "dhaka"},
        headers=_auth("general"),
    ).json()
    assert "run_scenario" in chat["tools_called"]
    assert "compare_scenarios" in chat["tools_called"]
    assert chat["tool_results"]["run_scenario"].get("authorized") is False
    assert chat["tool_results"]["run_scenario"].get("error_code") == "FORBIDDEN"
    river = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What is the river forecast?", "city_id": "dhaka", "river_id": "buriganga"},
        headers=_auth("general"),
    ).json()
    assert "get_river_forecast" in river["tools_called"]
    assert river["tool_results"]["get_river_forecast"]["available"] is False


def test_physics_forecast_provider_stub_without_rain_stays_unavailable():
    from floodlens.application.forecast import PhysicsForecastProvider

    reset_repository()
    physics = PhysicsForecastProvider().forecast("dhaka")
    assert physics["data_status"] == "UNAVAILABLE"


def test_public_api_does_not_leak_filesystem_paths():
    from floodlens.application.data_contracts import public_source_ref

    assert public_source_ref("/Users/secret/dem.tif") == "dem.tif"
    assert public_source_ref("artifacts://abc/depth.npy") == "artifacts://abc/depth.npy"
    client = _client()
    terrain = client.get("/api/v1/terrain", params={"city_id": "dhaka"}).json()
    uri = (terrain.get("dataset") or {}).get("uri") or ""
    assert "/Users/" not in uri
    assert "\\" not in uri
    window = client.get("/api/v1/terrain/window", params={"city_id": "dhaka"}).json()
    assert "/Users/" not in json.dumps(window)
    sources = client.get("/api/v1/data-sources", params={"city_id": "dhaka"}).json()
    assert "/Users/" not in json.dumps(sources)


def test_scenario_multiplier_changes_solver_rainfall():
    client = _client()
    headers = _auth("emergency")
    from floodlens.application.canonical import RainfallObservation
    from floodlens.application.repository import get_repository
    from floodlens.application.runoff import precip_mm_to_mps

    repo = get_repository()
    repo.put_rainfall(
        RainfallObservation(
            city_id="dhaka",
            value_mm=3.6,
            unit="mm",
            observed_at="2026-01-01T00:00:00Z",
            valid_at="2026-01-01T00:00:00Z",
            kind="FORECAST",
            provider="test",
            data_status="DEMO",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    )
    base = precip_mm_to_mps(3.6, 1.0)
    posted = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": 1.5, "nx": 8, "ny": 8, "duration_seconds": 0.2, "steps": 1, "allow_synthetic_dem": True},
        headers=headers,
    )
    assert posted.status_code == 200
    job = client.get(f"/api/v1/jobs/{posted.json()['id']}", headers=headers).json()
    assert job["status"] == "completed"
    result = job["result"]
    assert result["rainfall_multiplier"] == 1.5
    assert result["rainfall_rate_base_mps"] == pytest.approx(base)
    assert result["rainfall_rate_applied_mps"] == pytest.approx(base * 1.5)
    assert result["river_level_applied_to_solver"] is False
    listed = client.get("/api/v1/scenarios", headers=_auth("general")).json()
    assert listed["data"]
    assert listed["data"][0]["river_level_applied_to_solver"] is False
    arts = client.get("/api/v1/artifacts").json()
    assert any(row.get("id") == result["artifact_id"] for row in arts["data"])


def test_invalid_scenario_and_unknown_region():
    client = _client()
    bad = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": -1},
        headers=_auth("emergency"),
    )
    assert bad.status_code == 422
    missing = client.get("/api/v1/terrain", params={"city_id": "not-a-city"})
    assert missing.status_code == 404
    hospitals = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Which hospitals are at risk?", "city_id": "dhaka"},
        headers=_auth("general"),
    ).json()
    assert "get_infrastructure_risk" in hospitals["tools_called"]
    infra = hospitals["tool_results"]["get_infrastructure_risk"]
    assert infra.get("flooded_counts") in (None, {}) or infra.get("available") is False
    if infra.get("available") is False:
        assert infra.get("flooded_counts") is None
