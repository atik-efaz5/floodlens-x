#!/usr/bin/env python3
"""Phase 6.7 Track A diagnostic baselines. Never VALIDATED. Never trains a CNN."""

from floodlens.ml.spatial.phase67 import evaluate_phase67
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

if __name__ == "__main__":
    report = evaluate_phase67()
    freeze = report.get("freeze") or {}
    gates = (report.get("gates_67") or {}).get("gates") or {}
    spatial = load_spatial_registry()
    print("dataset", freeze.get("dataset_version"))
    print("events", freeze.get("n_independent_events"), "maps", freeze.get("n_maps"))
    print(
        "split",
        len(freeze.get("train_events") or []),
        len(freeze.get("validation_events") or []),
        len(freeze.get("test_events") or []),
    )
    print("label_m", freeze.get("label_resolution_m"), "working", freeze.get("working_grid"))
    print("classification", (report.get("gates_67") or {}).get("classification"))
    print("gates", {k: v.get("pass") if k != "F" else v.get("classification") for k, v in gates.items()})
    print("catalog", report.get("catalog_status"), "api", report.get("spatial_api"))
    print("public_spatial", public_spatial_status(spatial), "registry", spatial.get("status"))
    print("validated", report.get("promoted_to_validated"), "cnn", report.get("cnn_trained"))
    print("artifacts", report.get("artifact_dir"), report.get("report_md"))
