"""Phase 6.5A: real GFM processed_v2 + dataset-quality gates. Never trains a model.

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
from floodlens.ml.spatial.events import coverage_summary, event_records, inventory
from floodlens.ml.spatial.feature_catalog import catalog_from_audit, classify_summary
from floodlens.ml.spatial.gates import evaluate_gate0, evaluate_gates_af
from floodlens.ml.spatial.schema import SPATIAL_DIR, SPATIAL_DATASET_VERSION_V2, SPATIAL_MODEL_ID_V2
from floodlens.ml.spatial.splits import write_split_manifests

REPORT_PATH = SPATIAL_DIR / "phase65a_eval.json"
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


def acquire_phase65a(*, download_gfm: bool = False, fetch_features: bool = True) -> dict:
    from floodlens.ml.spatial.acquire_gfm import RAW_DIR, acquire_v2, index_local_v2

    out = {
        "gfm": None,
        "elevation": None,
        "rivers": None,
        "precip_lattice": None,
        "unavailable": [],
    }
    raw_hits = list(RAW_DIR.glob("*.tif"))
    if download_gfm or raw_hits:
        out["gfm"] = acquire_v2(download=download_gfm) if download_gfm else index_local_v2()
    else:
        out["gfm"] = {"n_kept": 0, "reason": "No local Equi7 GeoTIFFs."}
        out["unavailable"].append("gfm_raw")
    if not fetch_features:
        return out
    try:
        from floodlens.ml.spatial.elevation_lattice import fetch_elevation

        elev = fetch_elevation()
        out["elevation"] = {
            "n_aois": len((elev or {}).get("aois") or {}),
            "source": (elev or {}).get("source"),
            "status": "OBSERVED" if (elev or {}).get("aois") else "UNAVAILABLE",
        }
        if not out["elevation"]["n_aois"]:
            out["unavailable"].append("elevation_lattice")
    except Exception as exc:
        out["elevation"] = {"status": "UNAVAILABLE", "reason": str(exc)}
        out["unavailable"].append("elevation_lattice")
    try:
        from floodlens.ml.spatial.river_features import fetch_rivers

        rivers = fetch_rivers()
        out["rivers"] = {
            "source": rivers.get("source"),
            "n_aois": len(rivers.get("aois") or {}),
            "status": "OBSERVED" if rivers.get("aois") else "UNAVAILABLE",
            "license": rivers.get("license"),
        }
        if not out["rivers"]["n_aois"]:
            out["unavailable"].append("rivers")
    except Exception as exc:
        out["rivers"] = {"status": "UNAVAILABLE", "reason": str(exc)}
        out["unavailable"].append("rivers")
    try:
        from floodlens.ml.spatial.precip_lattice import fetch_lattice

        lattice = fetch_lattice()
        out["precip_lattice"] = {
            "source": lattice.get("source"),
            "n_aois": len(lattice.get("aois") or {}),
            "kind": lattice.get("kind"),
            "status": lattice.get("kind") or "UNAVAILABLE",
        }
        if not out["precip_lattice"]["n_aois"]:
            out["unavailable"].append("precip_lattice")
    except Exception as exc:
        out["precip_lattice"] = {"status": "UNAVAILABLE", "reason": str(exc)}
        out["unavailable"].append("precip_lattice")
    return out


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


def evaluate_phase65a(processed_dir: Optional[Path] = None) -> dict:
    """Dataset quality only. No GBDT, no U-Net, no registry promotion."""
    samples, meta = build_spatial_samples_v2(processed_dir=processed_dir)
    samples = [s for s in samples if not (s.extra or {}).get("synthetic") and s.label_kind != "SIMULATED"]
    inv = inventory(samples) if samples else {
        "n_independent_events": 0,
        "verdict": "INSUFFICIENT FOR VALIDATION",
        "cities": [],
        "pixels": {},
    }
    audit = audit_channels(samples) if samples else {"channels": {}, "n_spatial": 0, "cnn_allowed": False}
    events = event_records(samples) if samples else []
    coverage = coverage_summary(samples) if samples else {"regions": [], "n_regions": 0}
    manifests = {}
    if samples:
        manifests = write_split_manifests(samples, SPLITS_DIR)
    gates_af = evaluate_gates_af(samples, audit, manifests_written=bool(manifests))
    gate0 = evaluate_gate0(samples, audit)
    samples_per_event = {}
    for row in events:
        samples_per_event[row["event_id"]] = int((row.get("provenance") or {}).get("n_tiles") or 0)
    catalog = catalog_from_audit(audit)
    (SPATIAL_DIR / "gfm" / "processed_v2").mkdir(parents=True, exist_ok=True)
    (SPATIAL_DIR / "gfm" / "processed_v2" / "feature_catalog.json").write_text(
        json.dumps(_jsonable({"channels": catalog, "summary": classify_summary(audit)}), indent=2),
        encoding="utf-8",
    )
    (SPATIAL_DIR / "gfm" / "processed_v2" / "events.json").write_text(
        json.dumps(_jsonable(events), indent=2), encoding="utf-8"
    )
    (SPATIAL_DIR / "gfm" / "processed_v2" / "coverage.json").write_text(
        json.dumps(_jsonable(coverage), indent=2), encoding="utf-8"
    )
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
        }
        for s in samples
    ]
    (SPATIAL_DIR / "gfm" / "processed_v2" / "sample_manifest.json").write_text(
        json.dumps({"n": len(sample_manifest), "samples": sample_manifest}, indent=2),
        encoding="utf-8",
    )
    pixels = inv.get("pixels") or {}
    af = (gates_af.get("gates") or {})
    training_entry = all(af.get(k, {}).get("status") == "PASS" for k in ("A", "B", "C", "D", "E", "F"))
    recommendation = (
        "DATASET READY FOR MODEL EVALUATION — MODEL TRAINING REQUIRES SEPARATE APPROVAL."
        if training_entry
        else "DATASET STILL INSUFFICIENT — DO NOT TRAIN."
    )
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "phase": "6.5A",
        "model_id": SPATIAL_MODEL_ID_V2,
        "dataset_version": SPATIAL_DATASET_VERSION_V2,
        "dataset": meta,
        "inventory": inv,
        "events": events,
        "coverage": coverage,
        "channel_audit": audit,
        "feature_catalog": catalog,
        "channel_counts": _channel_counts(audit),
        "gate0": gate0,
        "gates_af": gates_af,
        "splits": manifests,
        "cnn_trained": False,
        "gbdt_trained": False,
        "unet_trained": False,
        "status": "NOT_TRAINED",
        "public_status": "NOT_TRAINED",
        "catalog_status": "NOT_VALIDATED",
        "promoted_to_validated": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
        "statistics": {
            "n_independent_events": inv.get("n_independent_events"),
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
            "samples_per_event": samples_per_event,
        },
        "recommendation": recommendation,
        "note": (
            "Phase 6.5A is dataset expansion and quality gates only. "
            "No model was trained. Spatial AI remains NOT_VALIDATED. "
            "POST /api/v1/forecast/ai-spatial stays UNAVAILABLE."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
    (SPATIAL_DIR / "gfm" / "processed_v2" / "gates_af.json").write_text(
        json.dumps(_jsonable(gates_af), indent=2), encoding="utf-8"
    )
    return report
