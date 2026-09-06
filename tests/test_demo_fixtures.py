"""DEMO operational fixtures. Scientific UNAVAILABLE paths stay off via pytest.ini/conftest."""

from fastapi.testclient import TestClient

from floodlens.application.demo_fixtures import DEMO_EVENT_ID
from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

HEADERS = {"Authorization": "Bearer demo.emergency"}


def _client(monkeypatch):
    monkeypatch.setenv("FLOODLENS_DEMO_FIXTURES", "1")
    reset_repository()
    return TestClient(app)


def test_demo_river_series_is_labeled_demo_not_real(monkeypatch):
    client = _client(monkeypatch)
    status = client.get("/api/v1/rivers/buriganga", headers=HEADERS)
    assert status.status_code == 200
    body = status.json()
    assert body["provenance"]["data_status"] == "DEMO"
    assert body["provenance"]["simulated"] is True
    assert body["provenance"]["freshness"] != "LIVE"
    series = body["series"]
    assert len(series) >= 2
    assert series[-1]["water_level_m"] is not None
    assert series[-1]["discharge_m3s"] is not None
    assert series[-1]["data_status"] == "DEMO"
    obs = client.get("/api/v1/rivers/buriganga/observations", headers=HEADERS)
    assert obs.status_code == 200
    payload = obs.json()
    assert payload["water_level_status"] == "DEMO"
    assert payload["discharge_status"] == "DEMO"
    assert payload["current_water_level_m"] is not None
    roc = payload["rate_of_change_level"]
    assert roc["status"] == "DEMO"
    assert roc["value"] is not None


def test_demo_rainfall_and_terrain_preview(monkeypatch):
    client = _client(monkeypatch)
    rain = client.get(
        "/api/v1/observations",
        params={"city_id": "dhaka", "variable": "precipitation_mm"},
        headers=HEADERS,
    )
    assert rain.status_code == 200
    body = rain.json()
    assert body["data"]
    assert body["provenance"]["data_status"] == "DEMO"
    assert body["provenance"]["freshness"] != "LIVE"
    assert body["overlay_artifact_id"]
    png = client.get(f"/api/v1/artifacts/{body['overlay_artifact_id']}/overlay.png")
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
    terrain = client.get("/api/v1/terrain", params={"city_id": "dhaka"})
    assert terrain.status_code == 200
    tbody = terrain.json()
    assert tbody["dataset"]["data_status"] == "DEMO"
    assert tbody["available"] is True
    assert tbody["dataset"]["min_elevation"] is not None
    window = client.get("/api/v1/terrain/window", params={"city_id": "dhaka"})
    assert window.status_code == 200
    wbody = window.json()
    assert wbody["elevation"] is None
    assert wbody["preview_available"] is True
    assert wbody["provenance"]["data_status"] == "DEMO"
    hill = client.get(f"/api/v1/artifacts/{wbody['overlay_artifact_id']}/overlay.png")
    assert hill.status_code == 200
    assert hill.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_demo_population_evac_resources(monkeypatch):
    client = _client(monkeypatch)
    impact = client.get("/api/v1/impact", params={"city_id": "dhaka"}, headers=HEADERS)
    assert impact.status_code == 200
    pop = impact.json()["categories"]["population"]
    assert pop["status"] == "DEMO"
    assert isinstance(pop["affected"], int)
    command = client.get("/api/v1/status", params={"city_id": "dhaka"}, headers=HEADERS)
    assert command.json()["command"]["population_exposed"] == pop["affected"]
    evac = client.get("/api/v1/impact/evacuation", params={"city_id": "dhaka"}, headers=HEADERS)
    assert evac.status_code == 200
    ebody = evac.json()
    assert ebody["official_evacuation_order"] is False
    assert ebody["routes"]["status"] == "DEMO"
    assert ebody["routes"]["features"]
    assert ebody["road_accessibility"]["travel_time"] is None
    resources = client.get("/api/v1/impact/resources", params={"city_id": "dhaka"}, headers=HEADERS)
    assert resources.status_code == 200
    boats = resources.json()["inventory"]["rescue_boats"]
    assert boats["status"] == "DEMO"
    assert boats["kind"] == "DEMO RESOURCE INVENTORY"
    assert isinstance(boats["value"], int)


def test_demo_history_compare_and_spatial_ai_stays_unavailable(monkeypatch):
    client = _client(monkeypatch)
    events = client.get("/api/v1/history/events", headers=HEADERS)
    assert events.status_code == 200
    ids = [row["event_id"] for row in events.json()["data"]]
    assert DEMO_EVENT_ID in ids
    compare = client.get(f"/api/v1/history/events/{DEMO_EVENT_ID}/compare", headers=HEADERS)
    assert compare.status_code == 200
    body = compare.json()
    assert body["comparison"] == "COMPARABLE"
    assert body["metrics"]["data_status"] == "DEMO"
    assert body["metrics"]["iou"] is not None
    preds = client.get(f"/api/v1/history/events/{DEMO_EVENT_ID}/predictions", headers=HEADERS)
    spatial = next(row for row in preds.json()["predictions"] if row.get("kind") == "AI_SPATIAL")
    assert spatial["status"] == "NOT_VALIDATED"
    assert spatial.get("artifact_id") in {None, ""}
    layers = client.get("/api/v1/catalog/layers", params={"city_id": "dhaka"})
    catalog = {row["id"]: row for row in layers.json()["layers"]}
    assert catalog["ai_spatial"]["data_status"] == "UNAVAILABLE"
    assert catalog["rainfall"]["data_status"] == "DEMO"
    assert catalog["population"]["data_status"] == "DEMO"
    assert catalog["water_level"]["data_status"] == "DEMO"


def test_demo_never_live_and_alerts_reject_gauge_metrics(monkeypatch):
    client = _client(monkeypatch)
    river = client.get("/api/v1/rivers/buriganga/state", headers=HEADERS).json()
    assert river["provenance"]["data_status"] != "LIVE"
    assert river["provenance"]["freshness"] != "LIVE"
    assert river["current"]["water_level_m"] is not None
    created = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "water_level", "threshold": 4.0},
        headers={"Authorization": "Bearer demo.general"},
    )
    assert created.status_code == 400
    detail = created.json()["detail"]
    assert detail["error_code"] == "METRIC_UNAVAILABLE"
