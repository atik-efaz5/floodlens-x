"""Open-Meteo adapter: OBSERVED vs FORECAST, explicit DEMO fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.error import URLError
from urllib.request import urlopen

from floodlens.application.canonical import RainfallObservation
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import classify_window, envelope
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat, utcnow
from floodlens.application.rate_limit import INGEST_BUCKET
from floodlens.application.repository import get_repository
from floodlens.application.validation import validate_non_negative

LOGGER = logging.getLogger("floodlens.ingest.meteo")

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}&hourly=precipitation"
    "&forecast_days=3&past_days=1&timezone=UTC"
)


def _synthetic_series(city_id: str) -> List[RainfallObservation]:
    now = utcnow()
    retrieved = isoformat(now)
    rows = []
    for hour in range(0, 73, 6):
        stamp = now - timedelta(hours=36 - hour)
        mm = max(0.0, 2.0 + (hour / 72.0) * 8.0)
        kind = "FORECAST" if stamp >= now else "SIMULATED"
        rows.append(
            RainfallObservation(
                city_id=city_id,
                value_mm=mm,
                unit="mm",
                observed_at=isoformat(stamp),
                valid_at=isoformat(stamp),
                kind=kind if kind == "FORECAST" else "SIMULATED",
                provider="demo-rainfall-generator",
                data_status="DEMO",
                retrieved_at=retrieved,
            )
        )
    return rows


def parse_open_meteo(payload: dict, city_id: str, lon: float, lat: float) -> List[RainfallObservation]:
    hours = payload.get("hourly", {}).get("time", [])
    values = payload.get("hourly", {}).get("precipitation", [])
    now = utcnow()
    retrieved = isoformat(now)
    rows = []
    for stamp, value in zip(hours, values):
        observed_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        mm = float(value or 0.0)
        validate_non_negative("rainfall_mm", mm)
        kind = "FORECAST" if observed_at >= now - timedelta(minutes=30) else "OBSERVED"
        rows.append(
            RainfallObservation(
                city_id=city_id,
                value_mm=mm,
                unit="mm",
                observed_at=isoformat(observed_at),
                valid_at=isoformat(observed_at),
                kind=kind,
                provider="Open-Meteo",
                data_status="REAL",
                retrieved_at=retrieved,
                lon=lon,
                lat=lat,
            )
        )
    return rows


def fetch_open_meteo_precipitation(city_id: str = "dhaka") -> dict:
    """REAL Open-Meteo when reachable; otherwise DEMO with fallback_used=true."""
    repo = get_repository()
    store = get_platform_store()
    city = create_city_registry().get_city(city_id)
    lon, lat = city.center_lon, city.center_lat
    fallback_used = False
    if not INGEST_BUCKET.allow():
        rows = _synthetic_series(city_id)
        fallback_used = True
        LOGGER.warning("open-meteo rate-limited city=%s; demo fallback", city_id)
    else:
        try:
            url = OPEN_METEO_URL.format(lat=lat, lon=lon)
            with urlopen(url, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = parse_open_meteo(payload, city_id, lon, lat)
            if not rows:
                raise RuntimeError("empty open-meteo series")
            LOGGER.info("open-meteo ok city=%s n=%s", city_id, len(rows))
        except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
            LOGGER.warning("open-meteo failed city=%s err=%s; demo fallback", city_id, exc)
            rows = _synthetic_series(city_id)
            fallback_used = True

    for row in rows:
        repo.put_rainfall(row)

    last = rows[-1]
    observed = [r for r in rows if r.kind == "OBSERVED"]
    anchor = observed[-1] if observed else last
    window = classify_window(
        datetime.fromisoformat(anchor.observed_at),
        "open-meteo",
    ) if not fallback_used else "UNAVAILABLE"
    data_status = "DEMO" if fallback_used else ("STALE" if window in {"STALE", "EXPIRED"} else "REAL")
    envelope_freshness = "SNAPSHOT" if fallback_used else window
    if envelope_freshness == "UNAVAILABLE" and not fallback_used:
        envelope_freshness = "RECENT"  # retrieved now; series includes future forecast hours
    prov = envelope(
        data_status=data_status,
        provider="Open-Meteo" if not fallback_used else "demo-rainfall-generator",
        dataset="precipitation",
        freshness=envelope_freshness if envelope_freshness in {
            "RECENT", "STALE", "EXPIRED", "UNAVAILABLE", "SNAPSHOT", "STATIC"
        } else "RECENT",
        fallback_used=fallback_used,
        simulated=fallback_used,
        valid_at=last.valid_at,
        source_url=None if fallback_used else "https://open-meteo.com/",
        extra={"kinds": sorted({r.kind for r in rows})},
    )
    # keep legacy freshness key for Phase-1 tests
    if fallback_used:
        prov["freshness"] = "demo"
        prov["source"] = "demo-rainfall-generator"
        prov["simulated"] = True
        prov["timestamp"] = last.observed_at
    else:
        prov["source"] = "open-meteo"
        prov["simulated"] = False
        prov["timestamp"] = last.observed_at
        if prov["freshness"] == "RECENT":
            prov["freshness"] = "recent"
        elif prov["freshness"] == "STALE":
            prov["freshness"] = "stale"
        elif prov["freshness"] == "UNAVAILABLE":
            prov["freshness"] = "unavailable"
        elif prov["freshness"] == "EXPIRED":
            prov["freshness"] = "stale"
    store.ingest_runs.append(
        {
            "kind": "rainfall",
            "city_id": city_id,
            "count": len(rows),
            "at": isoformat(),
            "fallback_used": fallback_used,
        }
    )
    return {
        "city_id": city_id,
        "samples": len(rows),
        "observed": sum(1 for r in rows if r.kind == "OBSERVED"),
        "forecast": sum(1 for r in rows if r.kind == "FORECAST"),
        "fallback_used": fallback_used,
        "provenance": prov,
    }
