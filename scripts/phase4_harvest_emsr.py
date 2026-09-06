#!/usr/bin/env python3
"""Harvest Copernicus EMS Rapid Mapping metadata for Bangladesh.

Does not download vector ZIPs or WorldFloods. Absence of an activation is not dry.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from floodlens.ml.sources import DATA_DIR, EMSR_LIST_URL, emsr_catalog, http_get_json


def harvest() -> dict:
    offset = 0
    rows = []
    while True:
        payload = http_get_json(EMSR_LIST_URL.format(offset=offset))
        if not payload:
            break
        batch = payload.get("results") or []
        rows.extend(batch)
        if not payload.get("next") or not batch:
            break
        offset += len(batch)
        if offset > 2000:
            break
    bangladesh = []
    for row in rows:
        countries = row.get("countries") or []
        names = []
        for item in countries:
            names.append(item.get("name") if isinstance(item, dict) else str(item))
        blob = " ".join(names).lower() + " " + str(row.get("name") or "").lower()
        if "bangladesh" in blob:
            bangladesh.append(row)
    cited = emsr_catalog()
    return {
        "dataset_version": cited.get("dataset_version"),
        "label_kind": "OBSERVED",
        "polygons_downloaded": False,
        "harvest": {
            "endpoint": EMSR_LIST_URL.split("?")[0],
            "n_public_listed": len(rows),
            "n_bangladesh_in_public_list": len(bangladesh),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "activations": bangladesh,
        "cited_public_activations": cited.get("cited_public_activations"),
        "named_holdout_events_not_in_emsr_public_list": cited.get(
            "named_holdout_events_not_in_emsr_public_list"
        ),
        "note": cited.get("note"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DATA_DIR / "emsr_bangladesh_catalog.json"))
    args = parser.parse_args()
    payload = harvest()
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        "listed",
        payload["harvest"]["n_public_listed"],
        "bangladesh",
        payload["harvest"]["n_bangladesh_in_public_list"],
        "wrote",
        args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
