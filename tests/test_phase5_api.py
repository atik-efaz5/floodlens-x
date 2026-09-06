"""Phase 5 catalog, spatial UNAVAILABLE, 6h/12h, physics non-comparability."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app
from floodlens.ml.compare import COMPARISON_NOT_YET_COMPARABLE, PHYSICS_FOOTNOTE
from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.inference import SpatialForecastProvider
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

ROOT = Path(__file__).resolve().parents[1]


def _client():
    reset_repository()
    return TestClient(app)


def _auth(role: str = "admin") -> dict:
    return {"Authorization": f"Bearer demo.{role}"}


def test_catalog_has_two_ai_rows_spatial_not_trained():
    client = _client()
    models = client.get("/api/v1/models").json()
    by_id = {m["id"]: m for m in models["models"]}
    assert by_id["ai-forecast"]["status"] == public_status(load_registry())
    assert by_id["ai-forecast"]["label_kind"] == "MODELLED"
    spatial = by_id["ai-spatial-forecast"]
    assert spatial["status"] == public_spatial_status(load_spatial_registry())
    assert spatial["status"] == "NOT_TRAINED"
    assert spatial.get("display_status") in {"NOT_TRAINED", "TRAINED — NOT VALIDATED"}
    assert spatial["kind"] == "AI_SPATIAL"
    assert spatial["accuracy_claim"] is None
    row = client.get("/api/v1/models/ai-spatial-forecast").json()
    assert row["status"] == "NOT_TRAINED"
    assert row.get("comparable_to_physics") is False


def test_spatial_forecast_unavailable_until_validated():
    payload = SpatialForecastProvider().forecast("sunamganj")
    assert payload["available"] is False
    assert payload["data_status"] == "UNAVAILABLE"
    assert payload["overlay"] is None
    assert payload.get("catalog_status") == "NOT_VALIDATED"
    client = _client()
    queued = client.post(
        "/api/v1/forecast/ai-spatial",
        json={"city_id": "sunamganj"},
        headers=_auth("researcher"),
    )
    assert queued.status_code == 200
    job = queued.json()
    fetched = client.get(f"/api/v1/forecast/ai-spatial/{job['id']}", headers=_auth("researcher")).json()
    result = fetched.get("result") or {}
    if fetched.get("status") == "completed":
        assert result.get("available") is False
        assert result.get("data_status") == "UNAVAILABLE"


def test_aoi_ai_still_has_no_overlay_and_subdaily_unavailable():
    client = _client()
    queued = client.post("/api/v1/forecast/ai", json={"city_id": "dhaka"}, headers=_auth("researcher"))
    assert queued.status_code == 200
    job = queued.json()
    fetched = client.get(f"/api/v1/forecast/ai/{job['id']}", headers=_auth("researcher")).json()
    result = fetched.get("result") or {}
    if fetched.get("status") == "completed" and result.get("available"):
        assert result.get("overlay") is None
        for row in result.get("horizons") or []:
            assert row.get("expected_depth") is None
            if row.get("horizon_hours") in {6, 12}:
                assert row.get("available") is False
                assert row.get("data_status") == "UNAVAILABLE"


def test_research_compare_not_yet_comparable():
    client = _client()
    research = client.get("/api/v1/research/compare", headers=_auth("researcher")).json()
    assert research["ai"]["status"] == public_status()
    assert research["ai_spatial"]["status"] == public_spatial_status()
    assert research["comparable_to_physics"] is False
    assert research["comparison_status"] == "COMPARISON NOT YET COMPARABLE"
    blob = json.dumps(research)
    assert "94%" not in blob
    assert "COMPARISON NOT YET COMPARABLE" in blob
    assert "solver seconds" in research["physics"]["footnote"].lower() or "SWE" in PHYSICS_FOOTNOTE
    assert "inundation" in COMPARISON_NOT_YET_COMPARABLE.lower()


def test_frontend_spatial_overlay_hook():
    panel = (ROOT / "frontend/src/platform/ForecastPanel.jsx").read_text()
    assert "postAiSpatialForecast" in panel
    assert "artifact_id" in panel
    assert "COMPARISON NOT YET COMPARABLE" in panel
    api = (ROOT / "frontend/src/platform/api.js").read_text()
    assert "/api/v1/forecast/ai-spatial" in api
    status = (ROOT / "frontend/src/platform/ModelStatusPanel.jsx").read_text()
    assert "do not inherit VALIDATED" in status or "does not inherit" in status


def test_data_cards_and_probe_docs_exist():
    assert (ROOT / "docs/data_cards/GFM.md").exists()
    assert (ROOT / "docs/data_cards/GFM_SPATIAL.md").exists()
    assert (ROOT / "docs/data_cards/SPATIAL_FLOOD_DATASET_V2.md").exists()
    assert (ROOT / "docs/model_cards/SPATIAL_AI_FLOOD_v0.1.md").exists()
    assert (ROOT / "docs/model_cards/SPATIAL_AI_FLOOD_V2.md").exists()
    assert (ROOT / "docs/PHASE55_VALIDATION.md").exists()
    assert (ROOT / "docs/PHASE6_FORMULATION.md").exists()
    assert (ROOT / "docs/PHASE_6_5_DATASET_EXPANSION_PLAN.md").exists()
    phase65 = (ROOT / "docs/PHASE_6_5_DATASET_EXPANSION_PLAN.md").read_text()
    assert "Decision: E" in phase65
    assert "NOT_VALIDATED" in phase65
    assert "src/floodlens/numerical" in phase65
    assert (ROOT / "docs/data_cards/BD_INUNDATION_HISTORY.md").exists()
    assert (ROOT / "docs/model_cards/AI_SPATIAL_OCCURRENCE_v0.1.md").exists()
    assert (ROOT / "docs/PHASE5_DATA_INVENTORY.md").exists()
    gfm = (ROOT / "docs/data_cards/GFM.md").read_text()
    assert "OBSERVED" in gfm
    assert "proprietary" in gfm.lower()
    derived = (ROOT / "docs/data_cards/BD_INUNDATION_HISTORY.md").read_text()
    assert "DERIVED" in derived
    assert "not downloaded" in derived.lower() or "Not downloaded" in derived
