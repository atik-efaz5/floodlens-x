#!/usr/bin/env python3
"""Phase 6.5B: discover/acquire independent GFM events and evaluate dataset gates.

Never trains U-Net, CNN, GBDT, or Random Forest.
"""

from floodlens.ml.spatial.phase65b import acquire_phase65b, evaluate_phase65b

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--download-gfm", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()
    acq = None
    if not args.skip_index:
        acq = acquire_phase65b(download_gfm=args.download_gfm)
        print(
            "acquire",
            json.dumps(
                {
                    "n_clusters": len(acq.get("clusters") or []),
                    "gfm_index_n_kept": acq.get("gfm_index_n_kept"),
                    "duplicate_scenes": acq.get("duplicate_scenes"),
                },
                default=str,
            ),
        )
    report = evaluate_phase65b(acquire_log=acq)
    stats = report.get("statistics") or {}
    gates = (report.get("gates_af") or {}).get("gates") or {}
    print("events", stats.get("n_independent_events"), "scenes", stats.get("n_scenes"), "regions", stats.get("n_regions"))
    print("new_events", report.get("new_independent_event_ids"))
    print("gates", {k: v.get("status") for k, v in gates.items() if k in list("ABCDEFGHIJ")})
    print("gate_b_research", (gates.get("B") or {}).get("research_recommendation"))
    print(report.get("recommendation"))
    print("catalog_status", report.get("catalog_status"))
    print("dataset_version", report.get("dataset_version"))
    print("spatial_ai", report.get("spatial_ai"))
