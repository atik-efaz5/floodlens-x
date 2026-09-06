#!/usr/bin/env python3
"""Phase 5.5: expand-independent-events acquire is separate; this writes the eval report."""

from floodlens.ml.spatial.phase55 import evaluate_phase55

if __name__ == "__main__":
    report = evaluate_phase55()
    print(report.get("validation_verdict"), report.get("decision", {}).get("option"), "validated=", report.get("promoted_to_validated"))
    inv = report.get("inventory") or {}
    print("events", inv.get("n_independent_events"), "tiles", inv.get("n_tiles"), "days", inv.get("n_days"))
