"""Research Center orchestration: inventory, overview, experiments, AI status, reports."""

from __future__ import annotations

from typing import Optional

from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.rate_limit import check_rate
from floodlens.application.research_diagnostics import (
    diagnostic_inventory,
    long_term_stability,
    run_conservation,
    run_flux_source,
    run_interface_balance,
    run_jacobian,
    run_lake_at_rest,
    run_parabolic_bowl,
    run_perturbation,
    run_spectral,
)
from floodlens.ml.compare import COMPARISON_NOT_YET_COMPARABLE, PHYSICS_FOOTNOTE
from floodlens.ml.registry import public_status
from floodlens.ml.spatial.registry_spatial import public_spatial_status

SUITES = {
    "lake_at_rest": run_lake_at_rest,
    "parabolic_bowl": run_parabolic_bowl,
    "conservation": run_conservation,
    "spectral": run_spectral,
    "perturbation": run_perturbation,
    "flux_source": run_flux_source,
    "interface_balance": run_interface_balance,
    "jacobian": run_jacobian,
    "long_term": long_term_stability,
    "long_term_stability": long_term_stability,
}

CARD_SUITES = (
    "mass_conservation",
    "momentum_residual",
    "equilibrium_residual",
    "cfl",
    "spectral",
    "perturbation",
    "long_term_stability",
)


def _latest_by_suite() -> dict:
    store = get_platform_store()
    latest = {}
    for row in store.experiments.values():
        suite = row.get("suite")
        if not suite:
            continue
        prev = latest.get(suite)
        if prev is None or str(row.get("timestamp") or "") >= str(prev.get("timestamp") or ""):
            latest[suite] = row
    return latest


def _card_status(latest: dict, suite: str, field_ok=None) -> dict:
    row = latest.get(suite)
    if row is None and suite == "mass_conservation":
        row = latest.get("lake_at_rest") or latest.get("conservation")
    if row is None and suite == "momentum_residual":
        row = latest.get("lake_at_rest")
    if row is None and suite == "equilibrium_residual":
        row = latest.get("lake_at_rest")
    if row is None and suite == "cfl":
        row = latest.get("lake_at_rest") or latest.get("parabolic_bowl")
    if row is None:
        return {"id": suite, "status": "NOT_RUN", "value": None, "experiment_id": None}
    status = row.get("status") or "NOT_RUN"
    if row.get("passed") is True:
        card_status = "PASS"
    elif row.get("passed") is False or (isinstance(status, str) and "FAIL" in status):
        card_status = "FAIL"
    elif status in {"COMPUTED"}:
        card_status = "COMPUTED"
    else:
        card_status = status if status in {"PASS", "FAIL", "NOT_RUN", "UNAVAILABLE"} else "FAIL"
    value = None
    if suite == "mass_conservation":
        value = (row.get("conservation") or row.get("mass_conservation") or {}).get("relative_error")
        value = value if value is not None else row.get("mass_relative_error")
    elif suite == "momentum_residual":
        value = row.get("momentum_residual")
    elif suite == "equilibrium_residual":
        value = ((row.get("equilibrium_residual") or {}).get("Linf"))
    elif suite == "cfl":
        value = (row.get("cfl") or {}).get("cfl_max") or row.get("final_state", {}).get("cfl_max")
    elif suite == "spectral":
        value = row.get("nyquist_energy_ratio") or (row.get("spectral") or {}).get("nyquist_energy_ratio")
    elif suite == "perturbation":
        value = row.get("growth_factor")
    elif suite == "long_term_stability":
        value = row.get("executed_steps")
    return {
        "id": suite,
        "status": card_status,
        "value": value,
        "experiment_id": row.get("experiment_id") or row.get("id"),
        "timestamp": row.get("timestamp"),
        "raw_status": status,
    }


def research_overview() -> dict:
    latest = _latest_by_suite()
    lake = latest.get("lake_at_rest")
    return {
        "solver_version": PHYSICS_MODEL_VERSION,
        "experiment_id": (lake or {}).get("experiment_id"),
        "dataset": "synthetic-parabolic-bowl",
        "run_timestamp": (lake or {}).get("timestamp"),
        "status": (lake or {}).get("status") or "NOT_RUN",
        "validation_summary": (lake or {}).get("status") or "NOT_RUN",
        "cards": [_card_status(latest, key) for key in CARD_SUITES],
        "note": "PASS is only shown after that diagnostic has been executed and met its stated criterion.",
        "pause_supported": False,
        "live": False,
        "data_status": "SIMULATED",
        "physics_vs_ai": physics_vs_ai_status(),
    }


def list_research_experiments(limit: int = 30) -> dict:
    store = get_platform_store()
    rows = list(store.experiments.values())
    rows.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    summaries = []
    for row in rows[: max(1, min(int(limit), 50))]:
        summaries.append(
            {
                "experiment_id": row.get("experiment_id") or row.get("id"),
                "suite": row.get("suite"),
                "status": row.get("status"),
                "passed": row.get("passed"),
                "timestamp": row.get("timestamp"),
                "config_hash": row.get("config_hash"),
                "solver_version": row.get("solver_version") or row.get("model_version"),
            }
        )
    return {"experiments": summaries, "n": len(summaries)}


