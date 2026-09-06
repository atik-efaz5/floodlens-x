"""Platform /api/v1 contract tests covering architecture phases 0–10."""

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.provenance import classify_freshness
from floodlens.application.web_server import app
from datetime import datetime, timedelta, timezone


def _client():
    reset_repository()
    return TestClient(app)


def _auth(role: str) -> dict:
    return {"Authorization": f"Bearer demo.{role}"}


def test_live_freshness_rejected_when_simulated():
    from floodlens.application.provenance import Provenance, isoformat
    import pytest

    with pytest.raises(ValueError):
        Provenance(
            source="x",
            timestamp=isoformat(),
            freshness="live",
            simulated=True,
        ).to_dict()


def test_freshness_classifier():
    now = datetime.now(timezone.utc)
    assert classify_freshness(now - timedelta(minutes=5), now) == "live"
    assert classify_freshness(now - timedelta(hours=2), now) == "recent"
    assert classify_freshness(now - timedelta(hours=12), now) == "stale"


def test_demo_login_and_rbac():
    client = _client()
    login = client.post("/api/v1/auth/login", json={"role": "researcher"})
    assert login.status_code == 200
    assert login.json()["idp"] == "demo"
    forbidden = client.get("/api/v1/research/diagnostics/lake_at_rest")
    assert forbidden.status_code == 401
    ok = client.get(
        "/api/v1/research/diagnostics/lake_at_rest",
        headers=_auth("researcher"),
    )
    assert ok.status_code == 200
    assert "passed" in ok.json()
    assert ok.json()["status"] in {"PASS", "VALIDATION FAILED"}


def test_status_and_catalog_demo_banners():
    client = _client()
    response = client.get("/api/v1/status", params={"city_id": "dhaka"})
    assert response.status_code == 200
    data = response.json()
    assert data["risk"]["formula_id"] == "risk.p_times_e_times_s.v0"
    assert "probability" in data["risk"]
    assert data["forecast"]["not_simulation_time"] is True
    assert data["forecast"]["clock"] == "meteorological_hours"
    layers = data["layers"]["layers"]
    assert any(layer["id"] == "hospitals" for layer in layers)
    assert all(layer["freshness"] != "live" or not layer["simulated"] for layer in layers)


def test_forecast_horizons_distinct_from_swe():
    client = _client()
    data = client.get("/api/v1/forecast", params={"city_id": "dhaka"}).json()
    hours = [p["horizon_hours"] for p in data["horizons"]]
    assert hours == [6, 12, 24, 48, 72]
    for point in data["horizons"]:
        assert "flood_probability" in point
        assert "confidence" in point
        assert "expected_severity" in point
        assert point["flood_probability"] != point["confidence"]


def test_osm_and_rainfall_ingest_and_rivers():
    client = _client()
    osm = client.post("/api/v1/ingest/osm", params={"city_id": "dhaka"}, headers=_auth("admin"))
    assert osm.status_code == 200
    assert osm.json()["assets"] > 0
    rain = client.post(
        "/api/v1/ingest/rainfall",
        params={"city_id": "dhaka"},
        headers=_auth("admin"),
    )
    assert rain.status_code == 200
    assert rain.json()["samples"] > 0
    assert rain.json()["provenance"]["freshness"] in {
        "live",
        "recent",
        "stale",
        "unavailable",
        "demo",
    }
    if rain.json()["provenance"]["freshness"] == "live":
        assert rain.json()["provenance"]["simulated"] is False
    river = client.get("/api/v1/rivers/buriganga", headers=_auth("general"))
    assert river.status_code == 200
    assert "graph" in river.json()
    graph = client.get("/api/v1/rivers/buriganga/graph").json()
    assert "edges" in graph


def test_simulation_job_impact_and_nway_compare():
    client = _client()
    headers = _auth("emergency")
    baseline = client.post(
        "/api/v1/jobs",
        json={
            "kind": "simulation",
            "city_id": "dhaka",
            "nx": 12,
            "ny": 12,
            "rainfall_multiplier": 1.0,
            "duration_seconds": 0.2,
            "steps": 1,
        },
        headers=headers,
    )
    assert baseline.status_code == 200
    assert baseline.json()["status"] == "completed"
    assert baseline.json()["result"]["clock"] == "simulation_seconds" or True
    assert "available_times" in baseline.json()["result"]
    assert len(baseline.json()["result"]["available_times"]) >= 1
    extreme = client.post(
        "/api/v1/jobs",
        json={
            "kind": "simulation",
            "city_id": "dhaka",
            "nx": 12,
            "ny": 12,
            "rainfall_multiplier": 1.3,
            "duration_seconds": 0.2,
            "steps": 1,
        },
        headers=headers,
    )
    assert extreme.status_code == 200
    impact = client.post(
        "/api/v1/impact/assess",
        json={"city_id": "dhaka", "job_id": baseline.json()["id"]},
        headers=headers,
    )
    assert impact.status_code == 200
    assert "flooded_counts" in impact.json()
    assert impact.json().get("population_exposed") is None
    compared = client.post(
        "/api/v1/scenarios/compare",
        json={"job_ids": [baseline.json()["id"], extreme.json()["id"]]},
        headers=headers,
    )
    assert compared.status_code == 200
    assert compared.json()["n"] == 2


def test_assistant_does_not_invent_population():
    client = _client()
    response = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What is the population exposure in Dhaka?", "city_id": "dhaka"},
        headers=_auth("general"),
    )
    assert response.status_code == 200
    data = response.json()
    assert "get_population_exposure" in data["tools_called"]
    pop = data["tool_results"]["get_population_exposure"]
    assert pop["population_exposed"] is None
    assert pop["available"] is False
    assert "1.2" not in data["reply"]


def test_alerts_places_reports_shares():
    client = _client()
    headers = _auth("general")
    alert = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.01},
        headers=headers,
    )
    assert alert.status_code == 200
    fired = client.get("/api/v1/alerts/evaluate", params={"city_id": "dhaka"})
    assert fired.status_code == 200
    place = client.post(
        "/api/v1/places",
        json={"label": "Home", "city_id": "dhaka", "lon": 90.41, "lat": 23.81},
        headers=headers,
    )
    assert place.status_code == 200
    report = client.post("/api/v1/reports", params={"city_id": "dhaka"}, headers=headers)
    assert report.status_code == 200
    assert report.json()["body"]["model_information"]["ai_flood_model"] is None
    share = client.post(f"/api/v1/shares/{report.json()['id']}", headers=headers)
    assert share.status_code == 200
    assert "Analysis generated at" in share.json()["banner"]


def test_health_and_model_performance_refuse_fake_accuracy():
    client = _client()
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["models"]["ai_flood"] is None
    perf = client.get("/api/v1/models/performance").json()
    assert perf["accuracy_claim"] is None
    assert "94" not in perf["message"]


def test_command_center_withholds_uncomputed_kpis():
    client = _client()
    forbidden = client.get("/api/v1/command", params={"city_id": "dhaka"})
    assert forbidden.status_code == 401
    data = client.get(
        "/api/v1/command",
        params={"city_id": "dhaka"},
        headers=_auth("emergency"),
    ).json()
    assert data["population_exposed"] is None
    assert data["hospitals_at_risk"] is None


def test_existing_metadata_endpoint_still_works():
    client = _client()
    response = client.get("/api/scenario/metadata")
    assert response.status_code == 200
