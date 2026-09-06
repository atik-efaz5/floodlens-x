"""Phase 7.4 scenario / digital-twin workspace. No fabricated solver coupling."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from floodlens.application.canonical import RainfallObservation
from floodlens.application.repository import get_repository, reset_repository
from floodlens.application.runoff import precip_mm_to_mps
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Authorization": "Bearer demo.emergency"}
GENERAL = {"Authorization": "Bearer demo.general"}
RESEARCH = {"Authorization": "Bearer demo.researcher"}


def _client():
    reset_repository()
    return TestClient(app)


def _put_rain(city_id="dhaka", mm=3.6):
    get_repository().put_rainfall(
        RainfallObservation(
            city_id=city_id,
            value_mm=mm,
            unit="mm",
            observed_at="2026-01-01T00:00:00Z",
            valid_at="2026-01-01T00:00:00Z",
            kind="FORECAST",
            provider="test",
            data_status="DEMO",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    )


def test_scenario_capabilities_and_validation():
    client = _client()
    caps = client.get("/api/v1/scenarios/capabilities", headers=GENERAL)
    assert caps.status_code == 200
    body = caps.json()
    assert body["river_level_applied_to_solver"] is False
    by_id = {row["id"]: row for row in body["parameters"]}
    assert by_id["rainfall_multiplier"]["status"] == "SUPPORTED"
    assert by_id["river_level_delta_m"]["status"] == "PARTIAL"
    assert "NOT CURRENTLY APPLIED" in by_id["river_level_delta_m"]["note"]
    assert by_id["upstream_discharge"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["drainage_degradation"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["land_use"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["terrain_modification"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["dam_release"]["status"] == "NOT_IMPLEMENTED"
    bad = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": -1},
        headers=HEADERS,
    )
    assert bad.status_code == 422
    forbidden = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": 1.3},
        headers=GENERAL,
    )
    assert forbidden.status_code == 403
    missing = client.get("/api/v1/scenarios/baseline", params={"city_id": "not-a-city"}, headers=HEADERS)
    assert missing.status_code == 404


def test_rainfall_plus_30_applies_multiplier_and_stores_artifacts():
    client = _client()
    _put_rain()
    base = precip_mm_to_mps(3.6, 1.0)
    baseline = client.post(
        "/api/v1/scenarios",
        json={
            "city_id": "dhaka",
            "name": "Baseline ×1.0",
            "rainfall_multiplier": 1.0,
            "nx": 8,
            "ny": 8,
            "duration_seconds": 0.2,
            "steps": 1,
            "allow_synthetic_dem": True,
        },
        headers=HEADERS,
    )
    assert baseline.status_code == 200
    scenario = client.post(
        "/api/v1/scenarios",
        json={
            "city_id": "dhaka",
            "name": "Rainfall +30%",
            "rainfall_multiplier": 1.3,
            "baseline_id": baseline.json()["id"],
            "nx": 8,
            "ny": 8,
            "duration_seconds": 0.2,
            "steps": 1,
            "allow_synthetic_dem": True,
        },
        headers=HEADERS,
    )
    assert scenario.status_code == 200
    job = client.get(f"/api/v1/jobs/{scenario.json()['id']}", headers=HEADERS).json()
    assert job["status"] == "completed"
    assert job["kind"] == "scenario"
    result = job["result"]
    assert "depth" not in result
    assert result["artifact_id"]
    assert result["rainfall_multiplier"] == 1.3
    assert result["rainfall_rate_base_mps"] == pytest.approx(base)
    assert result["rainfall_rate_applied_mps"] == pytest.approx(base * 1.3)
    assert result["rainfall_rate_applied_mps"] != result["rainfall_rate_base_mps"]
    raw = json.dumps(result)
    assert len(raw) < 8000
    listed = client.get("/api/v1/scenarios/history", params={"city_id": "dhaka"}, headers=GENERAL)
    assert listed.status_code == 200
    names = [row.get("name") for row in listed.json()["scenarios"]]
    assert "Rainfall +30%" in names
    overlay = client.get(f"/api/v1/artifacts/{result['artifact_id']}/overlay.png")
    assert overlay.status_code == 200


def test_river_level_not_applied_to_solver():
    client = _client()
    _put_rain()
    posted = client.post(
        "/api/v1/scenarios",
        json={
            "city_id": "dhaka",
            "rainfall_multiplier": 1.0,
            "river_level_delta_m": 1.5,
            "nx": 8,
            "ny": 8,
            "duration_seconds": 0.2,
            "steps": 1,
            "allow_synthetic_dem": True,
        },
        headers=HEADERS,
    )
    assert posted.status_code == 200
    job = client.get(f"/api/v1/jobs/{posted.json()['id']}", headers=HEADERS).json()
    assert job["status"] == "completed"
    result = job["result"]
    assert result["river_level_delta_m"] == 1.5
    assert result["river_level_applied_to_solver"] is False
    assert job["river_level_applied_to_solver"] is False
    chain = client.get(
        "/api/v1/scenarios/causal-chain",
        params={"city_id": "dhaka", "job_id": job["id"]},
        headers=HEADERS,
    ).json()
    river = next(link for link in chain["links"] if link["name"].startswith("RIVER"))
    assert river["status"] == "NOT MODELED"
    assert chain["river_level_applied_to_solver"] is False


def test_failed_scenario_is_visible_when_rainfall_missing():
    client = _client()
    posted = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": 1.3, "nx": 8, "ny": 8, "allow_synthetic_dem": True},
        headers=HEADERS,
    )
    assert posted.status_code == 200
    job = client.get(f"/api/v1/jobs/{posted.json()['id']}", headers=HEADERS).json()
    assert job["status"] == "failed"
    assert job["error"]
    assert job["result"] in (None, {})
    assert "rainfall" in job["error"].lower() or "unavailable" in job["error"].lower()


def test_compare_difference_impact_provenance_and_report():
    client = _client()
    _put_rain()
    a = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": 1.0, "nx": 8, "ny": 8, "duration_seconds": 0.2, "steps": 1, "allow_synthetic_dem": True},
        headers=HEADERS,
    ).json()
    b = client.post(
        "/api/v1/scenarios",
        json={"city_id": "dhaka", "rainfall_multiplier": 1.3, "nx": 8, "ny": 8, "duration_seconds": 0.2, "steps": 1, "allow_synthetic_dem": True, "baseline_id": a["id"]},
        headers=HEADERS,
    ).json()
    compared = client.post("/api/v1/scenarios/compare", json={"job_ids": [a["id"], b["id"]]}, headers=HEADERS).json()
    assert compared["n"] == 2
    assert compared["difference"] is not None
    assert compared["difference"]["population_exposed"] is None
    assert compared["comparisons"][0]["population_exposed"] is None
    if compared["comparisons"][0]["max_depth_m"] is None or compared["comparisons"][1]["max_depth_m"] is None:
        assert compared["difference"]["max_depth_m"] is None
    diff = client.get(
        "/api/v1/scenarios/difference",
        params={"baseline_job": a["id"], "scenario_job": b["id"]},
        headers=HEADERS,
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["available"] is True
    assert body["kind"] == "difference"
    assert body["mode"] == "absolute"
    assert "depth" not in body
    png = client.get(f"/api/v1/artifacts/{body['artifact_id']}/overlay.png")
    assert png.status_code == 200
    workspace = client.get(
        "/api/v1/scenarios/workspace",
        params={"city_id": "dhaka", "baseline_job": a["id"], "scenario_job": b["id"]},
        headers=HEADERS,
    )
    assert workspace.status_code == 200
    ws = workspace.json()
    assert ws["river_level_applied_to_solver"] is False
    assert ws["compare"]["difference"]["population_exposed"] is None
    impact = client.get("/api/v1/impact", params={"city_id": "dhaka", "job_id": b["id"]}, headers=HEADERS)
    assert impact.status_code == 200
    assert impact.json()["categories"]["population"]["affected"] is None
    report = client.post(
        "/api/v1/reports",
        params={"city_id": "dhaka", "baseline_job": a["id"], "scenario_job": b["id"]},
        headers=HEADERS,
    )
    assert report.status_code == 200
    inner = report.json()["body"]
    assert inner["scenario"]["job_id"] == b["id"]
    assert inner["scenario"]["modified_variables"]["river_level_applied_to_solver"] is False
    assert inner["population_impact"]["available"] is False
    share = client.post(f"/api/v1/shares/{report.json()['id']}", headers=HEADERS)
    assert share.status_code == 200
    assert share.json()["banner"].startswith("Analysis generated at ")
    assert share.json()["scenario_id"] == b["id"]
    times = client.get(f"/api/v1/jobs/{b['id']}", headers=HEADERS).json()["result"].get("available_times") or []
    assert all(isinstance(t, (int, float)) for t in times)


def test_assistant_rainfall_30_uses_engine_not_invention():
    client = _client()
    chat = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What happens if rainfall increases by 30%?", "city_id": "dhaka"},
        headers=HEADERS,
    ).json()
    assert "get_region" in chat["tools_called"]
    assert "run_scenario" in chat["tools_called"]
    assert "compare_scenarios" in chat["tools_called"]
    job = chat["tool_results"]["run_scenario"]
    result = job.get("result") or {}
    assert job["status"] in {"completed", "failed"}
    if job["status"] == "completed":
        assert result["rainfall_multiplier"] == 1.3
        assert result["rainfall_rate_applied_mps"] == pytest.approx(result["rainfall_rate_base_mps"] * 1.3)
        assert result["river_level_applied_to_solver"] is False
        assert "1.3" in chat["reply"] or "rainfall_multiplier=1.3" in chat["reply"]
        assert "river_level_applied_to_solver=False" in chat["reply"] or "not applied" in chat["reply"].lower()
    assert "will definitely flood" not in chat["reply"].lower()
    diff = (chat["tool_results"].get("compare_scenarios") or {}).get("difference") or {}
    assert diff.get("population_exposed") is None


def test_frontend_scenario_workspace_contracts():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    controls = (ROOT / "frontend/src/scenario/ScenarioControls.jsx").read_text()
    summary = (ROOT / "frontend/src/scenario/ScenarioSummary.jsx").read_text()
    compare = (ROOT / "frontend/src/scenario/ScenarioCompareBar.jsx").read_text()
    history = (ROOT / "frontend/src/scenario/ScenarioHistory.jsx").read_text()
    progress = (ROOT / "frontend/src/platform/JobProgressPanel.jsx").read_text()
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    assert "ScenarioControls" in app_js
    assert "ScenarioSummary" in app_js
    assert "ScenarioCompareBar" in app_js
    assert "ScenarioHistory" in app_js
    assert "ScenarioPresets" in app_js
    assert "ForecastTimeline" in app_js
    assert "ImpactPanel" in app_js
    assert "NOT CURRENTLY APPLIED TO SWE SOLVER" in controls
    assert "Solver coupling: NOT APPLIED" in controls
    assert "rainfall_multiplier" in controls
    assert "NOT_IMPLEMENTED" in controls
    assert "POPULATION EXPOSURE: UNAVAILABLE" in summary
    assert "NOT MODELED" in summary
    assert "6/12/24/48/72h" in compare
    assert "Analysis generated at" in compare
    assert "Recent scenarios" in history
    assert "75% complete" not in progress
    assert "Solver percent UNAVAILABLE" in progress
    assert 'id: "simulation"' in shell
    blob = controls + summary + compare + history
    assert "Evacuate now" not in blob
    assert "fit_unet" not in app_js


def test_phase74_does_not_enable_spatial_ai_or_touch_solver():
    blobs = [
        (ROOT / "frontend/src/App.jsx").read_text(),
        (ROOT / "src/floodlens/application/scenario_workspace.py").read_text(),
    ]
    report = ROOT / "docs/PHASE_7_4_SCENARIO_DIGITAL_TWIN_REPORT.md"
    if report.exists():
        blobs.append(report.read_text())
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "mark_spatial_validated" not in blob
        assert "river_level_applied_to_solver = True" not in blob
        assert "river_level_applied_to_solver: True" not in blob
    client = _client()
    spatial = client.post("/api/v1/forecast/ai-spatial", json={"city_id": "dhaka"}, headers=HEADERS)
    assert spatial.status_code == 200
    job = spatial.json()
    fetched = client.get(f"/api/v1/forecast/ai-spatial/{job['id']}", headers=HEADERS)
    body = fetched.json()
    result = body.get("result") or {}
    if body.get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"
