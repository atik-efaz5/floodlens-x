"""Train spatial baselines. U-Net is not fit here unless Phase 6 Gate 1 passed."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np

from floodlens.ml.spatial.baselines import evaluate_spatial_baselines, fit_spatial_baselines
from floodlens.ml.spatial.builder import build_spatial_samples
from floodlens.ml.spatial.schema import SPATIAL_DATASET_VERSION, SPATIAL_DIR, SPATIAL_MODEL_ID
from floodlens.ml.spatial.splits import by_split
from floodlens.ml.uncertainty import fit_conformal

SPATIAL_CHECKPOINT = SPATIAL_DIR / "checkpoint.json"


def _run_id(payload: str) -> str:
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"spatial-{digest}"


def train_spatial(
    processed_dir: Optional[Path] = None,
    epochs: int = 6,
    path: Optional[Path] = None,
    fit_cnn: bool = False,
) -> dict:
    del epochs  # CNN not trained from this entrypoint
    samples, meta = build_spatial_samples(processed_dir=processed_dir)
    ckpt_path = Path(path or SPATIAL_CHECKPOINT)
    if not samples:
        return {
            "status": "NOT_TRAINED",
            "reason": meta.get("reason") or "no spatial samples",
            "dataset": meta,
            "model_id": SPATIAL_MODEL_ID,
        }
    train = by_split(samples, "train")
    val = by_split(samples, "val")
    test = by_split(samples, "test")
    if not train:
        return {
            "status": "NOT_TRAINED",
            "reason": "no train-split spatial maps (need GFM coverage in ≤2018)",
            "dataset": meta,
            "model_id": SPATIAL_MODEL_ID,
        }
    fitted = fit_spatial_baselines(samples)
    cnn_reason = (
        "CNN not trained. Phase 6 requires Gate 0/1 (spatial features + GBDT > persistence). "
        f"fit_cnn={fit_cnn} is ignored here; use floodlens.ml.spatial.phase6."
    )
    gbdt = fitted["predict"]["pixel_gbdt"]
    metrics = {
        "val": evaluate_spatial_baselines(samples, fitted, "val") if val else {"n_maps": 0},
        "test": evaluate_spatial_baselines(samples, fitted, "test") if test else {"n_maps": 0},
        "val_unet": {"n": 0, "skipped": cnn_reason},
        "test_unet": {"n": 0, "skipped": cnn_reason},
        "label_kind": meta.get("label_kind"),
        "accuracy_claim": None,
        "cnn_trained": False,
        "cnn_reason": cnn_reason,
    }
    y_bits: List[float] = []
    p_bits: List[float] = []
    for sample in val or train[: max(1, len(train) // 4)]:
        y = sample.y_binary().reshape(-1)
        p = gbdt(sample).reshape(-1)
        mask = np.isfinite(y)
        y_bits.extend(y[mask].tolist())
        p_bits.extend(p[mask].tolist())
    conformal = fit_conformal(np.asarray(y_bits), np.asarray(p_bits))
    run_id = _run_id(json.dumps({"n": len(samples), "v": SPATIAL_DATASET_VERSION}, sort_keys=True))
    ckpt = {
        "model_id": SPATIAL_MODEL_ID,
        "run_id": run_id,
        "dataset_version": SPATIAL_DATASET_VERSION,
        "status": "TRAINED",
        "label_kind": meta.get("label_kind"),
        "horizon_hours": meta.get("horizon_hours"),
        "unet": None,
        "cnn_trained": False,
        "cnn_reason": cnn_reason,
        "conformal": conformal.to_dict(),
        "rain_threshold_mm": fitted["rain_threshold_mm"],
        "logistic": fitted["logistic"].to_dict(),
        "boosting": fitted["boosting"].to_dict(),
        "metrics": metrics,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "note": (
            "Baselines only. Public catalog stays NOT_TRAINED until Gate 2 VALIDATED. "
            "8-day GFM horizon only. Not a 6/12/24 h forecast."
        ),
        "accuracy_claim": None,
        "comparable_to_physics": False,
    }
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    ckpt_path.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")
    from floodlens.ml.spatial.registry_spatial import mark_spatial_trained

    rel = "src/floodlens/application/data/ml/spatial/checkpoint.json"
    mark_spatial_trained(run_id, rel, SPATIAL_DATASET_VERSION)
    return ckpt
