#!/usr/bin/env python3
"""Phase 6.8A Target B observational diagnostic. Never trains a model."""

from floodlens.ml.spatial.phase68a import DECISION_TEXT, evaluate_phase68a
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

if __name__ == "__main__":
    report = evaluate_phase68a(write_docs=True)
    counts = report.get("counts") or {}
    dt = (report.get("delta_t") or {}).get("hours") or {}
    forcing = report.get("forcing") or {}
    unk = report.get("unknown") or {}
    letter = report.get("decision_letter")
    spatial = load_spatial_registry()
    print("TARGET B STATUS:", DECISION_TEXT.get(letter, letter))
    print("INDEPENDENT EVENTS:", counts.get("n_independent_events"))
    print("OBSERVED TRANSITION PAIRS:", counts.get("n_observed_transition_pairs"))
    print("MEDIAN DELTA-T HOURS:", dt.get("median"))
    print("FORCING COMPLETENESS:", forcing.get("complete_pair_fraction"))
    print("UNKNOWN PIXEL RATE:", unk.get("mean_unknown_fraction"))
    print("gates", {k: v.get("pass") for k, v in ((report.get("gates") or {}).get("gates") or {}).items()})
    print("catalog", report.get("catalog_status"), "api", report.get("spatial_api"))
    print("public_spatial", public_spatial_status(spatial), "registry", spatial.get("status"))
    print("validated", report.get("promoted_to_validated"), "cnn", report.get("cnn_trained"))
    print("artifacts", report.get("artifact_dir"), report.get("report_md"))
    print("MODEL TRAINING: NOT AUTHORIZED")
    print("SOLVER MODIFIED: NO")
