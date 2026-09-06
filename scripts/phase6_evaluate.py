#!/usr/bin/env python3
"""Phase 6 evaluate: channel audit, Gate 0/1/2, spatial baselines. Never VALIDATED."""

from floodlens.ml.spatial.phase6 import evaluate_phase6

if __name__ == "__main__":
    report = evaluate_phase6()
    g0 = report.get("gate0") or {}
    g1 = report.get("gate1") or {}
    g2 = report.get("gate2") or {}
    print("gate0", g0.get("pass"), "failed", g0.get("failed"))
    print("gate1", g1.get("pass"), "failed", g1.get("failed"))
    print("gate2", g2.get("pass"), "failed", g2.get("failed"))
    print("cnn", report.get("cnn_trained"), report.get("cnn_reason"))
    print("validated", report.get("promoted_to_validated"), "events", (report.get("inventory") or {}).get("n_independent_events"))
