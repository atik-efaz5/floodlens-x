#!/usr/bin/env python3
"""Phase 6.10 partial-causal Target-B design. Never trains a model."""

from floodlens.ml.spatial.phase610 import DECISION_TEXT, evaluate_phase610
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

if __name__ == "__main__":
    report = evaluate_phase610(write_docs=True, write_artifacts=True)
    counts = report.get("counts") or {}
    p2 = (report.get("policies") or {}).get("policy2_forecast") or {}
    letter = report.get("decision_letter")
    spatial = load_spatial_registry()
    print("DECISION:", letter, DECISION_TEXT.get(letter, letter))
    print("INDEPENDENT EVENTS:", counts.get("n_independent_events"))
    print("TARGET-B PAIRS:", counts.get("n_pairs"))
    print("FULL CAUSAL PAIRS:", counts.get("n_full_causal"))
    print("PARTIAL CAUSAL PAIRS:", counts.get("n_partial_causal"))
    print("STATE-ONLY PAIRS:", counts.get("n_state_only"))
    print("FORECAST-ELIGIBLE PAIRS:", (report.get("forecast_set") or {}).get("n_pairs"))
    print("TRAIN:", p2.get("train"))
    print("VAL:", p2.get("val"))
    print("TEST:", p2.get("test"))
    print("HYDROLOGY: MODELLED_STATE_AT_T0")
    print("TARGET B:", report.get("target_b_status"))
    print("gates", report.get("training_gates"))
    print("catalog", report.get("catalog_status"), "api", report.get("spatial_api"))
    print("public_spatial", public_spatial_status(spatial))
    print("artifacts", report.get("artifact_dir"), report.get("report_md"))
    print("MODEL TRAINING: NOT AUTHORIZED")
    print("SPATIAL AI: NOT_VALIDATED")
    print("SPATIAL API: UNAVAILABLE")
    print("TRACK B: SEPARATE")
    print("TRACK C: NOT YET IMPLEMENTED")
    print("SOLVER MODIFIED: NO")
