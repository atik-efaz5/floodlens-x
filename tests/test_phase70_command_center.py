"""Phase 7.0 command-center frontend and API contracts. No training. No fake numbers."""

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]


def test_command_center_shell_and_capability_matrix():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    caps = (ROOT / "frontend/src/platform/capabilities.js").read_text()
    assert "ForecastTimeline" in app_js
    assert "AlertsPanel" in app_js
    assert "ImpactPanel" in app_js
    assert "JobsListPanel" in app_js
    assert "CapabilityMatrix" in app_js
    assert "LocationSearchBar" in app_js
    assert "StatusPanel" in app_js
    assert "aria-label=\"Location search\"" in (ROOT / "frontend/src/components/LocationSearchBar.jsx").read_text() or "aria-label=" in (
        ROOT / "frontend/src/components/LocationSearchBar.jsx"
    ).read_text()
    assert "DEMO / SIMULATED DATA" in shell
    assert "Command Center" in shell
    assert "Population exposure" in caps
    assert "UNAVAILABLE" in caps
    assert "ai_spatial" in caps
    assert "NOT_VALIDATED" in caps or "NOT_VALIDATED" in (ROOT / "frontend/src/platform/ModelStatusPanel.jsx").read_text()


def test_unavailable_states_are_explicit():
    river = (ROOT / "frontend/src/platform/RiverForecastPanel.jsx").read_text()
    impact = (ROOT / "frontend/src/platform/ImpactPanel.jsx").read_text()
    forecast = (ROOT / "frontend/src/platform/ForecastPanel.jsx").read_text()
    status = (ROOT / "frontend/src/platform/StatusPanel.jsx").read_text()
    assert "WATER LEVEL:" in river and "UNAVAILABLE" in river
    assert "DISCHARGE:" in river
    assert "POPULATION EXPOSURE" in impact
    assert "spatial AI flood maps are UNAVAILABLE" in forecast
    assert "Probability" in status and "Exposure" in status and "Severity" in status
    assert "confidence" in status.lower()
    badge = (ROOT / "frontend/src/platform/ProvenanceBadge.jsx").read_text()
    for label in ("REAL", "SIMULATED", "DEMO", "UNAVAILABLE", "PARTIAL", "EXPERIMENTAL"):
        assert label in badge


def test_roles_and_views_remain():
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    assert "general" in shell and "emergency" in shell
    assert "researcher" in shell and "admin" in shell
    for view in ("explore", "forecast", "simulation", "impact", "research", "reports", "alerts"):
        assert view in shell


def test_api_command_center_does_not_invent_population():
    reset_repository()
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo.emergency"}
    status = client.get("/api/v1/status", params={"city_id": "dhaka"}, headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["command"]["population_exposed"] is None
    assert body["risk"]["category"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}
    layers = client.get("/api/v1/catalog/layers", params={"city_id": "dhaka"})
    assert layers.status_code == 200
    population = next(row for row in layers.json()["layers"] if row["id"] == "population")
    assert population["data_status"] == "UNAVAILABLE"
    alerts = client.get("/api/v1/alerts/evaluate", params={"city_id": "dhaka"}, headers=headers)
    assert alerts.status_code == 200
    jobs = client.get("/api/v1/jobs", headers=headers)
    assert jobs.status_code == 200
    general = client.get("/api/v1/jobs", headers={"Authorization": "Bearer demo.general"})
    assert general.status_code == 403
    spatial = client.post(
        "/api/v1/forecast/ai-spatial",
        json={"city_id": "dhaka"},
        headers=headers,
    )
    assert spatial.status_code == 200
    job = spatial.json()
    fetched = client.get(f"/api/v1/forecast/ai-spatial/{job['id']}", headers=headers)
    assert fetched.status_code == 200
    body_job = fetched.json()
    result = body_job.get("result") or {}
    if body_job.get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"
    rivers = client.get("/api/v1/rivers", params={"city_id": "dhaka"}, headers=headers)
    assert rivers.status_code == 200
    payload_rivers = rivers.json()
    if payload_rivers.get("data"):
        assert "segments" in payload_rivers["data"][0]


def test_phase70_does_not_train_or_touch_solver():
    blobs = [
        (ROOT / "frontend/src/App.jsx").read_text(),
        (ROOT / "frontend/src/platform/capabilities.js").read_text(),
        (ROOT / "docs/PHASE_7_0_COMMAND_CENTER_REPORT.md").read_text()
        if (ROOT / "docs/PHASE_7_0_COMMAND_CENTER_REPORT.md").exists()
        else "PHASE 7.0",
    ]
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "mark_spatial_validated" not in blob
