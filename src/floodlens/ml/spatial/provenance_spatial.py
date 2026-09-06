"""Spatial-dataset provenance. Extends application envelopes; does not replace them."""

from __future__ import annotations

from typing import Optional

from floodlens.application.data_contracts import envelope
from floodlens.application.provenance import isoformat, utcnow


def spatial_artifact_provenance(
    *,
    data_status: str,
    source: str,
    dataset: str,
    source_url: Optional[str] = None,
    source_version: Optional[str] = None,
    checksum: Optional[object] = None,
    processing_version: Optional[str] = None,
    license_name: Optional[str] = None,
    attribution: Optional[str] = None,
    label_kind: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    payload = envelope(
        data_status=data_status,
        provider=source,
        dataset=dataset,
        freshness="SNAPSHOT",
        source_url=source_url,
        source_version=source_version,
        extra={
            "source": source,
            "source_version": source_version,
            "retrieval_time": isoformat(utcnow()),
            "checksum": checksum,
            "processing_version": processing_version,
            "license": license_name,
            "attribution": attribution,
            "status": data_status,
            "label_kind": label_kind,
            **(extra or {}),
        },
    )
    return payload


REQUIRED_KEYS = (
    "source",
    "source_version",
    "processing_version",
    "status",
    "license",
    "attribution",
)


def provenance_complete(record: Optional[dict]) -> bool:
    if not record:
        return False
    extra = record.get("extra") if "provider" in record else record
    blob = extra or record
    for key in REQUIRED_KEYS:
        if not blob.get(key) and not record.get(key):
            return False
    return bool(blob.get("checksum") or blob.get("source_url") or record.get("source_url"))
