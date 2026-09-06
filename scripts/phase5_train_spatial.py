#!/usr/bin/env python3
"""Fit spatial baselines + U-Net. Does not promote the catalog to VALIDATED."""

from floodlens.ml.spatial.train import train_spatial

if __name__ == "__main__":
    report = train_spatial()
    print(report.get("status"), report.get("reason") or report.get("run_id"))
