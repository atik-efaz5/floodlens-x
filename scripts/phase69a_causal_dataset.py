#!/usr/bin/env python3
"""Phase 6.9A causal Target-B dataset construction. Never trains a model."""

from floodlens.ml.spatial.phase69a import DECISION_TEXT, evaluate_phase69a
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

if __name__ == "__main__":
    report = evaluate_phase69a(write_docs=True, acquire_forecast=True)
    counts = report.get("counts") or {}
    letter = report.get("decision_letter")
    spatial = load_spatial_registry()
    print("DECISION:", letter, DECISION_TEXT.get(letter, letter))
    print("INDEPENDENT EVENTS:", counts.get("n_independent_events"))
    print("TARGET-B PAIRS:", counts.get("n_pairs"))
    print("FULL CAUSAL PAIRS:", counts.get("n_full_causal"))
    print("PARTIAL CAUSAL PAIRS:", counts.get("n_partial_causal"))
    print("STATE-ONLY PAIRS:", counts.get("n_state_only"))
    print("POST-T0 / OBSERVATIONAL-ONLY PAIRS:", counts.get("n_observational_only"))
    print("FORECAST-VINTAGE COVERAGE:", counts.get("forecast_vintage_coverage_pct"), "%")
    print("EVENTS WITH FULL CAUSAL COVERAGE:", counts.get("n_events_full_causal"))
    print("TRAIN EVENTS WITH FULL CAUSAL PAIRS:", counts.get("n_train_events_full"))
    print("VALIDATION EVENTS WITH FULL CAUSAL PAIRS:", counts.get("n_val_events_full"))
    print("TEST EVENTS WITH FULL CAUSAL PAIRS:", counts.get("n_test_events_full"))
    print("GLOFAS STATE STATUS:", report.get("hydro_status"))
    print("TARGET B:", report.get("target_b_status"))
    print("catalog", report.get("catalog_status"), "api", report.get("spatial_api"))
    print("public_spatial", public_spatial_status(spatial))
    print("artifacts", report.get("artifact_dir"), report.get("report_md"))
    print("MODEL TRAINING: NOT AUTHORIZED")
    print("SPATIAL AI: NOT_VALIDATED")
    print("SPATIAL API: UNAVAILABLE")
    print("SOLVER MODIFIED: NO")
