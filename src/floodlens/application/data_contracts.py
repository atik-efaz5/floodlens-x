"""Phase-2 provenance: data_status, envelopes, source-specific freshness.

New API payloads must not use freshness ``live``. Use RECENT for genuinely
recent observations. ``LIVE`` is forbidden on simulated/demo products.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from floodlens.application.provenance import DATA_VERSION, isoformat, utcnow

DataStatus = Literal["REAL", "SIMULATED", "DEMO", "STALE", "UNAVAILABLE", "PARTIAL"]
FreshnessWindow = Literal["RECENT", "STALE", "EXPIRED", "UNAVAILABLE", "SNAPSHOT", "STATIC"]


def public_source_ref(uri: Optional[str]) -> Optional[str]:
    """Return a non-filesystem identifier for API payloads."""
    if not uri:
        return None
    if "://" in uri and not uri.startswith("file:"):
        return uri
    return Path(uri).name

# Seconds after which an observation is no longer RECENT, then STALE, then EXPIRED.
FRESHNESS_WINDOWS_S = {
    "open-meteo": (15 * 60, 6 * 3600, 48 * 3600),
    "openstreetmap": (None, None, None),  # SNAPSHOT
    "dem": (None, None, None),  # STATIC
    "river-gauge": (30 * 60, 12 * 3600, 72 * 3600),
    "default": (15 * 60, 6 * 3600, 48 * 3600),
}

FORBIDDEN_LIVE = "live"


@dataclass(frozen=True)
class DataEnvelope:
    """Required wrapper for every collection/product in /api/v1."""

    data_status: DataStatus
    provider: str
    dataset: str
    retrieved_at: str
    valid_at: Optional[str] = None
    expires_at: Optional[str] = None
    source_url: Optional[str] = None
    source_version: Optional[str] = None
    freshness: FreshnessWindow = "UNAVAILABLE"
    fallback_used: bool = False
    simulated: bool = False
    spatial_coverage: Optional[Dict[str, Any]] = None
    temporal_coverage: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        if self.freshness.lower() == FORBIDDEN_LIVE or str(self.data_status).upper() == "LIVE":
            raise ValueError("LIVE is not a permitted data_status/freshness")
        if self.simulated and self.data_status == "REAL":
            raise ValueError("REAL data_status cannot be combined with simulated=True")
        payload = {
            "data_status": self.data_status,
            "provider": self.provider,
            "dataset": self.dataset,
            "retrieved_at": self.retrieved_at,
            "valid_at": self.valid_at,
            "expires_at": self.expires_at,
            "source_url": self.source_url,
            "source_version": self.source_version,
            "freshness": self.freshness,
            "fallback_used": self.fallback_used,
            "simulated": self.simulated,
            "spatial_coverage": self.spatial_coverage,
            "temporal_coverage": self.temporal_coverage,
            "data_version": DATA_VERSION,
        }
        payload.update(self.extra)
        return payload


def envelope(
    *,
    data_status: DataStatus,
    provider: str,
    dataset: str,
    freshness: FreshnessWindow,
    fallback_used: bool = False,
    simulated: bool = False,
    valid_at: Optional[str] = None,
    source_url: Optional[str] = None,
    source_version: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    return DataEnvelope(
        data_status=data_status,
        provider=provider,
        dataset=dataset,
        retrieved_at=isoformat(),
        valid_at=valid_at,
        source_url=source_url,
        source_version=source_version,
        freshness=freshness,
        fallback_used=fallback_used,
        simulated=simulated,
        extra=extra or {},
    ).to_dict()


def classify_window(
    observed_at: datetime,
    source_key: str = "default",
    now: Optional[datetime] = None,
) -> FreshnessWindow:
    """Source-specific freshness. Never returns LIVE."""
    current = now or utcnow()
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    windows = FRESHNESS_WINDOWS_S.get(source_key, FRESHNESS_WINDOWS_S["default"])
    if windows[0] is None:
        return "SNAPSHOT" if source_key == "openstreetmap" else "STATIC"
    age_s = (current - observed_at).total_seconds()
    if age_s < 0:
        return "UNAVAILABLE"
    recent_s, stale_s, expired_s = windows
    if age_s <= recent_s:
        return "RECENT"
    if age_s <= stale_s:
        return "STALE"
    if age_s <= expired_s:
        return "EXPIRED"
    return "UNAVAILABLE"


def status_from_window(window: FreshnessWindow, simulated: bool, fallback: bool) -> DataStatus:
    if fallback or simulated:
        return "DEMO"
    if window == "UNAVAILABLE":
        return "UNAVAILABLE"
    if window in {"STALE", "EXPIRED"}:
        return "STALE"
    return "REAL"
