"""Phase 7.3 impact / evacuation / shelter / resources. No fabricated operational numbers."""

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Authorization": "Bearer demo.emergency"}
GENERAL = {"Authorization": "Bearer demo.general"}
RESEARCH = {"Authorization": "Bearer demo.researcher"}


def _client():
    reset_repository()
    return TestClient(app)


def test_impact_summary_population_and_categories_unavailable_without_raster():
    client = _client()
    payload = client.get("/api/v1/impact", params={"city_id": "dhaka"}, headers=HEADERS)
    assert payload.status_code == 200
    body = payload.json()
    pop = body["categories"]["population"]
    assert pop["status"] == "UNAVAILABLE"
    assert pop["affected"] is None
    assert "authoritative population" in pop["reason"].lower() or "not ingested" in pop["reason"].lower() or "not currently configured" in pop["reason"].lower()
    assert body["categories"]["agriculture"]["status"] == "UNAVAILABLE"
    assert body["categories"]["buildings"]["status"] == "NOT_COMPUTED"
    assert body["categories"]["hospitals"]["affected"] is None
    assert body["categories"]["hospitals"]["affected"] != 0
    assert body["safety"].startswith("Potential evacuation-risk analysis")
    assert "official evacuation order" in body["safety"].lower()
    assert body["limit"] <= 200
    general = client.get("/api/v1/impact", params={"city_id": "dhaka"}, headers=GENERAL)
    assert general.status_code == 200
    missing = client.get("/api/v1/impact", params={"city_id": "not-a-city"}, headers=HEADERS)
    assert missing.status_code == 404


def test_infrastructure_point_and_line_status():
    client = _client()
    infra = client.get(
        "/api/v1/impact/infrastructure",
        params={"city_id": "dhaka", "category": "hospital", "limit": 200},
        headers=HEADERS,
    )
    assert infra.status_code == 200
    body = infra.json()
    assert body["count"] <= body["limit"] <= 200
    assert body["assets"]
    row = body["assets"][0]
    assert row["impact_status"] in {"EXPOSED", "NOT_EXPOSED", "UNKNOWN", "NOT_COMPUTED"}
    assert row["expected_depth_m"] is None or isinstance(row["expected_depth_m"], float)
    assert row["data_status"] in {"DEMO", "REAL", "PARTIAL", "UNAVAILABLE"}
    roads = client.get(
        "/api/v1/impact/infrastructure",
        params={"city_id": "dhaka", "category": "road"},
        headers=HEADERS,
    ).json()
    if roads["assets"]:
        road = roads["assets"][0]
        assert road["impact_status"] in {"AFFECTED", "NOT_AFFECTED", "UNKNOWN", "NOT_COMPUTED"}
        assert road["road_flood_impact"]["percent_length_flooded"] is None or road["road_flood_impact"]["computed"] is True
        if not road["road_flood_impact"]["computed"]:
            assert road["road_flood_impact"]["percent_length_flooded"] is None
            assert "NOT_COMPUTED" in (road["road_flood_impact"]["reason"] or "")
    huge = client.get(
        "/api/v1/impact/infrastructure",
        params={"city_id": "dhaka", "limit": 10000},
        headers=HEADERS,
    )
    assert huge.json()["limit"] <= 200
    assert len(huge.json()["assets"]) <= 200


def test_shelter_capacity_occupancy_unavailable():
    client = _client()
    payload = client.get("/api/v1/impact/shelters", params={"city_id": "dhaka"}, headers=HEADERS)
    assert payload.status_code == 200
    body = payload.json()
    assert body["capacity_status"] == "UNAVAILABLE"
    assert body["occupancy_status"] == "UNAVAILABLE"
    assert body["accessibility_status"] == "NOT_COMPUTED"
    for row in body["shelters"]:
        assert row["capacity"] is None
        assert row["occupancy"] is None
        assert row["capacity"] != 0
        assert row["occupancy"] != 0
        assert row["suitability"] in {"FAVORABLE", "CAUTION", "EXPOSED", "UNKNOWN"}
        assert "safe" not in (row["suitability_note"] or "").lower() or "not labeled globally safe" in (row["suitability_note"] or "").lower()


