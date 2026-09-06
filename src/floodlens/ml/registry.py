"""Model registry. Public catalog stays NOT_TRAINED until VALIDATED."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

STATUSES = ("NOT_TRAINED", "TRAINED", "VALIDATED", "DEPLOYED", "DEPRECATED")
DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "application" / "data" / "ml" / "registry.json"


def default_record() -> dict:
    return {
        "id": "ai-forecast",
        "title": "AI Forecast",
        "kind": "AI",
        "status": "NOT_TRAINED",
        "accuracy_claim": None,
        "model_id": None,
        "run_id": None,
        "dataset_version": None,
        "checkpoint": None,
        "validated_split_ids": None,
        "note": "No validated AI flood model is deployed.",
    }


def load_registry(path: Optional[Path] = None) -> dict:
    path = Path(path or DEFAULT_REGISTRY)
    if not path.exists():
        return default_record()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") not in STATUSES:
        payload["status"] = "NOT_TRAINED"
    payload.setdefault("accuracy_claim", None)
    return payload


def save_registry(record: dict, path: Optional[Path] = None) -> dict:
    path = Path(path or DEFAULT_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    if record.get("status") not in STATUSES:
        raise ValueError("invalid registry status")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def public_status(record: Optional[dict] = None) -> str:
    """API catalog only leaves NOT_TRAINED after VALIDATED."""
    row = record or load_registry()
    return row["status"] if row.get("status") == "VALIDATED" else "NOT_TRAINED"


def mark_trained(run_id: str, checkpoint: str, dataset_version: str, path: Optional[Path] = None) -> dict:
    record = load_registry(path)
    if record.get("status") == "VALIDATED":
        return record
    record.update(
        {
            "status": "TRAINED",
            "run_id": run_id,
            "checkpoint": checkpoint,
            "dataset_version": dataset_version,
            "note": "Fit completed. Not validated. Public catalog remains NOT_TRAINED.",
        }
    )
    return save_registry(record, path)


def mark_validated(split_ids: dict, metrics: dict, path: Optional[Path] = None) -> dict:
    record = load_registry(path)
    if record.get("status") not in {"TRAINED", "VALIDATED"}:
        raise ValueError("cannot validate a model that has not been trained")
    record.update(
        {
            "status": "VALIDATED",
            "validated_split_ids": split_ids,
            "metrics": metrics,
            "accuracy_claim": None,
            "note": "Validated on documented split. Still no accuracy percentage without metric+split+horizon.",
        }
    )
    return save_registry(record, path)
