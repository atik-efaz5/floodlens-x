#!/usr/bin/env python3
"""Phase 6 acquire: 64×64 GFM AOI clips + elevation + rivers + precip lattice."""

from floodlens.ml.spatial.phase6 import acquire_phase6

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--download-gfm", action="store_true")
    parser.add_argument("--skip-features", action="store_true")
    args = parser.parse_args()
    out = acquire_phase6(download_gfm=args.download_gfm, fetch_features=not args.skip_features)
    gfm = out.get("gfm") or {}
    print("gfm_n_kept", gfm.get("n_kept") or gfm.get("gfm_n_kept"), "elevation", out.get("elevation"), "rivers", out.get("rivers"))
