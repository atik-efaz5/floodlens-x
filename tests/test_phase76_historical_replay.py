"""Phase 7.6 historical replay, compatibility, and model audit."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from floodlens.application.historical_workspace import (
    check_compatibility,
    classify_difference,
    compare_binary_maps,
    compare_event,
    event_catalog,
    event_detail,
    event_observations,
    semantic_type_of_job,
    timing_error,
    CLASS_FN,
    CLASS_FP,
    CLASS_TN,
    CLASS_TP,
    CLASS_UNKNOWN,
    SEMANTIC_FORECAST,
    SEMANTIC_OBSERVATION,
    SEMANTIC_SCENARIO,
    SEMANTIC_SIMULATION,
    TARGET_BINARY_EXTENT,
)
from floodlens.application.repository import reset_repository
from floodlens.application.web_server import app

GENERAL = {"Authorization": "Bearer demo.general"}
EMERGENCY = {"Authorization": "Bearer demo.emergency"}


def _client():
    reset_repository()
    return TestClient(app)


def test_event_catalog_uses_gfm_ids_not_invented_names():
    catalog = event_catalog()
    gfm = [row for row in catalog["data"] if row.get("catalog_family") == "GFM"]
    assert gfm
    row = next(item for item in gfm if item["event_id"] == "evt:2015-07-11")
    assert row["name"] is None
    assert row["label"] == "evt:2015-07-11"
    assert row["start"] == "2015-07-11"
    assert row["peak"] == "2015-07-16"
    assert row["end"] == "2015-08-09"
    assert "sunamganj" in row["regions"]
    assert row["flood_mechanism"]
    assert row["observation_source"]
    assert row["n_observations"] >= 1
    assert row["observed_flood_extent"] is None
    assert row["semantic_type"] == SEMANTIC_OBSERVATION


def test_catalog_filters_year_and_region():
    catalog = event_catalog(year=2015, region="sunamganj")
    assert catalog["data"]
    assert all("2015" in str(row.get("start")) for row in catalog["data"])
    assert all("sunamganj" in (row.get("regions") or []) for row in catalog["data"])


def test_event_selection_and_actual_timestamps():
    detail = event_detail("evt:2015-07-11")
    stamps = [row["timestamp"] for row in detail["timeline"] if row.get("timestamp")]
    assert stamps
    assert all("T-72" not in str(stamp) and "T-48" not in str(stamp) for stamp in stamps)
    assert any(str(stamp).startswith("2015-") for stamp in stamps)
    joined = " ".join(stamps)
    assert "T-24h" not in joined


def test_observation_only_replay_comparison_unavailable():
    compare = compare_event("evt:2015-07-11")
    assert compare["comparison"] in {"UNAVAILABLE", "NOT_COMPARABLE"}
    assert compare.get("metrics") is None
    obs = event_observations("evt:2015-07-11")
    assert obs["n"] >= 1
    assert all(row["semantic_type"] == SEMANTIC_OBSERVATION for row in obs["observations"])


def test_unknown_mask_preserved_in_binary_compare():
    predicted = np.array([[1, 1], [0, 0]], dtype=np.float64)
    observed = np.array([[1, CLASS_UNKNOWN], [0, 0]], dtype=np.float64)
    result = compare_binary_maps(predicted, observed)
    assert result["comparable"] is True
    metrics = result["metrics"]
    assert metrics["n_unknown_unscored"] >= 1
    assert metrics["tp"] + metrics["fp"] + metrics["fn"] + metrics["tn"] == metrics["n_jointly_valid"]
    classes = result["difference_classes"]["array"]
    assert classes[0, 1] == CLASS_UNKNOWN


def test_semantic_type_scenario_never_forecast():
    assert semantic_type_of_job({"kind": "scenario"}) == SEMANTIC_SCENARIO
    assert semantic_type_of_job({"kind": "scenario"}) != SEMANTIC_FORECAST
    assert semantic_type_of_job({"kind": "simulation"}) == SEMANTIC_SIMULATION
    assert semantic_type_of_job({"kind": "physics_forecast"}) == SEMANTIC_SIMULATION


def test_compatible_prediction_and_observation_compare_works():
    predicted = np.array([[1, 0], [1, 0]], dtype=np.float64)
    observed = np.array([[1, 1], [0, 0]], dtype=np.float64)
    result = compare_binary_maps(predicted, observed)
    assert result["comparison"] == "COMPARABLE"
    assert result["metrics"]["tp"] == 1
    assert result["metrics"]["fp"] == 1
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["tn"] == 1
    assert result["metrics"]["accuracy_claim"] is None
    classes = classify_difference(predicted, observed)
    assert classes[0, 0] == CLASS_TP
    assert classes[1, 0] == CLASS_FP
    assert classes[0, 1] == CLASS_FN
    assert classes[1, 1] == CLASS_TN


def test_incompatible_prediction_observation_not_comparable():
    compat = check_compatibility(
        {
            "semantic_type": SEMANTIC_FORECAST,
            "event_id": "evt:2015-07-11",
            "target_definition": TARGET_BINARY_EXTENT,
            "grid_shape": (32, 32),
            "spatial_resolution_m": 20,
            "timestamp": "2015-07-16T12:04:17Z",
            "units": "binary_flood_extent",
        },
        {
            "semantic_type": SEMANTIC_OBSERVATION,
            "event_id": "evt:2015-07-11",
            "target_definition": TARGET_BINARY_EXTENT,
            "grid_shape": (64, 64),
            "spatial_resolution_m": 500,
            "timestamp": "2015-08-09T12:04:18Z",
            "units": "binary_flood_extent",
        },
    )
    assert compat["comparison"] == "NOT_COMPARABLE"
    assert any("grid" in reason or "resolution" in reason for reason in compat["reasons"])


def test_scenario_vs_observation_not_comparable():
    compat = check_compatibility(
        {
            "semantic_type": SEMANTIC_SCENARIO,
            "event_id": "evt:2015-07-11",
            "target_definition": "PHYSICS_WATER_DEPTH_M",
        },
        {
            "semantic_type": SEMANTIC_OBSERVATION,
            "event_id": "evt:2015-07-11",
            "target_definition": TARGET_BINARY_EXTENT,
        },
    )
    assert compat["comparison"] == "NOT_COMPARABLE"
    assert any("SCENARIO" in reason for reason in compat["reasons"])


def test_grid_mismatch_binary_maps():
    result = compare_binary_maps(np.zeros((2, 2)), np.zeros((3, 3)))
    assert result["comparison"] == "NOT_COMPARABLE"
    assert result["metrics"] is None


def test_timing_error_unavailable_without_predictions():
    payload = timing_error(["2015-07-16T12:04:17Z"], [])
    assert payload["status"] == "UNAVAILABLE"
    assert payload["onset_error"] is None


def test_timing_error_states_temporal_resolution():
    payload = timing_error(
        ["2015-07-16T12:04:17Z", "2015-08-09T12:04:18Z"],
        ["2015-07-11T00:00:00Z"],
    )
    assert payload["status"] == "COMPUTED_AT_SCENE_RESOLUTION"
    assert "sparse" in payload["temporal_resolution"].lower() or "scene" in payload["temporal_resolution"].lower()


def test_history_api_catalog_and_compare():
    client = _client()
    catalog = client.get("/api/v1/history/events", headers=GENERAL)
    assert catalog.status_code == 200
    body = catalog.json()
    assert body["n"] >= 1
    event_id = next(row["event_id"] for row in body["data"] if row["catalog_family"] == "GFM")
    detail = client.get(f"/api/v1/history/events/{event_id}", headers=GENERAL).json()
    assert detail["event"]["event_id"] == event_id
    assert "T-72h" not in str(detail["timeline"])
    compare = client.get(f"/api/v1/history/events/{event_id}/compare", headers=GENERAL).json()
    assert compare["comparison"] in {"UNAVAILABLE", "NOT_COMPARABLE"}
    preds = client.get(f"/api/v1/history/events/{event_id}/predictions", headers=GENERAL).json()
    for row in preds["predictions"]:
        if row.get("kind") == "scenario" or row.get("semantic_type") == SEMANTIC_SCENARIO:
            assert row["semantic_type"] != SEMANTIC_FORECAST


def test_emsr_historical_events_endpoint_still_null_extent():
    client = _client()
    events = client.get("/api/v1/historical-events").json()
    assert all(row.get("observed_flood_extent") is None for row in events["data"])


def test_model_registry_and_performance_center():
    client = _client()
    gbdt = client.get("/api/v1/models/ai-forecast").json()
    assert gbdt["task"]
    assert "spatial flood map" not in gbdt["task"].lower()
    assert gbdt["accuracy_claim"] is None
    assert "splits" in gbdt or "split_counts" in gbdt
    spatial = client.get("/api/v1/models/ai-spatial-forecast").json()
    assert spatial["status"] == "NOT_TRAINED"
    assert spatial.get("scientific_status") == "NOT_VALIDATED"
    assert spatial.get("metrics") is None
    perf = client.get("/api/v1/models/performance").json()
    assert perf["accuracy_claim"] is None
    assert "94" not in perf["message"]
    assert perf["spatial_ai"]["status"] == "NOT_VALIDATED"
    assert perf["spatial_ai"]["metrics"] is None
    assert (perf.get("selected") or {}).get("headline", {}).get("statistical_power_limited") is True


def test_historical_report_omits_forecast_accuracy_without_prediction():
    client = _client()
    report = client.post(
        "/api/v1/history/events/evt:2015-07-11/report",
        headers=EMERGENCY,
    )
    assert report.status_code == 200
    body = report.json()["body"]
    assert body.get("forecast_accuracy") is None
    assert body.get("forecast_accuracy_omitted") is True
    assert body["comparison"]["metrics"] is None


def test_assistant_historical_and_performance_tools():
    client = _client()
    happened = client.post(
        "/api/v1/assistant/chat",
        json={
            "message": "What happened during this flood?",
            "city_id": "dhaka",
            "context": {"selected_event_id": "evt:2015-07-11"},
        },
        headers=GENERAL,
    ).json()
    assert "get_historical_event" in happened["tools_called"]
    assert happened["tool_results"]["get_historical_event"]["event_id"] == "evt:2015-07-11"

    perform = client.post(
        "/api/v1/assistant/chat",
        json={"message": "How well did the model perform?", "city_id": "dhaka"},
        headers=GENERAL,
    ).json()
    assert "get_model_performance" in perform["tools_called"]
    assert perform["tool_results"]["get_model_performance"]["accuracy_claim"] is None

    compare = client.post(
        "/api/v1/assistant/chat",
        json={
            "message": "Compare prediction and reality.",
            "city_id": "dhaka",
            "context": {"selected_event_id": "evt:2015-07-11"},
        },
        headers=GENERAL,
    ).json()
    assert "compare_forecast_vs_reality" in compare["tools_called"]
    result = compare["tool_results"]["compare_forecast_vs_reality"]
    assert result["comparison"] in {"UNAVAILABLE", "NOT_COMPARABLE"}
    assert result.get("metrics") is None

    error = client.post(
        "/api/v1/assistant/chat",
        json={
            "message": "What was the biggest error?",
            "city_id": "dhaka",
            "context": {"selected_event_id": "evt:2015-07-11"},
        },
        headers=GENERAL,
    ).json()
    assert "get_error_analysis" in error["tools_called"]
    assert error["tool_results"]["get_error_analysis"]["available"] is False


def test_spatial_ai_status_unchanged():
    client = _client()
    spatial = client.post(
        "/api/v1/assistant/chat",
        json={"message": "spatial AI status", "city_id": "dhaka"},
        headers=GENERAL,
    ).json()
    assert spatial["tool_results"]["get_spatial_ai_status"]["spatial_ai"] == "NOT_VALIDATED"


def test_provenance_present_on_history_payloads():
    client = _client()
    catalog = client.get("/api/v1/history/events", headers=GENERAL).json()
    assert catalog["provenance"]["provider"]
    assert catalog["provenance"]["data_status"]
    detail = client.get("/api/v1/history/events/evt:2015-07-11", headers=GENERAL).json()
    assert detail["provenance"]["dataset"]
    assert "REAL" not in str(detail["event"].get("data_status") or "") or detail["event"]["catalog_family"] == "GFM"