def get_research_experiment(experiment_id: str) -> dict:
    store = get_platform_store()
    row = store.experiments.get(experiment_id)
    if not row:
        raise KeyError(experiment_id)
    return row


def run_suite(suite: str, identity: str, **kwargs) -> dict:
    key = (suite or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key not in SUITES:
        raise KeyError(suite)
    check_rate(identity, "research.run")
    runner = SUITES[key]
    return runner(**kwargs)


def ai_experiment_center() -> dict:
    from floodlens.application.historical_workspace import model_performance_payload
    from floodlens.ml.train import list_experiments

    perf = model_performance_payload()
    spatial = public_spatial_status()
    track_a = public_status()
    experiments = list_experiments()
    return {
        "track_a": {
            "name": "GFM diagnostic baseline",
            "task": "AOI flood-occurrence probability (MODELLED GloFAS Q exceedance), not a flood map",
            "status": track_a,
            "dataset": "AOI GBDT / GFM diagnostic",
            "split": "held-out where documented in the model registry",
            "metrics": None if track_a != "VALIDATED" else "see /api/v1/models/performance",
            "limitations": "Validated only for its specific AOI task.",
            "uncertainty": "not calibrated",
        },
        "target_b": {
            "name": "Target B",
            "task": "forecast-style spatial occurrence",
            "status": "PARTIALLY FEASIBLE",
            "dataset": "partial causal / forecast vintage where documented",
            "split": "UNAVAILABLE as a trained operational model",
            "metrics": None,
            "limitations": "NOT TRAINED. PARTIALLY FEASIBLE only.",
            "uncertainty": "unavailable",
        },
        "spatial_ai": {
            "name": "Spatial AI",
            "task": "spatial flood occurrence map",
            "status": "NOT_VALIDATED",
            "api": "UNAVAILABLE",
            "dataset": None,
            "split": None,
            "metrics": None,
            "limitations": "Not an operational flood map. Does not inherit AOI GBDT VALIDATED.",
            "uncertainty": "unavailable",
            "registry_status": spatial,
        },
        "aoi_gbdt": {
            "name": "AOI GBDT",
            "task": "AOI flood-occurrence probability",
            "status": track_a,
            "limitations": "Validated for AOI task only.",
            "uncertainty": "not calibrated",
        },
        "recorded_training_experiments": len(experiments),
        "accuracy_claim": None,
        "performance": {
            "spatial_ai": (perf.get("spatial_ai") or {}).get("status") or "NOT_VALIDATED",
            "spatial_ai_metrics": (perf.get("spatial_ai") or {}).get("metrics"),
        },
        "uncertainty": {
            "calibrated": False,
            "status": "not calibrated",
            "note": "Performance metrics are not converted into forecast confidence.",
        },
        "physics_vs_ai": physics_vs_ai_status(),
        "model_training": "NOT AUTHORIZED",
    }


def physics_vs_ai_status() -> dict:
    return {
        "status": "NOT_COMPARABLE",
        "label": "PHYSICS VS SPATIAL AI: NOT_COMPARABLE",
        "reasons": [
            "target mismatch (SWE depth/momentum vs 8-day GFM occurrence)",
            "resolution mismatch",
            "forcing mismatch",
            "horizon mismatch (solver seconds vs meteorological / 8-day occurrence)",
        ],
        "note": COMPARISON_NOT_YET_COMPARABLE,
        "physics_footnote": PHYSICS_FOOTNOTE,
    }


def generate_research_report(experiment_id: Optional[str], created_by: Optional[str] = None) -> dict:
    from floodlens.application.reports import _finalize_snapshot
    from floodlens.application.rate_limit import check_rate as _check

    if created_by:
        _check(created_by, "research.report")
    store = get_platform_store()
    if experiment_id:
        experiment = store.experiments.get(experiment_id)
        if not experiment:
            raise KeyError(experiment_id)
    else:
        listed = list_research_experiments(limit=1)["experiments"]
        if not listed:
            experiment = {
                "suite": None,
                "status": "NOT_RUN",
                "passed": None,
                "experiment_id": None,
                "body_note": "No research experiment has been run in this process.",
            }
        else:
            experiment = get_research_experiment(listed[0]["experiment_id"])
    failed = bool(
        experiment.get("passed") is False
        or (isinstance(experiment.get("status"), str) and "FAIL" in str(experiment.get("status")))
    )
    body = {
        "kind": "research",
        "experiment": {
            "experiment_id": experiment.get("experiment_id") or experiment.get("id"),
            "suite": experiment.get("suite"),
            "status": experiment.get("status"),
            "passed": experiment.get("passed"),
            "failed_at_step": experiment.get("failed_at_step"),
            "config_hash": experiment.get("config_hash"),
        },
        "solver": PHYSICS_MODEL_VERSION,
        "configuration": (experiment.get("provenance") or {}).get("config"),
        "results": {
            "momentum_residual": experiment.get("momentum_residual"),
            "mass_relative_error": experiment.get("mass_relative_error"),
            "equilibrium_residual": experiment.get("equilibrium_residual"),
            "cfl": experiment.get("cfl"),
            "spectral": experiment.get("spectral") or {
                "nyquist_energy_ratio": experiment.get("nyquist_energy_ratio")
            },
            "perturbation": {
                "growth_factor": experiment.get("growth_factor"),
                "interpretation": experiment.get("interpretation"),
            }
            if experiment.get("suite") == "perturbation"
            else None,
            "jacobian": {
                "spectral_radius": experiment.get("spectral_radius"),
                "methodological_note": experiment.get("methodological_note")
                or experiment.get("note"),
                "global_stability_proof": False,
            }
            if experiment.get("suite") == "jacobian"
            else None,
        },
        "diagnostics": experiment.get("status"),
        "pass_fail": "VALIDATION FAILED" if failed else experiment.get("status"),
        "limitations": [
            "Synthetic basin diagnostics are SIMULATED, not observational products.",
            "Local Jacobian spectral radius is not proof of global long-term stability.",
            "Spatial AI remains NOT_VALIDATED. PHYSICS VS SPATIAL AI: NOT_COMPARABLE.",
            "Failed diagnostics are not rewritten as PASS.",
        ],
        "provenance": experiment.get("provenance"),
        "plots": {
            "note": "Plot data are capped summaries (series/subsample maps) stored with the experiment.",
            "nyquist_energy_ratio_series": experiment.get("nyquist_energy_ratio_series")
            or (experiment.get("spectral") or {}).get("nyquist_energy_ratio_series"),
        },
        "safety": "This is a research snapshot, not an operational flood declaration.",
        "executive_summary": {
            "suite": experiment.get("suite"),
            "status": "VALIDATION FAILED" if failed else experiment.get("status"),
            "solver": PHYSICS_MODEL_VERSION,
        },
    }
    if failed:
        body["conclusion"] = "VALIDATION FAILED"
        if experiment.get("failed_at_step"):
            body["conclusion"] = f"FAILED AT STEP {experiment['failed_at_step']}"
    report = store.put_report(
        {
            "city_id": "research",
            "created_by": created_by,
            "kind": "research",
            "model_version": PHYSICS_MODEL_VERSION,
            "physics_model_version": PHYSICS_MODEL_VERSION,
            "body": body,
            "formats": ["json", "csv", "pdf"],
            "job_id": experiment.get("experiment_id"),
            "live": False,
        }
    )
    store.audit("report.research", actor=created_by, detail={"report_id": report["id"]})
    return _finalize_snapshot(report, created_by=created_by, kind="research", map_state=None)


def latest_value(path: str):
    """Return a named diagnostic from the latest matching experiment, or UNAVAILABLE."""
    latest = _latest_by_suite()
    if path == "equilibrium_residual":
        row = latest.get("lake_at_rest") or latest.get("long_term_stability")
        if not row:
            return {"status": "NOT_RUN", "value": None}
        return {"status": row.get("status"), "value": row.get("equilibrium_residual")}
    if path == "lake_at_rest":
        row = latest.get("lake_at_rest")
        if not row:
            return {"status": "NOT_RUN", "passed": None}
        return {"status": row.get("status"), "passed": row.get("passed"), "momentum_residual": row.get("momentum_residual")}
    if path == "nyquist":
        row = latest.get("spectral") or latest.get("lake_at_rest")
        if not row:
            return {"status": "NOT_RUN", "nyquist_energy_ratio": None}
        spec = row.get("spectral") or row
        return {
            "status": row.get("status"),
            "nyquist_energy_ratio": spec.get("nyquist_energy_ratio") or row.get("nyquist_energy_ratio"),
            "unstable_classified": spec.get("unstable_classified", False),
        }
    if path == "spectral_radius":
        row = latest.get("jacobian")
        if not row:
            return {"status": "NOT_RUN", "spectral_radius": None, "global_stability_proof": False}
        return {
            "status": row.get("status"),
            "spectral_radius": row.get("spectral_radius"),
            "global_stability_proof": False,
            "methodological_note": row.get("methodological_note") or row.get("note"),
        }
    if path == "failure":
        for suite in ("long_term_stability", "lake_at_rest", "parabolic_bowl"):
            row = latest.get(suite)
            if row and (row.get("passed") is False or row.get("failed_at_step")):
                return {
                    "status": row.get("status"),
                    "failed_at_step": row.get("failed_at_step"),
                    "suite": suite,
                    "reason": row.get("status"),
                }
        return {"status": "NOT_RUN", "reason": "No failed diagnostic is stored in this process."}
    return {"status": "UNAVAILABLE"}
