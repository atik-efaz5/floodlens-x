"""Phase 4 API, registry, jobs, and frontend labels."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.forecast import AIModelForecastProvider
from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app
from floodlens.ml.compare import PHYSICS_FOOTNOTE
from floodlens.ml.registry import load_registry, public_status, save_registry

ROOT = Path(__file__).resolve().parents[1]


def _client():
    reset_repository()
    return TestClient(app)


def _auth(role: str = "admin") -> dict:
    return {"Authorization": f"Bearer demo.{role}"}


def test_models_catalog_ai_status_matches_registry():
    client = _client()
    models = client.get("/api/v1/models").json()
    kinds = {m["kind"]: m for m in models["models"]}
    expected = public_status(load_registry())
    assert kinds["AI"]["status"] == expected
    assert kinds["AI"]["accuracy_claim"] is None
    row = client.get("/api/v1/models/ai-forecast").json()
    assert row["status"] == expected
    assert row["accuracy_claim"] is None


def test_ai_forecast_job_never_invents_depth():
    client = _client()
    denied = client.post("/api/v1/forecast/ai", json={"city_id": "dhaka"}, headers=_auth("general"))
    assert denied.status_code == 403
    queued = client.post("/api/v1/forecast/ai", json={"city_id": "dhaka"}, headers=_auth("researcher"))
    assert queued.status_code == 200
    job = queued.json()
    fetched = client.get(f"/api/v1/forecast/ai/{job['id']}", headers=_auth("researcher")).json()
    result = fetched.get("result") or {}
    if fetched.get("status") == "completed":
        assert result.get("model_kind") == "AI"
        assert result.get("overlay") is None
        if result.get("data_status") == "UNAVAILABLE":
            assert result.get("horizons") == []
        else:
            for row in result.get("horizons") or []:
                assert row.get("expected_depth") is None
                assert row.get("artifact_id") in {None, ""}


def test_provider_unvalidated_checkpoint_does_not_change_catalog(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    save_registry(
        {
            "id": "ai-forecast",
            "status": "TRAINED",
            "checkpoint": str(tmp_path / "missing.ckpt.json"),
            "run_id": "local-exp",
            "dataset_version": "phase4.2-v0",
            "accuracy_claim": None,
            "note": "local experiment",
        },
        path=registry_path,
    )
    assert public_status(load_registry(registry_path)) == "NOT_TRAINED"
    payload = AIModelForecastProvider().forecast("dhaka")
    if public_status() != "VALIDATED":
        assert payload["data_status"] == "UNAVAILABLE"
    else:
        assert payload["overlay"] is None
        assert payload.get("expected_depth") is None


def test_historical_events_are_metadata_only():
    client = _client()
    events = client.get("/api/v1/historical-events").json()
    assert events["data"]
    assert all(row["observed_flood_extent"] is None for row in events["data"])
    assert all(row["data_status"] == "UNAVAILABLE" for row in events["data"])
    assert events["provenance"]["data_status"] == "UNAVAILABLE"


def test_research_compare_has_physics_footnote():
    client = _client()
    research = client.get("/api/v1/research/compare", headers=_auth("researcher")).json()
    assert research["ai"]["status"] == public_status()
    assert research["ai"]["accuracy_claim"] is None
    assert research["ranking_claim"] is None
    assert "94%" not in json.dumps(research)
    assert "solver seconds" in research["physics"]["footnote"].lower() or "SWE" in PHYSICS_FOOTNOTE


def test_experiments_and_metrics_routes():
    client = _client()
    denied = client.get("/api/v1/experiments")
    assert denied.status_code == 401
    payload = client.get("/api/v1/experiments", headers=_auth("researcher")).json()
    assert payload["accuracy_claim"] is None
    metrics = client.get("/api/v1/metrics", headers=_auth("researcher")).json()
    assert metrics["accuracy_claim"] is None


def test_frontend_phase4_labels():
    panel = (ROOT / "frontend/src/platform/ForecastPanel.jsx").read_text()
    assert "postAiForecast" in panel
    assert "NOT_TRAINED" in panel
    assert "SWE burst" in panel or "short SWE" in panel
    assert "interval" in panel
    status = (ROOT / "frontend/src/platform/ModelStatusPanel.jsx").read_text()
    assert "no accuracy claim" in status
    assert "NOT_TRAINED" in status
    assert "VALIDATED" in status
    api = (ROOT / "frontend/src/platform/api.js").read_text()
    assert "/api/v1/forecast/ai" in api
