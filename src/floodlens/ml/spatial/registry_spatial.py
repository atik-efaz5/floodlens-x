"""Spatial model registry. Separate from AOI GBDT registry.json so VALIDATED is not inherited."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from floodlens.ml.registry import STATUSES

SPATIAL_REGISTRY = (
    Path(__file__).resolve().parents[2] / "application" / "data" / "ml" / "spatial" / "registry.json"
)
SPATIAL_ID = "ai-spatial-forecast"
SPATIAL_TITLE = "AI Spatial Flood Occurrence"
SPATIAL_MODEL_ID = "AI-SPATIAL-OCCURRENCE-v0.1"


def default_spatial_record() -> dict:
    return {
        "id": SPATIAL_ID,
        "title": SPATIAL_TITLE,
        "kind": "AI_SPATIAL",
        "status": "NOT_TRAINED",
        "accuracy_claim": None,
        "model_id": SPATIAL_MODEL_ID,
        "run_id": None,
        "dataset_version": None,
        "checkpoint": None,
        "validated_split_ids": None,
        "label_kind": "OBSERVED",
        "horizon_hours": 192,
        "comparable_to_physics": False,
        "note": (
            "Spatial U-Net is NOT_TRAINED until held-out GFM maps exist and are validated. "
            "Does not inherit AOI GBDT VALIDATED status. 6h/12h/24h labels are not invented."
        ),
    }


def load_spatial_registry(path: Optional[Path] = None) -> dict:
    path = Path(path or SPATIAL_REGISTRY)
    if not path.exists():
        return default_spatial_record()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") not in STATUSES:
        payload["status"] = "NOT_TRAINED"
    payload.setdefault("accuracy_claim", None)
    payload.setdefault("kind", "AI_SPATIAL")
    payload.setdefault("comparable_to_physics", False)
    return payload


def save_spatial_registry(record: dict, path: Optional[Path] = None) -> dict:
    path = Path(path or SPATIAL_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    if record.get("status") not in STATUSES:
        raise ValueError("invalid spatial registry status")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def public_spatial_status(record: Optional[dict] = None) -> str:
    row = record or load_spatial_registry()
    return row["status"] if row.get("status") == "VALIDATED" else "NOT_TRAINED"


def mark_spatial_trained(
    run_id: str,
    checkpoint: str,
    dataset_version: str,
    path: Optional[Path] = None,
) -> dict:
    record = load_spatial_registry(path)
    if record.get("status") == "VALIDATED":
        return record
    record.update(
        {
            "status": "TRAINED",
            "run_id": run_id,
            "checkpoint": checkpoint,
            "dataset_version": dataset_version,
            "note": (
                "Fit completed on GFM AOI tiles. Not validated. Public catalog remains NOT_TRAINED. "
                "AOI GBDT VALIDATED status is unchanged."
            ),
        }
    )
    return save_spatial_registry(record, path)


def mark_spatial_validated(split_ids: dict, metrics: dict, path: Optional[Path] = None) -> dict:
    record = load_spatial_registry(path)
    if record.get("status") not in {"TRAINED", "VALIDATED"}:
        raise ValueError("cannot validate a spatial model that has not been trained")
    record.update(
        {
            "status": "VALIDATED",
            "validated_split_ids": split_ids,
            "metrics": metrics,
            "accuracy_claim": None,
            "note": "Validated on held-out GFM maps. Still no accuracy % without metric+split+horizon.",
        }
    )
    return save_spatial_registry(record, path)
