"""Phase 6.5B: independent-event expansion and dataset-quality gates. Never trains.

Does not call training or validation-promotion helpers.
Does not touch src/floodlens/numerical. Spatial catalog stays NOT_VALIDATED.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from floodlens.ml.spatial.builder import build_spatial_samples_v2
from floodlens.ml.spatial.channel_audit import CONSTANT, MISSING, SPATIAL, TEMPORAL_ONLY, audit_channels
from floodlens.ml.spatial.event_expansion import (
    BASELINE_EVENT_IDS,
    CANDIDATES_CSV,
    SOURCE_COMPATIBILITY,
    acquire_target_clusters,
    build_candidate_inventory,
    diagnose_sylhet,
    detect_duplicate_scenes,
    unknown_diagnostics,
)
from floodlens.ml.spatial.events import coverage_summary, event_records, inventory
from floodlens.ml.spatial.feature_catalog import catalog_from_audit, classify_summary
from floodlens.ml.spatial.gates import event_independence_report, evaluate_gate0, evaluate_gates_af
from floodlens.ml.spatial.schema import (
    SPATIAL_DIR,
    SPATIAL_DATASET_VERSION_V2,
    SPATIAL_DATASET_VERSION_V21,
    SPATIAL_MODEL_ID_V2,
)
from floodlens.ml.spatial.splits import write_split_manifests

REPORT_PATH = SPATIAL_DIR / "phase65b_eval.json"
SPLITS_DIR = SPATIAL_DIR / "splits_v2"


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return None
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if np.isfinite(val) else None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    return obj


def acquire_phase65b(*, download_gfm: bool = False) -> dict:
    from floodlens.ml.spatial.acquire_gfm import index_local_v2, snapshot_processed_v2_index

    snapshot_processed_v2_index("phase65a")
    if download_gfm:
        acq = acquire_target_clusters(download=True)
    else:
        acq = {"clusters": [], "gfm_index_n_kept": None, "download": False}
        acq["index"] = index_local_v2()
        acq["gfm_index_n_kept"] = (acq["index"] or {}).get("n_kept")
        acq["duplicate_scenes"] = detect_duplicate_scenes(acq["index"] or {})
    return acq


def _channel_counts(audit: dict) -> dict:
    channels = audit.get("channels") or {}
    counts = {SPATIAL: 0, TEMPORAL_ONLY: 0, CONSTANT: 0, MISSING: 0}
    for row in channels.values():
        klass = row.get("class") or MISSING
        counts[klass] = counts.get(klass, 0) + 1
    return {
        "n_channels": len(channels),
        "n_spatial": int(audit.get("n_spatial") or counts[SPATIAL]),
        "n_spatially_varying": int(audit.get("n_spatial") or counts[SPATIAL]),
        "n_temporal_only": counts[TEMPORAL_ONLY],
        "n_constant": counts[CONSTANT],
        "n_missing": counts[MISSING],
    }


def evaluate_phase65b(
    processed_dir: Optional[Path] = None,
    acquire_log: Optional[dict] = None,
) -> dict:
    """Dataset quality only. No GBDT, no U-Net, no registry promotion."""
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR_V2, stamp_processed_v2_version

    index_path = Path(processed_dir or PROCESSED_DIR_V2) / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"scenes": []}
    candidates = build_candidate_inventory(index, acquire_log)
    sylhet = diagnose_sylhet()
    unk_diag = unknown_diagnostics(index)
    samples, meta = build_spatial_samples_v2(processed_dir=processed_dir)
    samples = [s for s in samples if not (s.extra or {}).get("synthetic") and s.label_kind != "SIMULATED"]
    inv = inventory(samples) if samples else {
        "n_independent_events": 0,
        "verdict": "INSUFFICIENT FOR VALIDATION",
        "cities": [],
        "pixels": {},
        "event_ids": [],
    }
    event_ids = list(inv.get("event_ids") or [])
    new_ids = sorted(set(event_ids) - set(BASELINE_EVENT_IDS))
    material = len(new_ids) >= 1
    dataset_version = SPATIAL_DATASET_VERSION_V21 if material else SPATIAL_DATASET_VERSION_V2
    if material:
        stamp_processed_v2_version(dataset_version)
        meta = dict(meta or {})
        meta["dataset_version"] = dataset_version
        for sample in samples:
            sample.dataset_version = dataset_version
            sample.extra = dict(sample.extra or {})
            sample.extra["dataset_version"] = dataset_version
            prov = dict((sample.extra.get("provenance") or {}))
            if prov:
                prov["processing_version"] = dataset_version
                sample.extra["provenance"] = prov
    audit = audit_channels(samples) if samples else {"channels": {}, "n_spatial": 0, "cnn_allowed": False}
    events = event_records(samples) if samples else []
    coverage = coverage_summary(samples) if samples else {"regions": [], "n_regions": 0}
    b_report = event_independence_report(samples) if samples else event_independence_report([])
    manifests = {}
    if samples:
        manifests = write_split_manifests(samples, SPLITS_DIR)
    gates_af = evaluate_gates_af(samples, audit, manifests_written=bool(manifests))
    gate0 = evaluate_gate0(samples, audit)
    samples_per_event = {}
    for row in events:
        samples_per_event[row["event_id"]] = int((row.get("provenance") or {}).get("n_tiles") or 0)
    catalog = catalog_from_audit(audit)
    out_dir = SPATIAL_DIR / "gfm" / "processed_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "feature_catalog.json").write_text(
        json.dumps(_jsonable({"channels": catalog, "summary": classify_summary(audit)}), indent=2),
        encoding="utf-8",
    )
    (out_dir / "events.json").write_text(json.dumps(_jsonable(events), indent=2), encoding="utf-8")
    (out_dir / "coverage.json").write_text(json.dumps(_jsonable(coverage), indent=2), encoding="utf-8")
    sample_manifest = [
        {
            "sample_id": f"{(s.extra or {}).get('event_id')}:{(s.extra or {}).get('region_id') or s.city_id}:{s.scene_id}",
            "dataset_version": s.dataset_version,
            "event_id": (s.extra or {}).get("event_id"),
            "scene_id": s.scene_id,
            "region_id": (s.extra or {}).get("region_id") or s.city_id,
            "tile_id": (s.extra or {}).get("tile_id"),
            "split": s.split,
            "target_time": s.valid_at,
            "input_window": (s.extra or {}).get("input_window"),
            "label_window": (s.extra or {}).get("label_window"),
            "label_kind": s.label_kind,
            "rainfall_status": (s.extra or {}).get("rainfall_status"),
            "dem_present": s.dem_present,
            "source_ids": (s.extra or {}).get("source_ids"),
            "deduplication_key": (s.extra or {}).get("deduplication_key"),
        }
        for s in samples
    ]
    (out_dir / "sample_manifest.json").write_text(
        json.dumps({"n": len(sample_manifest), "samples": sample_manifest}, indent=2),
        encoding="utf-8",
    )
    pixels = inv.get("pixels") or {}
    n_events = int(inv.get("n_independent_events") or 0)
    if n_events >= 20:
        recommendation = "DATASET REACHED MINIMUM EVENT FLOOR — TRAINING STILL REQUIRES APPROVAL"
    else:
        recommendation = "DATASET STILL INSUFFICIENT — DO NOT TRAIN"
    accepted = [r for r in candidates if r.get("accepted")]
    rejected = [r for r in candidates if not r.get("accepted")]
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "phase": "6.5B",
        "model_id": SPATIAL_MODEL_ID_V2,
        "dataset_version": dataset_version,
        "material_event_expansion": material,
        "new_independent_event_ids": new_ids,
        "baseline_event_ids": list(BASELINE_EVENT_IDS),
        "dataset": meta,
        "inventory": inv,
        "events": events,
        "coverage": coverage,
        "candidates": candidates,
        "candidates_path": str(CANDIDATES_CSV),
        "accepted_events": accepted,
        "rejected_candidates": rejected,
        "source_compatibility": SOURCE_COMPATIBILITY,
        "sylhet_diagnosis": sylhet,
        "unknown_diagnostics": unk_diag,
        "event_independence": b_report,
        "channel_audit": audit,
        "feature_catalog": catalog,
        "channel_counts": _channel_counts(audit),
        "gate0": gate0,
        "gates_af": gates_af,
        "splits": manifests,
        "duplicate_scenes": detect_duplicate_scenes(index),
        "cnn_trained": False,
        "gbdt_trained": False,
        "unet_trained": False,
        "status": "NOT_TRAINED",
        "public_status": "NOT_TRAINED",
        "catalog_status": "NOT_VALIDATED",
        "promoted_to_validated": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
        "spatial_ai": "NOT_VALIDATED",
        "api_ai_spatial": "UNAVAILABLE",
        "solver_modified": False,
        "statistics": {
            "n_independent_events": n_events,
            "n_scenes": len({s.scene_id for s in samples if s.scene_id}),
            "n_regions": coverage.get("n_regions") or len(inv.get("cities") or []),
            "n_tiles": inv.get("n_tiles") or len(samples),
            "valid_pixels": pixels.get("valid"),
            "flood_pixels": pixels.get("flood"),
            "dry_pixels": pixels.get("dry"),
            "unknown_pixels": pixels.get("unknown"),
            "unknown_percentage": None
            if pixels.get("unknown_fraction") is None
            else 100.0 * float(pixels["unknown_fraction"]),
            "worst_event_unknown_percentage": None
            if unk_diag.get("worst_event_unknown_fraction") is None
            else 100.0 * float(unk_diag["worst_event_unknown_fraction"]),
            "samples_per_event": samples_per_event,
            "train_events": b_report.get("train_events"),
            "validation_events": b_report.get("validation_events"),
            "test_events": b_report.get("test_events"),
            "events_per_year": b_report.get("events_per_year"),
            "events_per_region": b_report.get("events_per_region"),
            "events_per_mechanism": b_report.get("events_per_mechanism"),
        },
        "recommendation": recommendation,
        "note": (
            "Phase 6.5B is independent-event expansion and quality assessment only. "
            "No model was trained. Spatial AI remains NOT_VALIDATED. "
            "POST /api/v1/forecast/ai-spatial stays UNAVAILABLE. "
            "Training requires a separate explicit approval even if Gate B reaches 20 events."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
    (out_dir / "gates_af.json").write_text(json.dumps(_jsonable(gates_af), indent=2), encoding="utf-8")
    return report