def test_evacuation_language_and_routes_not_computed():
    client = _client()
    payload = client.get("/api/v1/impact/evacuation", params={"city_id": "dhaka"}, headers=HEADERS)
    assert payload.status_code == 200
    body = payload.json()
    assert body["kind"] == "POTENTIAL EVACUATION-RISK ANALYSIS"
    assert body["official_evacuation_order"] is False
    assert "Evacuate now" not in body["safety"]
    assert body["routes"]["status"] == "NOT_COMPUTED"
    assert body["road_accessibility"]["travel_time"] is None
    assert body["road_accessibility"]["safe_route"] is None
    assert body["planning_boundary"]["kind"] == "STUDY REGION"


def test_resource_priority_evidence_and_role_permissions():
    client = _client()
    resources = client.get("/api/v1/impact/resources", params={"city_id": "dhaka"}, headers=HEADERS)
    assert resources.status_code == 200
    body = resources.json()
    for item in body["inventory"].values():
        assert item["status"] == "UNAVAILABLE"
        assert item["value"] is None
    assert body["planning_estimates"]["status"] == "UNAVAILABLE"
    assert body["priorities"]
    for row in body["priorities"]:
        assert row["priority"] in {"HIGH", "LOW", "UNKNOWN"}
        assert row["why"]
        assert row["evidence"]
        assert "17 hospitals" not in row["why"]
    forbidden = client.get("/api/v1/impact/resources", params={"city_id": "dhaka"}, headers=GENERAL)
    assert forbidden.status_code == 403
    research = client.get("/api/v1/impact", params={"city_id": "dhaka"}, headers=RESEARCH)
    assert research.status_code == 200


def test_scenario_impact_and_report_integration():
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
        headers=HEADERS,
    )
    assert job.status_code == 200
    job_id = job.json()["id"]
    impact = client.get("/api/v1/impact", params={"city_id": "dhaka", "job_id": job_id}, headers=HEADERS)
    assert impact.status_code == 200
    body = impact.json()
    assert body["scenario"]["job_id"] == job_id
    assert body["scenario"]["label"] == "SCENARIO"
    assert body["categories"]["population"]["affected"] is None
    hospitals = body["categories"]["hospitals"]
    assert hospitals["computation"] == "COMPUTED FROM CURRENT FLOOD OVERLAY"
    assert hospitals["affected"] is not None
    report = client.post("/api/v1/reports", params={"city_id": "dhaka"}, headers=HEADERS)
    assert report.status_code == 200
    inner = report.json()["body"]
    assert inner["population_impact"]["available"] is False
    assert inner["evacuation_planning"]["official_evacuation_order"] is False
    assert inner["shelter_analysis"]["capacity_status"] == "UNAVAILABLE"
    assert inner["data_availability"]["observed_resource_inventory"] == "UNAVAILABLE"


def test_frontend_impact_workspace_contracts():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    summary = (ROOT / "frontend/src/impact/ImpactSummaryPanel.jsx").read_text()
    evac = (ROOT / "frontend/src/impact/EvacuationPanel.jsx").read_text()
    shelter = (ROOT / "frontend/src/impact/ShelterPanel.jsx").read_text()
    resources = (ROOT / "frontend/src/impact/ResourcePlanningPanel.jsx").read_text()
    osm = (ROOT / "frontend/src/components/OsmInfrastructureLayer.jsx").read_text()
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    assert "ImpactSummaryPanel" in app_js
    assert "ShelterPanel" in app_js
    assert "EvacuationPanel" in app_js
    assert "ResourcePlanningPanel" in app_js
    assert "ImpactEvidence" in app_js
    assert "POPULATION EXPOSURE: UNAVAILABLE" in summary
    assert "No authoritative population dataset" in summary
    assert "Potential evacuation-risk analysis" in evac
    assert "Not an official evacuation order" in evac
    assert "Evacuate now" not in evac
    assert "CAPACITY" in shelter
    assert "OCCUPANCY" in shelter
    assert "OBSERVED RESOURCE INVENTORY" in resources
    assert "EXPECTED DEPTH" in osm
    assert "ROAD FLOOD IMPACT" in osm
    assert 'id: "impact"' in shell
    blob = summary + evac + shelter + resources
    assert "Evacuate now" not in blob
    assert "official evacuation order" in evac.lower()


def test_phase73_does_not_enable_spatial_ai_or_touch_solver():
    blobs = [
        (ROOT / "frontend/src/App.jsx").read_text(),
        (ROOT / "src/floodlens/application/impact_workspace.py").read_text(),
    ]
    report = ROOT / "docs/PHASE_7_3_IMPACT_EVACUATION_REPORT.md"
    if report.exists():
        blobs.append(report.read_text())
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "mark_spatial_validated" not in blob
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
