#!/usr/bin/env python3
"""Fetch Open-Meteo archive for the three MVP city centers.

Tiny extracts only. Attribution: Weather data by Open-Meteo.com (CC BY 4.0).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from floodlens.ml.dataset_builder import city_centers
from floodlens.ml.sources import DATA_DIR, fetch_openmeteo_archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-06-14")
    parser.add_argument("--end", default="2022-06-20")
    parser.add_argument("--out", default=str(DATA_DIR / "openmeteo_archive_sample.json"))
    args = parser.parse_args()
    cities = {}
    for city_id, (lat, lon) in city_centers().items():
        payload = fetch_openmeteo_archive(lat, lon, args.start, args.end)
        if not payload.get("available"):
            print(f"{city_id}: UNAVAILABLE {payload.get('reason')}")
            continue
        hours = payload["hourly"].get("time") or []
        vals = payload["hourly"].get("precipitation") or []
        cities[city_id] = {
            "lat": lat,
            "lon": lon,
            "n_hours": len(hours),
            "time": hours,
            "precipitation_mm": vals,
            "sum_mm": round(sum(v or 0 for v in vals), 3),
        }
        print(city_id, "hours", len(hours), "sum_mm", cities[city_id]["sum_mm"])
    if not cities:
        return 1
    out = {
        "source": "Open-Meteo Historical /v1/archive (ERA5 family)",
        "license": "CC BY 4.0",
        "attribution": "Weather data by Open-Meteo.com",
        "data_status": "REAL",
        "kind": "OBSERVED_REANALYSIS",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "start_date": args.start,
        "end_date": args.end,
        "note": "Tiny AOI-center extract. Not a full training archive.",
        "cities": cities,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
