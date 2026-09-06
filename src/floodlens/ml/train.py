"""Train, evaluate, and persist Phase 4 experiments. Does not set VALIDATED."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from floodlens.ml.baselines import HORIZON_WEIGHTS, FittedBaselines, evaluate_baselines, fit_baselines
from floodlens.ml.evaluate import average_precision
from floodlens.ml.features import matrix
from floodlens.ml.lstm import TinyLSTM, pack_issue_sequences
from floodlens.ml.schema import DATASET_VERSION, ForecastSample
from floodlens.ml.splits import by_split
from floodlens.ml.uncertainty import coverage, fit_conformal

DEFAULT_EXPERIMENT_DIR = Path(__file__).resolve().parents[3] / "data" / "ml" / "experiments"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def config_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def train_classical(samples: Sequence[ForecastSample], track: str = "A") -> dict:
    fitted = fit_baselines(samples, track=track)
    val = evaluate_baselines(samples, fitted, "val")
    test = evaluate_baselines(samples, fitted, "test")
    X_val, y_val, _ = matrix(by_split(samples, "val"), track=track, scaler=fitted.scaler)
    boost_val = fitted.boosting.predict_proba(X_val) if y_val.size else np.zeros((0,))
    calibrator = fit_conformal(y_val, boost_val)
    cov = coverage(y_val, boost_val, calibrator)
    return {
        "fitted": fitted,
        "val": val,
        "test": test,
        "conformal": calibrator,
        "conformal_coverage_val": cov,
        "track": track,
    }


def maybe_train_lstm(samples: Sequence[ForecastSample], classical: dict, epochs: int = 8) -> dict:
    """Train LSTM only as a comparison; ship only if val AUPRC beats boosting."""
    train = by_split(samples, "train")
    val = by_split(samples, "val")
    seq_tr, y_tr, _ = pack_issue_sequences(train)
    seq_va, y_va, _ = pack_issue_sequences(val)
    xgb_auprc = ((classical.get("val") or {}).get("models") or {}).get("xgboost_class", {}).get("auprc")
    result = {
        "trained": False,
        "justified": False,
        "reason": "insufficient sequences",
        "val_auprc": None,
        "xgboost_val_auprc": xgb_auprc,
        "headroom": None,
    }
    if seq_tr.shape[0] < 20 or seq_va.shape[0] < 8:
        return result
    # Cap sequences so CPU LSTM comparison stays minutes-or-less.
    seq_tr, y_tr = seq_tr[:240], y_tr[:240]
    seq_va, y_va = seq_va[:80], y_va[:80]
    model = TinyLSTM(hidden=8, seed=3)
    model.fit(seq_tr, y_tr, horizons=None, epochs=epochs, lr=0.08, batch_size=32)
    p_va = model.predict_proba_seq(seq_va).reshape(-1)
    y_flat = y_va.reshape(-1)
    auprc = average_precision(y_flat, p_va)
    headroom = None if xgb_auprc is None or np.isnan(auprc) else float(auprc - xgb_auprc)
    justified = bool(headroom is not None and headroom > 0.01)
    result.update(
        {
            "trained": True,
            "justified": justified,
            "reason": (
                "LSTM val AUPRC exceeds XGBoost-class by >0.01"
                if justified
                else "XGBoost-class already sufficient; LSTM not promoted"
            ),
            "val_auprc": auprc,
            "headroom": headroom,
            "n_train_sequences": int(seq_tr.shape[0]),
            "n_val_sequences": int(seq_va.shape[0]),
            "model": model,
        }
    )
    return result


def run_experiment(
    samples: Sequence[ForecastSample],
    track: str = "A",
    experiment_dir: Optional[Path] = None,
    seed: int = 7,
) -> dict:
    experiment_dir = Path(experiment_dir or DEFAULT_EXPERIMENT_DIR)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    classical = train_classical(samples, track=track)
    lstm = maybe_train_lstm(samples, classical)
    run_id = f"{track}-{config_hash({'seed': seed, 'dataset': DATASET_VERSION, 't': _now()})}"
    fitted: FittedBaselines = classical["fitted"]
    payload = {
        "run_id": run_id,
        "dataset_version": DATASET_VERSION,
        "track": track,
        "label_kind": "MODELLED" if track == "A" else "OBSERVED",
        "seed": seed,
        "created_at": _now(),
        "status": "TRAINED",
        "registry_status_if_published": "TRAINED",
        "validated": False,
        "note": (
            "Synthetic or local experiment. GET /models stays NOT_TRAINED until VALIDATED "
            "on a documented real split. Do not report accuracy %."
        ),
        "val": classical["val"],
        "test": classical["test"],
        "conformal": classical["conformal"].to_dict(),
        "conformal_coverage_val": classical["conformal_coverage_val"],
        "lstm": {k: v for k, v in lstm.items() if k != "model"},
        "horizon_weights": {str(k): v for k, v in HORIZON_WEIGHTS.items()},
        "beats_persistence_val": classical["val"].get("beats_persistence"),
        "config_hash": config_hash({"seed": seed, "track": track, "dataset": DATASET_VERSION}),
    }
    (experiment_dir / f"{run_id}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    ckpt = {
        "run_id": run_id,
        "track": track,
        "scaler": fitted.scaler.to_dict(),
        "boosting": fitted.boosting.to_dict(),
        "logistic": fitted.logistic.to_dict(),
        "conformal": classical["conformal"].to_dict(),
        "climatology_rate": fitted.climatology_rate,
        "threshold": fitted.threshold,
        "lstm": None if not lstm.get("justified") else lstm["model"].to_dict(),
        "dataset_version": DATASET_VERSION,
        "status": "TRAINED",
    }
    ckpt_path = experiment_dir / f"{run_id}.ckpt.json"
    ckpt_path.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")
    payload["checkpoint"] = str(ckpt_path)
    classical["run"] = payload
    classical["lstm"] = lstm
    classical["checkpoint"] = ckpt
    return classical


def list_experiments(experiment_dir: Optional[Path] = None) -> list:
    experiment_dir = Path(experiment_dir or DEFAULT_EXPERIMENT_DIR)
    if not experiment_dir.exists():
        return []
    rows = []
    for path in sorted(experiment_dir.glob("*.json")):
        if path.name.endswith(".ckpt.json"):
            continue
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return rows
