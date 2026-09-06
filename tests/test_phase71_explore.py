"""Phase 7.1 Explore workspace contracts. No fabricated flood products."""

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Authorization": "Bearer demo.emergency"}


def test_explore_frontend_shell_and_url_state():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    search = (ROOT / "frontend/src/components/LocationSearchBar.jsx").read_text()
    flood_map = (ROOT / "frontend/src/components/FloodMap.jsx").read_text()
    osm = (ROOT / "frontend/src/components/OsmInfrastructureLayer.jsx").read_text()
    river = (ROOT / "frontend/src/components/RiverNetworkLayer.jsx").read_text()
    layers = (ROOT / "frontend/src/explore/ExploreLayerManager.jsx").read_text()
    panel = (ROOT / "frontend/src/explore/SelectedAreaPanel.jsx").read_text()
    timeline = (ROOT / "frontend/src/explore/ExploreTimeline.jsx").read_text()
    url_state = (ROOT / "frontend/src/explore/urlState.js").read_text()
    assert "ExploreLayerManager" in app_js
    assert "SelectedAreaPanel" in app_js
    assert "ExploreTimeline" in app_js
    assert "serializeExploreHash" in app_js
    assert "InfraFilterBar" in app_js
    assert 'aria-label="Clear location search"' in search
    assert "region_id" in search
    assert "Invalid coordinates" in search
    assert "UNAVAILABLE" in flood_map
    assert "?? 0" not in flood_map
    assert "ROAD FLOOD IMPACT: NOT_COMPUTED" in osm
    assert "enabledTypes" in osm
    assert "bbox" in osm
    assert "onSelect" in river
    assert "upstream" in river
    assert "UNAVAILABLE" in layers
    assert "rainfall" in layers.lower()
    assert "UNAVAILABLE" in panel
    assert "NOT_COMPUTED" in panel
    assert "DEMO / not spatial AI" in timeline
    assert "T+6" not in timeline
    assert "layers" in url_state and "filter" in url_state and "river" in url_state


def test_explore_unavailable_layers_have_reasons():
    reset_repository()
    client = TestClient(app)
    response = client.get("/api/v1/catalog/layers", params={"city_id": "dhaka"})
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["layers"]}
    for layer_id in ("rainfall", "population", "water_level", "ai_spatial"):
        assert rows[layer_id]["data_status"] == "UNAVAILABLE"
        assert rows[layer_id].get("reason")
    assert rows["terrain"].get("reason")
    assert rows["hospitals"]["data_status"] in {"REAL", "DEMO", "PARTIAL"}
    assert "bridges" in rows
    assert "schools" in rows


def test_explore_search_country_river_region_id():
    reset_repository()
    client = TestClient(app)
    dhaka = client.get("/api/geocode/search", params={"q": "Dhaka"})
    assert dhaka.status_code == 200
    dhaka_hit = dhaka.json()["results"][0]
    assert dhaka_hit["region_id"] == "dhaka"
    river = client.get("/api/geocode/search", params={"q": "Buriganga"})
    assert river.status_code == 200
    assert river.json()["results"][0]["place_type"] == "river"
    country = client.get("/api/geocode/search", params={"q": "Bangladesh"})
    assert country.status_code == 200
    assert country.json()["results"][0]["place_type"] == "country"
    region = client.get("/api/geocode/search", params={"q": "dhaka"})
    assert any(item.get("region_id") == "dhaka" for item in region.json()["results"])
    empty = client.get("/api/geocode/search", params={"q": "Nowhereville"})
    assert empty.status_code == 200
    assert empty.json()["results"] == []


def test_explore_region_geometry_is_study_bounds_not_admin():
    reset_repository()
    client = TestClient(app)
    response = client.get("/api/v1/regions/dhaka", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["geometry"]["type"] == "Polygon"
    assert "not an administrative" in body["note"].lower()
    assert body["bounds"]["west"] < body["bounds"]["east"]
    missing = client.get("/api/v1/regions/not-a-city", headers=HEADERS)
    assert missing.status_code == 404


def test_explore_infrastructure_bbox_and_type_filter():
    reset_repository()
    client = TestClient(app)
    client.post("/api/v1/ingest/osm", params={"city_id": "dhaka"}, headers=HEADERS)
    bbox = client.get(
        "/api/v1/infrastructure",
        params={"city_id": "dhaka", "bbox": "90.3,23.7,90.5,23.9", "limit": 50},
        headers=HEADERS,
    )
    assert bbox.status_code == 200
    payload = bbox.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["limit"] <= 500
    hospitals = client.get(
        "/api/v1/infrastructure",
        params={"city_id": "dhaka", "type": "hospital", "bbox": "90.3,23.7,90.5,23.9", "limit": 50},
        headers=HEADERS,
    )
    assert hospitals.status_code == 200
    for feature in hospitals.json()["features"]:
        assert feature["properties"]["asset_type"] == "hospital"
    provenance = payload.get("provenance") or {}
    assert provenance.get("data_status") in {"REAL", "DEMO", "UNAVAILABLE", "PARTIAL"}


def test_explore_river_segment_details():
    reset_repository()
    client = TestClient(app)
    client.post("/api/v1/ingest/osm", params={"city_id": "dhaka"}, headers=HEADERS)
    rivers = client.get("/api/v1/rivers", params={"city_id": "dhaka"}, headers=HEADERS)
    assert rivers.status_code == 200
    rows = rivers.json().get("data") or []
    assert rows
    river = rows[0]
    segments = river.get("segments") or []
    assert segments
    segment = segments[0]
    detail = client.get(
        f"/api/v1/rivers/{river['id']}/segments/{segment['id']}",
        headers=HEADERS,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["segment"]["id"] == segment["id"]
    assert "upstream" in body and "downstream" in body
    assert body["water_level_m"] is None
    assert body["discharge_m3s"] is None
    assert "UNAVAILABLE" in body["note"]


def test_explore_does_not_enable_spatial_ai_or_touch_solver():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    report = ROOT / "docs/PHASE_7_1_EXPLORE_WORKSPACE_REPORT.md"
    blob = app_js + (report.read_text() if report.exists() else "PHASE 7.1")
    assert "fit_unet" not in blob
    assert "mark_spatial_validated" not in blob
    reset_repository()
    client = TestClient(app)
    spatial = client.post(
        "/api/v1/forecast/ai-spatial",
        json={"city_id": "dhaka"},
        headers=HEADERS,
    )
    assert spatial.status_code == 200
    job = spatial.json()
    fetched = client.get(f"/api/v1/forecast/ai-spatial/{job['id']}", headers=HEADERS)
    result = (fetched.json().get("result") or {}) if fetched.status_code == 200 else {}
    if fetched.json().get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"
