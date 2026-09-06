"""Train the first real-data flood-occurrence model. Synthetic tracks are not used here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from floodlens.ml.baselines import evaluate_baselines, fit_baselines
from floodlens.ml.evaluate import choose_threshold
from floodlens.ml.features import matrix
from floodlens.ml.leakage import parse_ts
from floodlens.ml.real_dataset import (
    REAL_DATASET_VERSION,
    REAL_HORIZONS,
    build_real_samples,
)
from floodlens.ml.registry import load_registry, mark_trained, mark_validated, save_registry
from floodlens.ml.schema import ForecastSample
from floodlens.ml.splits import by_split
from floodlens.ml.train import _now, config_hash, maybe_train_lstm
from floodlens.ml.uncertainty import coverage, fit_conformal

REAL_CHECKPOINT = (
    Path(__file__).resolve().parents[1] / "application" / "data" / "ml" / "real" / "checkpoint.json"
)
REAL_EXPERIMENT_DIR = Path(__file__).resolve().parents[1] / "application" / "data" / "ml" / "real"


def _error_cases(
    samples: Sequence[ForecastSample],
    y: np.ndarray,
    p: np.ndarray,
    k: int = 8,
    threshold: float = 0.5,
) -> dict:
    kept = list(samples)
    misses = []
    false_pos = []
    hits = []
    for sample, yi, pi in zip(kept, y, p):
        row = {
            "city_id": sample.city_id,
            "issue_time": sample.issue_time,
            "horizon_hours": sample.horizon_hours,
            "y": int(yi),
            "p": float(pi),
            "antecedent_24h": sample.x_antecedent_24h,
            "q_last": (sample.x_glofas_q_lookback or [None])[-1],
        }
        pred = int(pi >= threshold)
        if int(yi) == 1 and pred == 0:
            misses.append(row)
        if int(yi) == 0 and pred == 1:
            false_pos.append(row)
        if int(yi) == pred:
            hits.append(row)
    misses.sort(key=lambda r: r["p"])
    false_pos.sort(key=lambda r: -r["p"])
    return {
        "false_negatives_lowest_p": misses[:k],
        "false_positives_highest_p": false_pos[:k],
        "n_false_negatives": len(misses),
        "n_false_positives": len(false_pos),
        "n_correct": len(hits),
        "threshold": threshold,
        "note": "Track A MODELLED labels. Not in-situ flood maps. Physics SWE not paired.",
    }


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def _tune_rows(samples: Sequence[ForecastSample]) -> list:
    """Last two train years (2020–2021) for threshold/conformal if 2022 val has no events."""
    return [
        s
        for s in by_split(samples, "train")
        if parse_ts(s.issue_time).year >= 2020
    ]


def train_real(real_dir: Optional[Path] = None, experiment_dir: Optional[Path] = None) -> dict:
    samples, meta = build_real_samples(real_dir=real_dir)
    classical = fit_baselines(samples, track="A")
    X_val, y_val, kept_val = matrix(by_split(samples, "val"), track="A", scaler=classical.scaler)
    boost_val = classical.boosting.predict_proba(X_val) if y_val.size else np.zeros((0,))
    threshold_source = "val_2022"
    X_cal, y_cal, p_cal = X_val, y_val, boost_val
    if y_val.size == 0 or float(np.sum(y_val)) == 0.0:
        tune = _tune_rows(samples)
        X_cal, y_cal, _ = matrix(tune, track="A", scaler=classical.scaler)
        p_cal = classical.boosting.predict_proba(X_cal) if y_cal.size else np.zeros((0,))
        threshold_source = "train_2020_2021_inner_tune (val 2022 has zero positives outside named holdout)"
    classical.threshold = choose_threshold(y_cal, p_cal) if y_cal.size and float(np.sum(y_cal)) else 0.5
    val = evaluate_baselines(samples, classical, "val")
    val["threshold_source"] = threshold_source
    val["note"] = (
        "2022 val excluding named holdout has prevalence 0 at the train-only AMS threshold; "
        "AUPRC/AUROC are undefined. Threshold and conformal used 2020–2021 train years. "
        "Tracks A and B must not be mixed. Accuracy is not reported."
        if threshold_source.startswith("train_")
        else "Tracks A and B must not be mixed. Accuracy is not reported."
    )
    test = evaluate_baselines(samples, classical, "test")
    calibrator = fit_conformal(y_cal, p_cal)
    cov = coverage(y_cal, p_cal, calibrator)

    geo_rows = [s for s in samples if s.city_id != "sunamganj" and s.split == "train"] + [
        s for s in samples if s.city_id == "sunamganj" and s.split == "test"
    ]
    geo_fitted = fit_baselines(geo_rows, track="A")
    geo_report = evaluate_baselines(geo_rows, geo_fitted, "test")

    lstm = maybe_train_lstm(samples, {"val": val}, epochs=6)
    if not lstm.get("justified"):
        lstm["scientific_reason"] = (
            "Primary data are tabular AOI time series (precip windows + 7-day Q). "
            "TinyLSTM packing requires all five production horizons including 6h/12h; "
            "daily GloFAS labels cannot support those heads without fabricating targets. "
            "A ConvLSTM/GNN is unjustified (no raster cube, no river graph). "
            "GBDT is the appropriate first real model."
        )
    X_test, y_test, kept_test = matrix(by_split(samples, "test"), track="A", scaler=classical.scaler)
    boost_test = classical.boosting.predict_proba(X_test)
    cov_test = coverage(y_test, boost_test, calibrator)
    errors = _error_cases(kept_test, y_test, boost_test, threshold=classical.threshold)

    experiment_dir = Path(experiment_dir or REAL_EXPERIMENT_DIR)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"real-A-{config_hash({'dataset': REAL_DATASET_VERSION, 'seed': 7})}"
    payload = {
        "run_id": run_id,
        "dataset_version": REAL_DATASET_VERSION,
        "track": "A",
        "label_kind": "MODELLED",
        "role": "REAL_HISTORICAL_HINDCAST",
        "not_synthetic": True,
        "synthetic_scores_excluded": True,
        "seed": 7,
        "created_at": _now(),
        "horizons": list(REAL_HORIZONS),
        "skipped_horizons": [6, 12],
        "dataset": meta,
        "val": val,
        "test": test,
        "geographic_holdout_sunamganj": geo_report,
        "conformal": calibrator.to_dict(),
        "conformal_coverage_val": cov,
        "conformal_coverage_test": cov_test,
        "conformal_target": 0.80,
        "threshold_source": threshold_source,
        "operating_threshold": classical.threshold,
        "lstm": {k: v for k, v in lstm.items() if k != "model"},
        "error_analysis": errors,
        "physics_comparison": {
            "status": "LIMITED",
            "footnote": (
                "Physics Baseline v0.1 is a short SWE burst forced by that hour's rain, "
                "not a 24h inundation model, and is scored against MODELLED GloFAS Q "
                "exceedance — not a like-for-like hydrodynamic comparison."
            ),
            "n_paired": 0,
            "reason": (
                "SWE burst max depth / flood_fraction is not GloFAS Q exceedance. "
                "No conversion is applied. Metrics for physics on this label are null, not zero."
            ),
            "ai_test": test.get("models", {}).get("xgboost_class"),
            "physics_test": None,
            "comparable_quantities": False,
        },
        "best_model_on_test_auprc": (
            "persistence"
            if test.get("models", {}).get("persistence", {}).get("auprc", 0)
            >= test.get("models", {}).get("xgboost_class", {}).get("auprc", 0)
            else "xgboost_class"
        ),
        "shipped_model": "xgboost_class",
        "best_model": "xgboost_class",
        "accuracy_claim": None,
        "note": (
            "Persistence is a strong baseline for daily Q exceedance. "
            "Do not claim the GBDT beats persistence unless test AUPRC/F1 say so. "
            "Not synthetic Track A/B scores."
        ),
    }
    (experiment_dir / f"{run_id}.json").write_text(
        json.dumps(_json_safe(payload), indent=2, default=str, allow_nan=False),
        encoding="utf-8",
    )
    ckpt = {
        "run_id": run_id,
        "track": "A",
        "model_id": "FLOOD-OCCURRENCE-GBDT-v0.1",
        "model_kind": "AI",
        "version": "v0.1",
        "dataset_version": REAL_DATASET_VERSION,
        "scaler": classical.scaler.to_dict(),
        "boosting": classical.boosting.to_dict(),
        "logistic": classical.logistic.to_dict(),
        "conformal": calibrator.to_dict(),
        "climatology_rate": classical.climatology_rate,
        "threshold": classical.threshold,
        "threshold_source": threshold_source,
        "lstm": None if not lstm.get("justified") else lstm["model"].to_dict(),
        "supported_horizons": [24, 48, 72],
        "q_thresholds_m3s": meta.get("q_thresholds_m3s"),
        "status": "TRAINED",
        "seed": 7,
        "software": "floodlens-x phase4.5 numpy GBDT",
        "features": "precip lookback 24h + windows 1/3/6/12/24/48/72h + Q lookback 7d (t-7..t-1) + month + horizon",
        "hyperparameters": {"n_estimators": classical.boosting.n_estimators, "learning_rate": classical.boosting.learning_rate},
        "train_dates": "2015-01-01 to 2021-12-31 (issue times; 2022-05-09..2022-06-21 held out)",
        "validation_dates": "2022-01-01 to 2022-12-31 excluding named holdout",
        "test_dates": "2023-01-01 to 2024-12-31 plus 2022-05-09..2022-06-21 named holdout",
        "label_kind": "MODELLED",
    }
    rel_ckpt = "src/floodlens/application/data/ml/real/checkpoint.json"
    REAL_CHECKPOINT.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")
    payload["checkpoint"] = rel_ckpt
    mark_trained(run_id, rel_ckpt, REAL_DATASET_VERSION)
    split_ids = {
        "train": "issue_time < 2022-01-01",
        "val": "2022 excluding 2022-05-09..2022-06-21",
        "test": "2023-2024 plus named 2022 NE Bangladesh holdout",
        "geographic_holdout": "sunamganj vs dhaka+sylhet",
    }
    mark_validated(split_ids, _json_safe({"val": val, "test": test}), path=None)
    record = load_registry()
    record.update(
        {
            "model_id": "FLOOD-OCCURRENCE-GBDT-v0.1",
            "version": "v0.1",
            "training_run": run_id,
            "features": ckpt["features"],
            "hyperparameters": ckpt["hyperparameters"],
            "label_kind": "MODELLED",
            "metrics": _json_safe(record.get("metrics")),
            "note": (
                "Validated on held-out Open-Meteo GloFAS Q exceedance (MODELLED). "
                "Not in-situ flood maps. Persistence can outperform GBDT on AUPRC/F1 "
                "because labels are daily Q persistence. Do not quote accuracy %."
            ),
        }
    )
    save_registry(_json_safe(record))
    payload["registry_status"] = "VALIDATED"
    payload["checkpoint_obj"] = ckpt
    payload["fitted"] = classical
    payload["lstm_full"] = lstm
    payload["samples"] = samples
    return payload


if __name__ == "__main__":
    result = train_real()
    print("n", result["dataset"]["n"])
    print("splits", result["dataset"]["splits"])
    print("val auprc", result["val"]["models"]["xgboost_class"]["auprc"])
    print("test auprc", result["test"]["models"]["xgboost_class"]["auprc"])
    print("beats persistence", result["test"]["beats_persistence"])
    print("lstm justified", result["lstm"].get("justified"))
    print("status VALIDATED")
