"""Phase 7.2 River Intelligence contracts. No fabricated gauges, arrival times, or flow direction."""

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.rivers import compute_rate_of_change
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Authorization": "Bearer demo.emergency"}


def _client():
    reset_repository()
    return TestClient(app)


def test_river_search_buriganga_empty_and_unknown():
    client = _client()
    hits = client.get("/api/v1/rivers/search", params={"q": "Buriganga", "city_id": "dhaka"}, headers=HEADERS)
    assert hits.status_code == 200
    body = hits.json()
    assert body["results"]
    assert any(row["kind"] == "river" and row["id"] == "buriganga" for row in body["results"])
    assert any(row["kind"] == "segment" and row["id"] == "buriganga-up" for row in body["results"])
    assert body["basin"]["available"] is False
    assert body["provenance"]["data_status"] in {"DEMO", "UNAVAILABLE"}
    empty = client.get("/api/v1/rivers/search", params={"q": "   ", "city_id": "dhaka"}, headers=HEADERS)
    assert empty.status_code == 400
    unknown = client.get(
        "/api/v1/rivers/search",
        params={"q": "zzzz-not-a-river", "city_id": "dhaka"},
        headers=HEADERS,
    )
    assert unknown.status_code == 200
    assert unknown.json()["results"] == []
    study = client.get("/api/v1/rivers/search", params={"q": "Dhaka"}, headers=HEADERS)
    assert study.status_code == 200
    assert any(row["kind"] == "study_region" for row in study.json()["results"])


def test_river_overview_and_segment_selection():
    client = _client()
    listed = client.get("/api/v1/rivers", params={"city_id": "dhaka", "limit": 80}, headers=HEADERS)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["limit"] <= 80
    assert len(payload["data"]) <= payload["limit"]
    assert payload["flow_direction_status"] == "UNAVAILABLE / TOPOLOGY ONLY"
    assert payload["kind"] == "NETWORK TOPOLOGY"
    assert payload["provenance"]["data_status"] == "DEMO"
    overview = client.get("/api/v1/rivers/buriganga/overview", headers=HEADERS)
    assert overview.status_code == 200
    body = overview.json()
    assert body["river"]["id"] == "buriganga"
    assert body["segment_count"] >= 2
    assert body["geometry_available"] is True
    assert body["observation_status"] == "UNAVAILABLE"
    assert body["forecast_status"] == "UNAVAILABLE"
    assert body["flow_direction_status"] == "UNAVAILABLE / TOPOLOGY ONLY"
    assert body["hydrological_propagation"] == "NOT_COMPUTED"
    assert body["estimated_arrival_time"] is None
    assert all(row["kind"] == "STUDY REGION" for row in body["study_regions"])
    detail = client.get("/api/v1/rivers/buriganga/segments/buriganga-up", headers=HEADERS)
    assert detail.status_code == 200
    segment = detail.json()
    assert segment["segment"]["id"] == "buriganga-up"
    assert segment["water_level_m"] is None
    assert segment["discharge_m3s"] is None
    assert segment["estimated_arrival_time"] is None
    missing = client.get("/api/v1/rivers/not-a-river/overview", headers=HEADERS)
    assert missing.status_code == 404


def test_upstream_downstream_neighbors_and_graph():
    client = _client()
    neighbors = client.get(
        "/api/v1/rivers/buriganga/segments/buriganga-up/neighbors",
        headers=HEADERS,
    )
    assert neighbors.status_code == 200
    body = neighbors.json()
    assert body["kind"] == "NETWORK TOPOLOGY"
    assert body["flow_direction_verified"] is False
    assert body["hydrological_propagation"] == "NOT_COMPUTED"
    assert body["estimated_arrival_time"] is None
    assert any(row["id"] == "buriganga-mid" for row in body["downstream"])
    assert any(row["id"] == "buriganga-mid" for row in body["reachable_downstream"])
    assert body["limit"] <= 50
    graph = client.get("/api/v1/rivers/buriganga/graph")
    assert graph.status_code == 200
    gbody = graph.json()
    assert "edges" in gbody
    assert gbody["flow_direction_verified"] is False
    assert gbody["flow_direction_status"] == "UNAVAILABLE / TOPOLOGY ONLY"
    assert len(gbody["edges"]) <= gbody["limit"] <= 80
    missing_seg = client.get(
        "/api/v1/rivers/buriganga/segments/no-such-segment/neighbors",
        headers=HEADERS,
    )
    assert missing_seg.status_code == 404


def test_observations_unavailable_not_zero():
    client = _client()
    obs = client.get("/api/v1/rivers/buriganga/observations", headers=HEADERS)
    assert obs.status_code == 200
    body = obs.json()
    assert body["water_level_status"] == "UNAVAILABLE"
    assert body["discharge_status"] == "UNAVAILABLE"
    assert body["current_water_level_m"] is None
    assert body["current_discharge_m3s"] is None
    assert body["flood_threshold_m"] is None
    assert body["time_to_threshold"] is None
    assert body["estimated_arrival_time"] is None
    assert body["forecast"]["available"] is False
    assert body["rate_of_change_level"]["status"] == "UNAVAILABLE"
    assert body["rate_of_change_level"]["value"] is None
    assert body["current_water_level_m"] != 0
    assert body["current_discharge_m3s"] != 0
    for row in body["observations"]:
        if not row.get("available"):
            assert row.get("water_level_m") is None
            assert row.get("discharge_m3s") is None


