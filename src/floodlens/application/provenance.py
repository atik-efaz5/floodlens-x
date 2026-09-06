"""Provenance, freshness, and model-version contracts.

Every user-facing product must carry these fields. Freshness ``live`` is only
allowed when ``timestamp`` is a real observation time from an ingest source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

Freshness = Literal["live", "recent", "stale", "unavailable", "demo"]

PHYSICS_MODEL_VERSION = "SW-SOLVER-v0.6"
FORECAST_MODEL_VERSION = "FLOOD-NOWCAST-HEURISTIC-v0.1"
AI_MODEL_VERSION = None  # no trained flood model in v1
DATA_VERSION = "platform-v1"
FORMULA_ID = "risk.p_times_e_times_s.v0"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: Optional[datetime] = None) -> str:
    stamp = value or utcnow()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


@dataclass(frozen=True)
class Provenance:
    source: str
    timestamp: str
    data_version: str = DATA_VERSION
    model_version: Optional[str] = None
    freshness: Freshness = "demo"
    simulated: bool = True

    def to_dict(self) -> dict:
        payload = asdict(self)
        if payload["freshness"] == "live" and payload["simulated"]:
            raise ValueError("Live freshness cannot be combined with simulated=True")
        return payload


def demo_provenance(source: str, model_version: Optional[str] = None) -> Provenance:
    return Provenance(
        source=source,
        timestamp=isoformat(),
        data_version=DATA_VERSION,
        model_version=model_version,
        freshness="demo",
        simulated=True,
    )


def observed_provenance(
    source: str,
    timestamp: str,
    freshness: Freshness,
    model_version: Optional[str] = None,
) -> Provenance:
    if freshness == "demo":
        return demo_provenance(source, model_version)
    return Provenance(
        source=source,
        timestamp=timestamp,
        data_version=DATA_VERSION,
        model_version=model_version,
        freshness=freshness,
        simulated=False,
    )


def classify_freshness(observed_at: datetime, now: Optional[datetime] = None) -> Freshness:
    """Map observation age to freshness. Never returns live for demo clocks."""
    current = now or utcnow()
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    age_s = (current - observed_at).total_seconds()
    if age_s < 0:
        return "unavailable"
    if age_s <= 15 * 60:
        return "live"
    if age_s <= 6 * 3600:
        return "recent"
    if age_s <= 48 * 3600:
        return "stale"
    return "unavailable"
