#!/usr/bin/env python3
"""Download AOI-clipped GFM ensemble flood extent (size-capped)."""

import os

from floodlens.ml.spatial.acquire_gfm import acquire, index_local_raw

if __name__ == "__main__":
    if os.environ.get("FLOODLENS_GFM_LOCAL_ONLY") == "1":
        index = index_local_raw()
    else:
        index = acquire()
    print("kept", index.get("n_kept"), "raw_bytes", index.get("raw_bytes"))