def test_rate_of_change_requires_real_series():
    empty = compute_rate_of_change([], "water_level_m")
    assert empty["status"] == "UNAVAILABLE"
    assert empty["value"] is None
    unavailable = compute_rate_of_change(
        [{"available": False, "t": "2026-09-01T00:00:00+00:00", "water_level_m": None}],
        "water_level_m",
    )
    assert unavailable["status"] == "UNAVAILABLE"
    real = compute_rate_of_change(
        [
            {"available": True, "t": "2026-09-01T00:00:00+00:00", "water_level_m": 1.0},
            {"available": True, "t": "2026-09-01T02:00:00+00:00", "water_level_m": 1.5},
        ],
        "water_level_m",
    )
    assert real["status"] == "REAL"
    assert real["value"] == 0.25
    assert real["units"] == "m/h"
    assert real["interval"] == "2.000 h"


def test_bbox_and_invalid_queries_are_bounded():
    client = _client()
    miss = client.get(
        "/api/v1/rivers",
        params={"city_id": "dhaka", "bbox": "0,0,1,1"},
        headers=HEADERS,
    )
    assert miss.status_code == 200
    assert miss.json()["data"] == []
    hit = client.get(
        "/api/v1/rivers",
        params={"city_id": "dhaka", "bbox": "90.3,23.67,90.43,23.73"},
        headers=HEADERS,
    )
    assert hit.status_code == 200
    assert hit.json()["data"]
    bad = client.get("/api/v1/rivers", params={"bbox": "not-a-bbox"}, headers=HEADERS)
    assert bad.status_code == 400
    huge = client.get("/api/v1/rivers", params={"city_id": "dhaka", "limit": 10000}, headers=HEADERS)
    assert huge.status_code == 200
    assert huge.json()["limit"] <= 80
    assert len(huge.json()["data"]) <= 80


def test_frontend_river_workspace_contracts():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    search = (ROOT / "frontend/src/river/RiverSearch.jsx").read_text()
    panel = (ROOT / "frontend/src/river/RiverIntelligencePanel.jsx").read_text()
    graph = (ROOT / "frontend/src/river/RiverTopologyGraph.jsx").read_text()
    series = (ROOT / "frontend/src/river/RiverTimeSeries.jsx").read_text()
    layer = (ROOT / "frontend/src/components/RiverNetworkLayer.jsx").read_text()
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    forecast = (ROOT / "frontend/src/platform/RiverForecastPanel.jsx").read_text()
    assert "RiverSearch" in app_js
    assert "RiverIntelligencePanel" in app_js
    assert "RiverTimeSeries" in app_js
    assert "topologyHighlights" in app_js
    assert 'platformView === "river"' in app_js
    assert 'id: "river"' in shell
    assert 'role="combobox"' in search
    assert "aria-label=\"River search\"" in search
    assert "FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY" in graph
    assert "NETWORK TOPOLOGY" in graph
    assert "HYDROLOGICAL PROPAGATION: NOT_COMPUTED" in panel
    assert "ESTIMATED ARRIVAL TIME: UNAVAILABLE" in panel
    assert "WATER LEVEL:" in panel
    assert "UNAVAILABLE" in panel
    assert "STUDY REGION" in panel
    assert "river_level_delta_m" in panel
    assert "row.available && row[field] != null" in series
    assert "FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY" in layer
    assert "WATER LEVEL: UNAVAILABLE" in layer
    assert "row.available && row.water_level_m != null" in forecast
    assert "water_level_m: 0" not in panel
    assert "discharge_m3s: 0" not in panel
    assert '"normal"' not in panel.lower()
    assert '"stable"' not in panel.lower()


def test_phase72_does_not_enable_spatial_ai_or_touch_solver():
    blobs = [
        (ROOT / "frontend/src/App.jsx").read_text(),
        (ROOT / "frontend/src/river/RiverIntelligencePanel.jsx").read_text(),
        (ROOT / "src/floodlens/application/rivers.py").read_text(),
    ]
    report = ROOT / "docs/PHASE_7_2_RIVER_INTELLIGENCE_REPORT.md"
    if report.exists():
        blobs.append(report.read_text())
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "mark_spatial_validated" not in blob
    client = _client()
    spatial = client.post(
        "/api/v1/forecast/ai-spatial",
        json={"city_id": "dhaka"},
        headers=HEADERS,
    )
    assert spatial.status_code == 200
    job = spatial.json()
    fetched = client.get(f"/api/v1/forecast/ai-spatial/{job['id']}", headers=HEADERS)
    assert fetched.status_code == 200
    body = fetched.json()
    result = body.get("result") or {}
    if body.get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"
