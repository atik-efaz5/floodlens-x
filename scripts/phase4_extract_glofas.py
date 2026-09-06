#!/usr/bin/env python3
"""Extract GloFAS historical discharge at exactly 3 AOI cells.

Refuses a global cube. Requires a CDS account (cdsapi). Without credentials
this script exits 0 after writing an UNAVAILABLE status file — it does not
invent discharge or return-period thresholds.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from floodlens.ml.sources import DATA_DIR, glofas_cells, glofas_extract_status

MAX_CELLS = 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DATA_DIR / "glofas_extract_status.json"))
    args = parser.parse_args()
    meta = glofas_cells()
    cells = meta.get("cells") or []
    if len(cells) > MAX_CELLS:
        raise SystemExit(f"refusing {len(cells)} cells; max is {MAX_CELLS}")
    cds_ok = bool(os.environ.get("CDSAPI_KEY") or Path.home().joinpath(".cdsapirc").exists())
    status = glofas_extract_status()
    status["cds_credentials_present"] = cds_ok
    status["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    if not cds_ok:
        status["reason"] = (
            "No CDS credentials (.cdsapirc or CDSAPI_KEY). Extract skipped. "
            "Global GloFAS cube download is forbidden."
        )
        Path(args.out).write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return 0
    status["reason"] = (
        "CDS credentials found but the 3-cell retrieve is not executed in-repo "
        "(avoid accidental cube downloads). Use cdsapi with a point request for "
        "the three lat/lon cells in glofas_cells.json only."
    )
    Path(args.out).write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
