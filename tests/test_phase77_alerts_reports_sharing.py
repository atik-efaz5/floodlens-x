"""Phase 7.7 saved locations, alerts, reports, and sharing.

Does not train models, enable spatial AI, or modify the solver.
UNAVAILABLE is never coerced to 0 or FALSE.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.alerts import evaluate_alert
from floodlens.application.platform_store import get_platform_store
from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
GENERAL = {"Authorization": "Bearer demo.general"}
EMERGENCY = {"Authorization": "Bearer demo.emergency"}
RESEARCH = {"Authorization": "Bearer demo.researcher"}
ADMIN = {"Authorization": "Bearer demo.admin"}


def _client():
    reset_repository()
    return TestClient(app)


def test_saved_locations_crud_restore_and_authorization():
    client = _client()
    created = client.post(
        "/api/v1/locations",
        json={
            "name": "Dhaka home",
            "location_type": "city",
            "city_id": "dhaka",
            "latitude": 23.81,
            "longitude": 90.41,
            "zoom": 12,
            "layers": ["rivers", "forecast"],
        },
        headers=GENERAL,
    )
    assert created.status_code == 200
    loc = created.json()
    assert loc["owner"] == "demo.general"
    assert loc["user_id"] == "demo.general"
    location_id = loc["id"]

    listed = client.get("/api/v1/locations", headers=GENERAL)
    assert listed.status_code == 200
    cards = listed.json()["cards"]
    assert any(row["location_id"] == location_id for row in cards)
    card = next(row for row in cards if row["location_id"] == location_id)
    assert card["name"] == "Dhaka home"
    assert card["risk"] in {"LOW", "MODERATE", "HIGH", "CRITICAL", "UNAVAILABLE"}
    assert card["data_freshness"] != "LIVE"

    renamed = client.patch(
        f"/api/v1/locations/{location_id}",
        json={"name": "Dhaka HQ"},
        headers=GENERAL,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Dhaka HQ"

    restore = client.get(f"/api/v1/locations/{location_id}/restore", headers=GENERAL)
    assert restore.status_code == 200
    ctx = restore.json()
    assert ctx["city_id"] == "dhaka"
    assert ctx["latitude"] == 23.81
    assert ctx["zoom"] == 12
    assert "risk" not in ctx
    assert "flood_probability" not in ctx
    assert "stale result" in ctx["note"].lower() or "live data" in ctx["note"].lower()

    other = client.get(f"/api/v1/locations/{location_id}", headers=EMERGENCY)
    assert other.status_code == 403

    spoof = client.post(
        "/api/v1/places",
        json={
            "label": "Spoofed",
            "city_id": "dhaka",
            "lon": 90.4,
            "lat": 23.8,
            "user_id": "someone-else",
        },
        headers=GENERAL,
    )
    assert spoof.status_code == 200
    assert spoof.json()["owner"] == "demo.general"

    deleted = client.delete(f"/api/v1/locations/{location_id}", headers=GENERAL)
    assert deleted.status_code == 200
    missing = client.get(f"/api/v1/locations/{location_id}", headers=GENERAL)
    assert missing.status_code == 404


def test_alerts_validation_unavailable_metrics_and_permissions():
    client = _client()
    ok = client.post(
        "/api/v1/alerts",
        json={
            "city_id": "dhaka",
            "metric": "flood_probability",
            "condition": "flood_probability",
            "operator": "gte",
            "threshold": 0.7,
            "channel": "in-app",
            "kind": "personal",
            "user_id": "attacker",
        },
        headers=GENERAL,
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["owner"] == "demo.general"
    assert body["state"] == "ARMED"
    assert body["channel"] == "in-app"

    water = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "water_level", "threshold": 4.0},
        headers=GENERAL,
    )
    assert water.status_code == 400
    detail = water.json()["detail"]
    assert detail["error_code"] == "METRIC_UNAVAILABLE"
    assert "UNAVAILABLE" in detail["reason"]

    river = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "river_level", "threshold": 1.0},
        headers=GENERAL,
    )
    assert river.status_code == 400

    population = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "population", "threshold": 0},
        headers=GENERAL,
    )
    assert population.status_code == 400

    nan = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": "NaN"},
        headers=GENERAL,
    )
    assert nan.status_code == 400
    inf = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": "inf"},
        headers=GENERAL,
    )
    assert inf.status_code == 400

    system = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.9, "kind": "system"},
        headers=GENERAL,
    )
    assert system.status_code == 400
    researcher_system = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.9, "kind": "system"},
        headers=RESEARCH,
    )
    assert researcher_system.status_code == 400
    admin_system = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.9, "kind": "system"},
        headers=ADMIN,
    )
    assert admin_system.status_code == 200

    email = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.5, "channel": "email"},
        headers=GENERAL,
    )
    assert email.status_code == 400

    metrics = client.get("/api/v1/alerts/metrics", params={"city_id": "dhaka"}, headers=GENERAL)
    assert metrics.status_code == 200
    by_id = {row["metric"]: row for row in metrics.json()["metrics"]}
    assert by_id["river_level"]["available"] is False
    assert by_id["water_level"]["supported"] is False
    assert by_id["population"]["available"] is False
    assert "in-app" in metrics.json()["channels"]["implemented"]
    assert "email" in metrics.json()["channels"]["prepared_not_implemented"]


def test_alert_state_machine_dedup_and_history():
    client = _client()
    created = client.post(
        "/api/v1/alerts",
        json={"city_id": "dhaka", "condition": "flood_probability", "threshold": 0.01, "operator": "gte"},
        headers=GENERAL,
    )
    assert created.status_code == 200
    alert_id = created.json()["id"]

    first = client.get("/api/v1/alerts/evaluate", params={"city_id": "dhaka"}, headers=GENERAL)
    assert first.status_code == 200
    fired = first.json()["fired"]
    assert any(row["id"] == alert_id for row in fired)
    row = next(item for item in first.json()["evaluations"] if item["id"] == alert_id)
    assert row["condition_status"] in {"CURRENTLY_TRUE", "STALE"}
    assert row["state"] == "TRIGGERED"
    assert "threshold" in (row.get("message") or "").lower()
    assert "not a declaration" in (row.get("message") or "").lower()
    assert "not an official evacuation order" in (row.get("message") or "").lower()

    second = client.get("/api/v1/alerts/evaluate", params={"city_id": "dhaka"}, headers=GENERAL)
    assert second.status_code == 200
    assert not any(row["id"] == alert_id for row in second.json()["fired"])

    ack = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=GENERAL)
    assert ack.status_code == 200
    assert ack.json()["state"] == "ACKNOWLEDGED"

    history = client.get(f"/api/v1/alerts/{alert_id}/history", headers=GENERAL)
    assert history.status_code == 200
    events = history.json()["history"]
    assert events
    for event in events:
        if event.get("actual_value") is None:
            assert event.get("actual_value_display") == "UNAVAILABLE"

    store = get_platform_store()
    ghost = store.put_alert(
        {
            "owner": "demo.general",
            "city_id": "dhaka",
            "metric": "river_level",
            "condition": "river_level",
            "operator": "gte",
            "threshold": 1.0,
            "state": "ARMED",
            "active": True,
        }
    )
    evaluation = evaluate_alert(ghost)
    assert evaluation["condition_status"] == "UNAVAILABLE"
    assert evaluation["state"] == "ARMED"
    assert evaluation["actual_value"] is None
    assert evaluation["actual_value_status"] == "UNAVAILABLE"


def test_unavailable_metric_is_not_classified_false():
    store = get_platform_store()
    store.reset()
    alert = {
        "id": "alert_ghost",
        "owner": "demo.general",
        "city_id": "dhaka",
        "metric": "population",
        "condition": "population",
        "operator": "gt",
        "threshold": 0,
        "state": "ARMED",
        "active": True,
    }
    row = evaluate_alert(alert)
    assert row["condition_status"] == "UNAVAILABLE"
    assert row["condition_status"] != "CURRENTLY_FALSE"
    assert row["state"] == "ARMED"


def test_reports_are_immutable_snapshots_with_nulls_and_exports():
    client = _client()
    report = client.post(
        "/api/v1/reports",
        params={"city_id": "dhaka"},
        json={"map_state": {"city_id": "dhaka", "zoom": 11, "layers": ["rivers"]}},
        headers=GENERAL,
    )
    assert report.status_code == 200
    payload = report.json()
    assert payload["live"] is False
    assert payload["immutable"] is True
    assert payload["snapshot_time"]
    assert "SNAPSHOT GENERATED AT" in payload["banner"]
    body = payload["body"]
    assert body["population_impact"]["population_exposed"] is None
    assert body["population_impact"]["available"] is False
    assert body["river_conditions"]["current_water_level_m"] is None
    assert body["river_conditions"]["water_level_status"] == "UNAVAILABLE"
    assert body["model_information"]["ai_flood_model"] is None
    assert body["scenario"]["modified_variables"]["river_level_applied_to_solver"] is False
    assert payload["map_state"]["zoom"] == 11
    assert payload["kind"] in {"region", "scenario"}

    fetched = client.get(f"/api/v1/reports/{payload['id']}", headers=GENERAL)
    assert fetched.status_code == 200
    assert fetched.json()["live"] is False
    assert fetched.json()["body"]["population_impact"]["population_exposed"] is None

    csv_text = client.get(f"/api/v1/reports/{payload['id']}", params={"format": "csv"}, headers=GENERAL)
    assert csv_text.status_code == 200
    assert "body.population_impact.population_exposed,,UNAVAILABLE" in csv_text.text
    assert "body.population_impact.population_exposed,0" not in csv_text.text
    assert "body.river_conditions.current_water_level_m,,UNAVAILABLE" in csv_text.text

    pdf = client.get(f"/api/v1/reports/{payload['id']}", params={"format": "pdf"}, headers=GENERAL)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert b"SNAPSHOT GENERATED AT" in pdf.content
    assert b"UNAVAILABLE" in pdf.content
    assert b"STORED ONLY / NOT APPLIED" in pdf.content

    historical = client.post(
        "/api/v1/reports",
        params={"city_id": "dhaka", "event_id": "evt:2015-07-11"},
        headers=GENERAL,
    )
    assert historical.status_code == 200
    hist = historical.json()
    assert hist["kind"] == "historical"
    assert hist["live"] is False
    assert hist["body"].get("forecast_accuracy") is None
    assert hist["body"].get("forecast_accuracy_omitted") is True


def test_sharing_snapshot_revoke_and_provenance():
    client = _client()
    report = client.post("/api/v1/reports", params={"city_id": "dhaka"}, headers=GENERAL)
    assert report.status_code == 200
    report_id = report.json()["id"]
    original_category = report.json()["body"]["current_conditions"]["category"]

    private = client.post(f"/api/v1/shares/{report_id}", params={"visibility": "private"}, headers=GENERAL)
    assert private.status_code == 200
    share = private.json()
    assert share["live"] is False
    assert share["banner"].startswith("Analysis generated at ")
    assert "historical snapshot" in share["banner"].lower()
    assert share["model_version"]
    assert share["dataset_version"]

    opened = client.get(f"/api/v1/shares/{share['id']}", headers=GENERAL)
    assert opened.status_code == 200
    view = opened.json()
    assert view["available"] is True
    assert view["live"] is False
    assert view["status"] == "SHARED SNAPSHOT"
    assert "Current live data may differ" in view["stale_notice"]
    assert view["snapshot"]["body"]["population_impact"]["population_exposed"] is None

    store = get_platform_store()
    store.reports[report_id]["body"]["current_conditions"]["category"] = "FABRICATED"
    frozen = client.get(f"/api/v1/shares/{share['id']}", headers=GENERAL).json()
    assert frozen["snapshot"]["body"]["current_conditions"]["category"] == original_category
    assert frozen["live"] is False

    other = client.get(f"/api/v1/shares/{share['id']}", headers=EMERGENCY)
    assert other.status_code == 404

    public = client.post(f"/api/v1/shares/{report_id}", params={"visibility": "public"}, headers=GENERAL)
    assert public.status_code == 200
    anon = client.get(f"/api/v1/shares/{public.json()['id']}")
    assert anon.status_code == 200
    assert anon.json()["live"] is False

    revoked = client.post(f"/api/v1/shares/{share['id']}/revoke", headers=GENERAL)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "SHARE UNAVAILABLE"
    denied = client.get(f"/api/v1/shares/{share['id']}", headers=GENERAL)
    assert denied.status_code == 404
    assert denied.json()["detail"]["error_code"] == "SHARE_UNAVAILABLE"
    assert report_id in store.reports


def test_assistant_report_and_share_do_not_invent_numbers():
    client = _client()
    report = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Generate a report from this analysis.", "city_id": "dhaka"},
        headers=GENERAL,
    )
    assert report.status_code == 200
    payload = report.json()
    assert "generate_report" in payload["tools_called"]
    generated = payload["tool_results"]["generate_report"]
    assert generated["live"] is False
    assert generated["body"]["population_impact"]["population_exposed"] is None

    share = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Share this analysis.", "city_id": "dhaka"},
        headers=GENERAL,
    )
    assert share.status_code == 200
    assert "share_analysis" in share.json()["tools_called"]
    shared = share.json()["tool_results"]["share_analysis"]
    assert shared["live"] is False
    assert shared.get("share_id")


def test_spatial_ai_and_scientific_status_remain_frozen():
    client = _client()
    spatial = client.post("/api/v1/forecast/ai-spatial", json={"city_id": "dhaka"}, headers=EMERGENCY)
    assert spatial.status_code == 200
    job = client.get(f"/api/v1/forecast/ai-spatial/{spatial.json()['id']}", headers=EMERGENCY)
    assert job.status_code == 200
    body_job = job.json()
    result = body_job.get("result") or {}
    if body_job.get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"
    perf = client.get("/api/v1/models/performance").json()
    assert perf["spatial_ai"]["status"] == "NOT_VALIDATED"
    assert perf["spatial_ai"]["metrics"] is None
    health = client.get("/api/v1/health").json()
    assert health["models"]["ai_flood"] is None


def test_frontend_panels_preserve_unavailable_and_snapshot_copy():
    alerts = (ROOT / "frontend/src/platform/AlertsPanel.jsx").read_text()
    locations = (ROOT / "frontend/src/platform/LocationsPanel.jsx").read_text()
    reports = (ROOT / "frontend/src/platform/ReportsPanel.jsx").read_text()
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    app = (ROOT / "frontend/src/App.jsx").read_text()
    assert "METRIC UNAVAILABLE" in alerts
    assert "not a declaration that a flood is happening" in alerts
    assert "aria-label=\"Create alert\"" in alerts
    assert "aria-label=\"Alert threshold\"" in alerts
    assert "My locations" in locations
    assert "Confirm delete" in locations
    assert "role=\"alertdialog\"" in locations
    assert "SNAPSHOT GENERATED AT" in reports
    assert "SHARE UNAVAILABLE" in reports
    assert "historical snapshot" in reports
    assert "LocationsPanel" in app
    assert "handleRestoreLocation" in app
    assert 'id: "locations"' in shell
    assistant = (ROOT / "frontend/src/platform/AssistantDock.jsx").read_text()
    assert "Share this analysis" in assistant
    assert "share_analysis" in assistant
