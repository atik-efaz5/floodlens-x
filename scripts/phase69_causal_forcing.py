#!/usr/bin/env python3
"""Phase 6.9 causal forcing audit. Never trains a model. Never downloads TIGGE."""

from floodlens.ml.spatial.phase69 import DECISION_TEXT, evaluate_phase69
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

if __name__ == "__main__":
    report = evaluate_phase69(write_docs=True)
    counts = report.get("counts") or {}
    letter = report.get("decision_letter")
    gates = (report.get("gates") or {}).get("gates") or {}
    spatial = load_spatial_registry()
    print("DECISION:", letter, DECISION_TEXT.get(letter, letter))
    print("TARGET B:", report.get("target_b_status"))
    print("FORECAST-VINTAGE FORCING:", report.get("forecast_vintage_status"))
    print("HYDROLOGICAL STATE:", report.get("hydro_status"))
    print("pairs", counts.get("n_pairs"), "events", counts.get("n_independent_events"))
    print("acquired_forecast_pairs", counts.get("n_pairs_with_acquired_forecast"))
    print("gates", {k: v.get("status") for k, v in gates.items()})
    print("catalog", report.get("catalog_status"), "api", report.get("spatial_api"))
    print("public_spatial", public_spatial_status(spatial))
    print("validated", report.get("promoted_to_validated"), "cnn", report.get("cnn_trained"))
    print("artifacts", report.get("artifact_dir"), report.get("report_md"))
    print("MODEL TRAINING: NOT AUTHORIZED")
    print("SOLVER MODIFIED: NO")
