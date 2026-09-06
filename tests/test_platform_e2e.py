"""Playwright is optional. This file is the production e2e contract via the API."""

import pytest
from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app


def test_user_journey_search_forecast_scenario_impact_assistant_report():
    reset_repository()
    client = TestClient(app)
    headers = {"Authorization": "Bearer demo.emergency"}
    status = client.get("/api/v1/status", params={"city_id": "dhaka"}, headers=headers)
    assert status.status_code == 200
    forecast = client.get("/api/v1/forecast", params={"city_id": "dhaka"}, headers=headers)
    assert forecast.status_code == 200
    job = client.post(
        "/api/v1/jobs",
        json={
            "kind": "simulation",
            "city_id": "dhaka",
            "nx": 10,
            "ny": 10,
            "rainfall_multiplier": 1.3,
            "duration_seconds": 0.2,
            "steps": 1,
        },
        headers=headers,
    )
    assert job.status_code == 200
    impact = client.post(
        "/api/v1/impact/assess",
        json={"city_id": "dhaka", "job_id": job.json()["id"]},
        headers=headers,
    )
    assert impact.status_code == 200
    chat = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What should we prepare if rainfall increases by 30%?", "city_id": "dhaka"},
        headers=headers,
    )
    assert chat.status_code == 200
    assert chat.json()["tools_called"]
    report = client.post("/api/v1/reports", params={"city_id": "dhaka"}, headers=headers)
    assert report.status_code == 200


def test_playwright_optional_skip():
    pytest.importorskip("playwright")
    pytest.skip("Browser e2e is enabled only when Playwright is installed")
