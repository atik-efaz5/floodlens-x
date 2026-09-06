#!/usr/bin/env python3
"""Phase 6.5A: index real GFM processed_v2 and evaluate dataset-quality gates.

Never trains U-Net, CNN, GBDT, or Random Forest.
"""

from floodlens.ml.spatial.phase65a import acquire_phase65a, evaluate_phase65a

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--download-gfm", action="store_true")
    parser.add_argument("--skip-features", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()
    if not args.skip_index:
        acq = acquire_phase65a(download_gfm=args.download_gfm, fetch_features=not args.skip_features)
        gfm = acq.get("gfm") or {}
        print("acquire", json.dumps({k: v for k, v in acq.items() if k != "gfm"}, default=str))
        print("gfm_n_kept", gfm.get("n_kept"), "tiles", gfm.get("tiles"), "failed", len(gfm.get("failed_downloads") or []))
    report = evaluate_phase65a()
    stats = report.get("statistics") or {}
    gates = (report.get("gates_af") or {}).get("gates") or {}
    print("events", stats.get("n_independent_events"), "scenes", stats.get("n_scenes"), "regions", stats.get("n_regions"))
    print("gates", {k: v.get("status") for k, v in gates.items() if k in list("ABCDEFGHIJ")})
    print(report.get("recommendation"))
    print("catalog_status", report.get("catalog_status"))
