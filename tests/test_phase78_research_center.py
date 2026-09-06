"""Phase 7.8 Research Center. Does not modify the solver or fabricate diagnostics."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from floodlens.application.platform_store import get_platform_store
from floodlens.application.repository import reset_repository
from floodlens.application.research_center import generate_research_report, research_overview
from floodlens.application.research_diagnostics import JACOBIAN_NOTE
from floodlens.application.web_server import app

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = {"Authorization": "Bearer demo.researcher"}
GENERAL = {"Authorization": "Bearer demo.general"}


def _client():
    reset_repository()
    return TestClient(app)


def test_rbac_hides_research_from_general():
    client = _client()
    assert client.get("/api/v1/research/overview").status_code == 401
    assert client.get("/api/v1/research/overview", headers=GENERAL).status_code == 403
    assert client.get("/api/v1/research/overview", headers=RESEARCH).status_code == 200


def test_overview_not_run_until_executed():
    client = _client()
    overview = client.get("/api/v1/research/overview", headers=RESEARCH).json()
    assert overview["status"] == "NOT_RUN"
    assert all(card["status"] == "NOT_RUN" for card in overview["cards"])
    assert overview["physics_vs_ai"]["status"] == "NOT_COMPARABLE"


def test_lake_at_rest_and_conservation_and_cfl():
    client = _client()
    lake = client.get("/api/v1/research/diagnostics/lake_at_rest", headers=RESEARCH)
    assert lake.status_code == 200
    body = lake.json()
    assert "passed" in body
    assert body["status"] in {"PASS", "VALIDATION FAILED"} or str(body["status"]).startswith("FAILED AT STEP")
    assert body["equilibrium_residual"]["norm_definition"]
    assert "Linf" in body["equilibrium_residual"]
    assert body["cfl"]["dt_s"] is not None
    assert "not proof of global stability" in body["cfl"]["note"]
    assert body["conservation"]["mass_initial"] is not None
    assert body["conservation"]["mass_final"] is not None
    assert body["boundary"]["quality_inferred"] == "UNAVAILABLE"
    assert body["data_status"] == "SIMULATED"
    assert body["provenance"]["solver_version"]
    assert body["provenance"]["config_hash"]


def test_parabolic_bowl_api():
    client = _client()
    bowl = client.get("/api/v1/research/diagnostics/parabolic_bowl", headers=RESEARCH)
    assert bowl.status_code == 200
    body = bowl.json()
    assert body["suite"] == "parabolic_bowl"
    assert body["pause_supported"] is False
    assert body["final_state"]["max_depth_m"] is not None


def test_spectral_perturbation_flux_interface_jacobian():
    client = _client()
    spectral = client.get("/api/v1/research/diagnostics/spectral", headers=RESEARCH).json()
    assert "nyquist_energy_ratio" in spectral
    assert spectral["unstable_classified"] is False

    pert = client.post(
        "/api/v1/research/run",
        json={"suite": "perturbation", "amplitude": 1e-12},
        headers=RESEARCH,
    )
    assert pert.status_code == 200
    pbody = pert.json()
    assert pbody["growth_factor"] is not None
    assert "not automatically classified as solver unstable" in pbody["interpretation"].lower()

    flux = client.get("/api/v1/research/diagnostics/flux_source", headers=RESEARCH).json()
    assert flux["maps"]["combined_rhs_hu"]["status"] == "COMPUTED"

    iface = client.get(
        "/api/v1/research/diagnostics/interface_balance",
        params={"i": 4, "j": 4, "direction": "x"},
        headers=RESEARCH,
    ).json()
    assert iface["interface"]["left_state"]
    assert iface["interface"]["reconstructed_left"]

    jac = client.get("/api/v1/research/diagnostics/jacobian", headers=RESEARCH).json()
    assert jac["spectral_radius"] is not None
    assert jac["global_stability_proof"] is False
    assert "NOT BY ITSELF PROOF OF GLOBAL" in (jac.get("methodological_note") or "") + (jac.get("note") or "")
    assert JACOBIAN_NOTE.split()[0] == "LOCAL"


def test_long_term_and_failed_run_is_fail():
    client = _client()
    ok = client.get("/api/v1/research/diagnostics/long_term", headers=RESEARCH)
    assert ok.status_code == 200
    body = ok.json()
    assert body["executed_steps"] >= 1
    assert body["status"] in {"PASS", "VALIDATION FAILED"} or str(body["status"]).startswith("FAILED AT STEP")

    store = get_platform_store()
    store.put_experiment(
        {
            "id": "exp_fail_test",
            "experiment_id": "exp_fail_test",
            "suite": "long_term_stability",
            "passed": False,
            "status": "FAILED AT STEP 40",
            "failed_at_step": 40,
            "timestamp": "2099-01-01T00:00:00+00:00",
        }
    )
    overview = research_overview()
    long_card = next(card for card in overview["cards"] if card["id"] == "long_term_stability")
    assert long_card["status"] == "FAIL"
    report = generate_research_report("exp_fail_test", created_by="demo.researcher")
    assert "FAILED AT STEP 40" in (report["body"].get("conclusion") or "")
    assert report["body"]["conclusion"] != "COMPLETED"
    assert report["live"] is False


def test_unavailable_and_not_run_and_reproducibility_and_ai():
    client = _client()
    inv = client.get("/api/v1/research/inventory", headers=RESEARCH).json()
    assert inv["diagnostics"]
    overview = client.get("/api/v1/research/overview", headers=RESEARCH).json()
    assert any(card["status"] == "NOT_RUN" for card in overview["cards"])
    run = client.post("/api/v1/research/run", json={"suite": "lake_at_rest"}, headers=RESEARCH)
    assert run.status_code == 200
    exp_id = run.json()["experiment_id"]
    fetched = client.get(f"/api/v1/research/experiments/{exp_id}", headers=RESEARCH)
    assert fetched.status_code == 200
    assert fetched.json()["config_hash"] == run.json()["config_hash"]
    listed = client.get("/api/v1/research/experiments", headers=RESEARCH).json()
    assert listed["n"] >= 1
    ai = client.get("/api/v1/research/ai", headers=RESEARCH).json()
    assert ai["spatial_ai"]["status"] == "NOT_VALIDATED"
    assert ai["target_b"]["status"] == "PARTIALLY FEASIBLE"
    assert ai["model_training"] == "NOT AUTHORIZED"
    assert ai["physics_vs_ai"]["status"] == "NOT_COMPARABLE"
    assert ai["uncertainty"]["calibrated"] is False
    report = client.post("/api/v1/research/reports", params={"experiment_id": exp_id}, headers=RESEARCH)
    assert report.status_code == 200
    assert report.json()["kind"] == "research"
    assert report.json()["live"] is False


def test_assistant_research_tools_respect_rbac():
    client = _client()
    denied = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Did the Lake-at-Rest test pass?", "city_id": "dhaka"},
        headers=GENERAL,
    ).json()
    lake_tool = denied.get("tool_results", {}).get("get_lake_at_rest_status")
    assert "get_lake_at_rest_status" in denied.get("authorized_denied", []) or (
        isinstance(lake_tool, dict) and lake_tool.get("authorized") is False
    )
    allowed = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Did the Lake-at-Rest test pass?", "city_id": "dhaka"},
        headers=RESEARCH,
    ).json()
    assert "get_lake_at_rest_status" in allowed["tools_called"]
    nyquist = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Show me the Nyquist energy.", "city_id": "dhaka"},
        headers=RESEARCH,
    ).json()
    assert "get_nyquist_energy" in nyquist["tools_called"]
    radius = client.post(
        "/api/v1/assistant/chat",
        json={"message": "What is the spectral radius?", "city_id": "dhaka"},
        headers=RESEARCH,
    ).json()
    assert "get_spectral_radius" in radius["tools_called"]
    assert "global" in radius["reply"].lower()


def test_frontend_research_center_copy():
    center = (ROOT / "frontend/src/platform/ResearchCenter.jsx").read_text()
    app = (ROOT / "frontend/src/App.jsx").read_text()
    assert "ResearchCenter" in app
    assert "LOCAL JACOBIAN SPECTRAL RADIUS" in center
    assert "FAILED AT STEP" in center
    assert "Generate research report" in center
    assert 'aria-label="Research center"' in center
    assert "UNAVAILABLE" in center


def test_solver_and_spatial_ai_untouched():
    client = _client()
    perf = client.get("/api/v1/models/performance").json()
    assert perf["spatial_ai"]["status"] == "NOT_VALIDATED"
    blob = (ROOT / "src/floodlens/application/research_diagnostics.py").read_text()
    assert "not clipped" in blob.lower()
