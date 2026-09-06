"""Public data accessors. Fail closed. Never invent gauges or RP thresholds."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

DATA_DIR = Path(__file__).resolve().parents[1] / "application" / "data" / "ml"
OPEN_METEO_ARCHIVE = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
    "&hourly=precipitation&timezone=UTC"
)
FLOOD_URL = (
    "https://flood-api.open-meteo.com/v1/flood"
    "?latitude={lat}&longitude={lon}&daily=river_discharge"
    "&start_date={start}&end_date={end}&forecast_days=0"
)
EMSR_LIST_URL = (
    "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/"
    "public-activations-info/?limit=100&offset={offset}"
)


def _load_json(name: str) -> dict:
    path = DATA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def licenses() -> dict:
    return _load_json("licenses.json")


def glofas_cells() -> dict:
    return _load_json("glofas_cells.json")


def emsr_catalog() -> dict:
    return _load_json("emsr_bangladesh_catalog.json")


def openmeteo_sample() -> dict:
    return _load_json("openmeteo_archive_sample.json")


def http_get_json(url: str, timeout: int = 30) -> Optional[dict]:
    """urllib first, curl fallback (some macOS Python builds lack CA certs)."""
    req = Request(url, headers={"User-Agent": "floodlens-x-phase4/0.1"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        try:
            raw = subprocess.check_output(
                ["curl", "-sS", "-A", "floodlens-x-phase4/0.1", "--max-time", str(timeout), url],
                stderr=subprocess.DEVNULL,
            )
            return json.loads(raw.decode("utf-8"))
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
            return None


def http_get_bytes(url: str, timeout: int = 60) -> Optional[bytes]:
    """Binary GET with curl fallback (macOS Python CA gaps)."""
    req = Request(url, headers={"User-Agent": "floodlens-x-phase69b/0.1"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (URLError, TimeoutError, OSError):
        try:
            return subprocess.check_output(
                ["curl", "-sS", "-A", "floodlens-x-phase69b/0.1", "--max-time", str(timeout), url],
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            return None


def fetch_openmeteo_archive(lat: float, lon: float, start: str, end: str) -> Dict[str, Any]:
    url = OPEN_METEO_ARCHIVE.format(lat=lat, lon=lon, start=start, end=end)
    payload = http_get_json(url)
    if not payload or "hourly" not in payload:
        return {
            "available": False,
            "data_status": "UNAVAILABLE",
            "reason": "Open-Meteo archive unreachable",
            "source_url": url,
        }
    return {
        "available": True,
        "data_status": "REAL",
        "source_url": url,
        "hourly": payload["hourly"],
        "license": "CC BY 4.0",
        "attribution": "Weather data by Open-Meteo.com",
    }


def glofas_extract_status() -> dict:
    cells = glofas_cells()
    return {
        "available": False,
        "data_status": cells.get("data_status", "UNAVAILABLE"),
        "label_kind": "MODELLED",
        "reason": (
            "CDS extract not present. Run scripts/phase4_extract_glofas.py with "
            "CDS credentials. Global cube download is forbidden."
        ),
        "cells": cells.get("cells", []),
        "return_period": cells.get("return_period"),
        "max_cells": 3,
    }
