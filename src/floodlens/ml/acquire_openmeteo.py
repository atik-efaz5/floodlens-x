"""Acquire Open-Meteo GloFAS discharge + ERA5-family precip for 3 AOI centers.

No CDS credentials. Three cells only. Year-chunked HTTPS. CC BY 4.0 attribution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from floodlens.ml.dataset_builder import city_centers
from floodlens.ml.sources import http_get_json

REAL_DIR = Path(__file__).resolve().parents[1] / "application" / "data" / "ml" / "real"
FLOOD_URL = (
    "https://flood-api.open-meteo.com/v1/flood"
    "?latitude={lat}&longitude={lon}&daily=river_discharge"
    "&start_date={start}&end_date={end}&forecast_days=0"
)
PRECIP_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
    "&hourly=precipitation&timezone=UTC"
)
PRECIP_START = "2014-12-01"
PRECIP_END = "2024-12-31"
DISCHARGE_START = "2015-01-01"
DISCHARGE_END = "2024-12-31"
YEARS = list(range(2014, 2025))


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _years_for(start: str, end: str) -> List[tuple]:
    y0, y1 = int(start[:4]), int(end[:4])
    out = []
    for year in range(y0, y1 + 1):
        a = start if year == y0 else f"{year}-01-01"
        b = end if year == y1 else f"{year}-12-31"
        out.append((a, b))
    return out


def fetch_discharge_city(city_id: str, lat: float, lon: float) -> dict:
    times: List[str] = []
    values: List[float] = []
    urls = []
    snapped = {}
    for start, end in _years_for(DISCHARGE_START, DISCHARGE_END):
        url = FLOOD_URL.format(lat=lat, lon=lon, start=start, end=end)
        payload = http_get_json(url, timeout=60)
        if not payload or "daily" not in payload:
            raise RuntimeError(f"discharge unavailable {city_id} {start} {end}: {payload}")
        daily = payload["daily"]
        times.extend(daily.get("time") or [])
        values.extend(daily.get("river_discharge") or [])
        urls.append(url)
        snapped = {
            "grid_lat": payload.get("latitude"),
            "grid_lon": payload.get("longitude"),
            "elevation": payload.get("elevation"),
        }
    return {
        "city_id": city_id,
        "request_lat": lat,
        "request_lon": lon,
        **snapped,
        "source_urls": urls,
        "time": times,
        "river_discharge_m3s": values,
        "n": len(times),
        "n_null": sum(1 for v in values if v is None),
        "units": "m3 s-1",
    }


def fetch_precip_city(city_id: str, lat: float, lon: float) -> dict:
    times: List[str] = []
    values: List[float] = []
    urls = []
    for start, end in _years_for(PRECIP_START, PRECIP_END):
        url = PRECIP_URL.format(lat=lat, lon=lon, start=start, end=end)
        payload = http_get_json(url, timeout=90)
        if not payload or "hourly" not in payload:
            raise RuntimeError(f"precip unavailable {city_id} {start} {end}: {payload}")
        hourly = payload["hourly"]
        times.extend(hourly.get("time") or [])
        values.extend(hourly.get("precipitation") or [])
        urls.append(url)
    return {
        "city_id": city_id,
        "lat": lat,
        "lon": lon,
        "source_urls": urls,
        "time": times,
        "precipitation_mm": values,
        "n": len(times),
        "n_null": sum(1 for v in values if v is None),
        "units": "mm",
    }


def acquire(out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir or REAL_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    centers = city_centers()
    discharge: Dict[str, dict] = {}
    precip: Dict[str, dict] = {}
    for city_id, (lat, lon) in centers.items():
        print(f"discharge {city_id} ...", flush=True)
        discharge[city_id] = fetch_discharge_city(city_id, lat, lon)
        print(f"  n={discharge[city_id]['n']} nulls={discharge[city_id]['n_null']}", flush=True)
        print(f"precip {city_id} ...", flush=True)
        precip[city_id] = fetch_precip_city(city_id, lat, lon)
        print(f"  n={precip[city_id]['n']} nulls={precip[city_id]['n_null']}", flush=True)
    disc_path = out_dir / "discharge_2015_2024.json"
    precip_path = out_dir / "precip_2014_2024.json"
    disc_blob = json.dumps(
        {
            "provider": "Open-Meteo Flood API (GloFAS v4 reanalysis)",
            "license": "CC BY 4.0; GloFAS/Copernicus CEMS-FLOODS",
            "attribution": "Weather data by Open-Meteo.com; GloFAS/Copernicus EMS",
            "label_kind": "MODELLED",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "start_date": DISCHARGE_START,
            "end_date": DISCHARGE_END,
            "cities": discharge,
        },
        separators=(",", ":"),
    )
    precip_blob = json.dumps(
        {
            "provider": "Open-Meteo Historical /v1/archive (ERA5 family)",
            "license": "CC BY 4.0",
            "attribution": "Weather data by Open-Meteo.com",
            "kind": "OBSERVED_REANALYSIS",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "start_date": PRECIP_START,
            "end_date": PRECIP_END,
            "cities": precip,
        },
        separators=(",", ":"),
    )
    disc_path.write_text(disc_blob, encoding="utf-8")
    precip_path.write_text(precip_blob, encoding="utf-8")
    manifest = {
        "dataset_version": "phase4.5-openmeteo-glofas-v1",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "discharge_2015_2024.json": {
                "sha256": _sha256_bytes(disc_blob.encode("utf-8")),
                "bytes": disc_path.stat().st_size,
                "role": "Track A modelled daily discharge labels + Q lookback",
            },
            "precip_2014_2024.json": {
                "sha256": _sha256_bytes(precip_blob.encode("utf-8")),
                "bytes": precip_path.stat().st_size,
                "role": "Hourly precip features (reanalysis up to issue time t)",
            },
        },
        "size_estimate_note": (
            "Three AOI points only. ~10 years daily Q + ~10 years hourly precip. "
            "Not a global cube. Not WorldFloods."
        ),
        "credentials": "none",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("wrote", disc_path, disc_path.stat().st_size)
    print("wrote", precip_path, precip_path.stat().st_size)
    return manifest


if __name__ == "__main__":
    acquire()
