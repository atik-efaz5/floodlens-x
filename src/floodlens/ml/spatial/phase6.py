"""Phase 6 formulation: audit, gates, spatial baselines. Never promotes VALIDATED.

Does not train a U-Net. Does not invent 6–72 h labels. Does not touch the solver.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from floodlens.ml.spatial.baselines import evaluate_spatial_baselines, fit_spatial_baselines
from floodlens.ml.spatial.builder import build_spatial_samples_v2
from floodlens.ml.spatial.channel_audit import audit_channels, refuse_cnn
from floodlens.ml.spatial.events import inventory, same_event_in_train_and_test
from floodlens.ml.spatial.eval_spatial import event_metrics
from floodlens.ml.spatial.gates import cnn_refusal, evaluate_gate0, evaluate_gate1, evaluate_gate2
from floodlens.ml.spatial.schema import SPATIAL_DIR, SPATIAL_MODEL_ID_V2
from floodlens.ml.spatial.splits import by_split, geographic_split

REPORT_PATH = SPATIAL_DIR / "phase6_eval.json"


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


def _iou(row: Optional[dict]) -> Optional[float]:
    if not row:
        return None
    if row.get("iou") is not None:
        try:
            return float(row["iou"])
        except (TypeError, ValueError):
            pass
    op = row.get("operating_point") or {}
    if op.get("csi") is not None:
        try:
            return float(op["csi"])
        except (TypeError, ValueError):
            pass
    return None


def _geo_holdout(samples):
    train = [s for s in samples if geographic_split(s.city_id) == "train"]
    test = [s for s in samples if geographic_split(s.city_id) == "test"]
    return train, test


def evaluate_phase6(processed_dir: Optional[Path] = None) -> dict:
    samples, meta = build_spatial_samples_v2(processed_dir=processed_dir)
    inv = inventory(samples) if samples else {
        "n_independent_events": 0,
        "verdict": "INSUFFICIENT FOR VALIDATION",
        "cities": [],
    }
    audit = audit_channels(samples) if samples else {
        "channels": {},
        "n_spatial": 0,
        "min_spatial_required": 4,
        "cnn_allowed": False,
    }
    gate0 = evaluate_gate0(samples, audit)
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model_id": SPATIAL_MODEL_ID_V2,
        "dataset": meta,
        "inventory": inv,
        "channel_audit": audit,
        "gate0": gate0,
        "gate1": None,
        "gate2": None,
        "cnn_trained": False,
        "cnn_reason": refuse_cnn(audit) or "CNN skipped until Gate 1 (and Phase 6 still prefers GBDT).",
        "baselines": None,
        "status": "NOT_TRAINED",
        "public_status": "NOT_TRAINED",
        "catalog_status": "NOT_VALIDATED",
        "promoted_to_validated": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
        "target": {
            "definition": "P(cell flooded) from GFM ensemble extent, tau=0.25, unknown=255 never dry",
            "horizon_hours": 192,
            "supported_product_horizons": [192],
            "unavailable_horizons": [6, 12, 24, 48, 72],
            "unavailable_reason": "GFM scenes are not daily 6–72 h maps. Labels are not invented.",
        },
        "primary_model": "pixel_gbdt",
        "note": (
            "Phase 6 is formulation and gating. If Gate 0 fails: expand data. Do not train a U-Net. "
            "Catalog stays NOT_VALIDATED until Gate 2."
        ),
    }
    train = by_split(samples, "train") if samples else []
    val = by_split(samples, "val") if samples else []
    test = by_split(samples, "test") if samples else []
    gbdt_iou = None
    persist_iou = None
    n_train_events = 0
    if samples and train:
        fitted = fit_spatial_baselines(samples)
        report["baselines"] = {
            "val": evaluate_spatial_baselines(samples, fitted, "val") if val else {"n_maps": 0},
            "test": evaluate_spatial_baselines(samples, fitted, "test") if test else {"n_maps": 0},
            "note": "Diagnostic even if Gate 0 fails. Not a VALIDATED catalog claim.",
        }
        test_models = ((report["baselines"].get("test") or {}).get("models") or {})
        gbdt_iou = _iou(test_models.get("pixel_gbdt"))
        persist_iou = _iou(test_models.get("persistence"))
        rf_iou = _iou(test_models.get("pixel_rf"))
        report["headline_baselines"] = {
            "test_persistence_iou": persist_iou,
            "test_pixel_gbdt_iou": gbdt_iou,
            "test_pixel_rf_iou": rf_iou,
            "test_logistic_iou": _iou(test_models.get("pixel_logistic")),
            "test_conv_smooth_iou": _iou(test_models.get("conv_smooth")),
            "accuracy_claim": None,
        }
        n_train_events = len({(s.extra or {}).get("event_id") for s in train})
        geo_train, geo_test = _geo_holdout(samples)
        geo_iou = None
        saved_splits = [(s, s.split) for s in samples]
        if geo_test and geo_train:
            for s in geo_train:
                s.split = "train"
            for s in geo_test:
                s.split = "test"
            try:
                geo_fitted = fit_spatial_baselines(geo_train + geo_test)
                geo_rows = evaluate_spatial_baselines(geo_train + geo_test, geo_fitted, "test")
                geo_iou = _iou((geo_rows.get("models") or {}).get("pixel_gbdt"))
            finally:
                for s, split in saved_splits:
                    s.split = split
            report["geographic_holdout"] = {
                "n_train": len(geo_train),
                "n_test": len(geo_test),
                "pixel_gbdt_iou": geo_iou,
                "collapsed_to_zero": geo_iou is not None and geo_iou <= 0.0,
            }
        else:
            report["geographic_holdout"] = {
                "n_train": len(geo_train),
                "n_test": len(geo_test),
                "pixel_gbdt_iou": None,
            }
        if test:
            gbdt_fn = fitted["predict"]["pixel_gbdt"]
            report["event_metrics_test"] = event_metrics(test, gbdt_fn)
        report["leakage"] = {
            "same_event_train_test": same_event_in_train_and_test(samples),
        }
        # Uncertainty: omit until informative. Do not ship current conformal as confidence.
        report["uncertainty"] = {
            "omitted": True,
            "reason": "Phase 5.5 conformal was uninformative (rank corr ~0). Redesign after Gate 0.",
            "informative": False,
        }
    gate1 = evaluate_gate1(gate0, gbdt_iou, persist_iou, n_train_events)
    report["gate1"] = gate1
    report["cnn_reason"] = cnn_refusal(audit, gate1) or (
        "Gate 1 passed but Phase 6 still skips U-Net; pixel GBDT/RF is the v2 primary."
        if gate1.get("pass")
        else report["cnn_reason"]
    )
    geo_ok = bool((report.get("geographic_holdout") or {}).get("pixel_gbdt_iou") not in (None, 0.0))
    if (report.get("geographic_holdout") or {}).get("collapsed_to_zero"):
        geo_ok = False
    event_ok = bool(report.get("event_metrics_test"))
    gate2 = evaluate_gate2(
        gate1,
        event_metrics_ok=event_ok,
        geographic_holdout_not_zero=geo_ok,
        conformal_claim_80=False,
        uncertainty_informative=False,
        uncertainty_omitted=True,
    )
    report["gate2"] = gate2
    report["promoted_to_validated"] = False
    if gate2.get("pass"):
        report["note"] = (
            "Gate 2 criteria were met in this report, but Phase 6 still does not call "
            "mark_spatial_validated. An operator must promote after review."
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
    return report


def acquire_phase6(*, download_gfm: bool = False, fetch_features: bool = True) -> dict:
    """Index local GFM at 64×64 AOIs; optionally fetch elevation, rivers, precip lattice."""
    from floodlens.ml.spatial.acquire_gfm import RAW_DIR, TILE_ID, acquire, index_local_v2

    out = {"gfm": None, "elevation": None, "rivers": None, "precip_lattice": None}
    if download_gfm:
        acquire(download=True)
    raw_hits = list(RAW_DIR.glob(f"*{TILE_ID}.tif"))
    if raw_hits:
        out["gfm"] = index_local_v2()
        out["gfm_n_kept"] = out["gfm"].get("n_kept")
    else:
        out["gfm"] = {"n_kept": 0, "reason": "No local Equi7 product-tile GeoTIFFs."}
    if not fetch_features:
        return out
    from floodlens.ml.spatial.elevation_lattice import fetch_elevation
    from floodlens.ml.spatial.precip_lattice import fetch_lattice
    from floodlens.ml.spatial.river_features import fetch_rivers

    out["elevation"] = {"n_aois": len((fetch_elevation() or {}).get("aois") or {})}
    rivers = fetch_rivers()
    out["rivers"] = {
        "source": rivers.get("source"),
        "n_aois": len(rivers.get("aois") or {}),
    }
    lattice = fetch_lattice()
    out["precip_lattice"] = {
        "source": lattice.get("source"),
        "n_aois": len(lattice.get("aois") or {}),
        "kind": lattice.get("kind"),
    }
    return out
