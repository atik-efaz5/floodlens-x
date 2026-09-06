#!/usr/bin/env python3
"""Phase 5.0 access probe. No large download."""

from floodlens.ml.spatial.probe import run_probe

if __name__ == "__main__":
    report = run_probe(write=True)
    print(report["primary_label_source"], "stop=" + str(report["stop"]))
    print("wrote", report.get("wrote"))
