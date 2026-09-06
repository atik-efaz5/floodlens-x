"""Spatial map metrics: IoU/Dice/CSI, event-level, uncertainty, conformal coverage.

Accuracy is not reported. Unknown pixels are dropped, never scored as dry.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from floodlens.ml.evaluate import average_precision, auroc, brier, confusion_at_threshold, summarize
from floodlens.ml.spatial.schema import UNKNOWN, SpatialForecastSample
from floodlens.ml.uncertainty import ConformalCalibrator, coverage as conformal_coverage


def _valid_yp(sample: SpatialForecastSample, prob: np.ndarray):
    y = sample.y_binary()
    p = np.asarray(prob, dtype=np.float64)
    mask = np.isfinite(y) & np.isfinite(p)
    return y[mask], p[mask]


def dice_at_threshold(y_true, y_prob, threshold: float = 0.5) -> float:
    cm = confusion_at_threshold(y_true, y_prob, threshold)
    num = 2.0 * cm["tp"]
    den = 2.0 * cm["tp"] + cm["fp"] + cm["fn"]
    return float(num / den) if den else 0.0


def map_metrics(y_true, y_prob, threshold: float = 0.5) -> dict:
    row = summarize(y_true, y_prob, threshold=threshold)
    cm = row["operating_point"]
    row["iou"] = cm["csi"]
    row["dice"] = dice_at_threshold(y_true, y_prob, threshold)
    row["csi"] = cm["csi"]
    row["recall"] = cm["recall"]
    row["precision"] = cm["precision"]
    row["accuracy_claim"] = None
    return row


def event_metrics(
    samples: Sequence[SpatialForecastSample],
    pred_fn: Callable[[SpatialForecastSample], np.ndarray],
    threshold: float = 0.5,
) -> dict:
    per = []
    for sample in samples:
        y, p = _valid_yp(sample, pred_fn(sample))
        if y.size == 0:
            continue
        row = map_metrics(y, p, threshold=threshold)
        row["event_id"] = (sample.extra or {}).get("event_id")
        row["city_id"] = sample.city_id
        row["valid_at"] = sample.valid_at
        row["n_flood"] = int(np.sum(np.asarray(sample.y_flood) == 1))
        per.append(row)
    if not per:
        return {"n_maps": 0, "events": [], "summary": {}, "worst": None, "accuracy_claim": None}

    def _agg(key):
        vals = [r[key] for r in per if r.get(key) is not None and np.isfinite(r[key])]
        if not vals:
            return {"mean": None, "median": None, "std": None}
        arr = np.asarray(vals, dtype=np.float64)
        return {"mean": float(np.mean(arr)), "median": float(np.median(arr)), "std": float(np.std(arr))}

    worst = min(per, key=lambda r: (r.get("iou") if r.get("iou") is not None and np.isfinite(r.get("iou")) else 1.0))
    return {
        "n_maps": len(per),
        "events": per,
        "summary": {k: _agg(k) for k in ("iou", "dice", "recall", "precision", "auprc")},
        "worst": {
            "event_id": worst.get("event_id"),
            "city_id": worst.get("city_id"),
            "valid_at": worst.get("valid_at"),
            "iou": worst.get("iou"),
            "dice": worst.get("dice"),
        },
        "accuracy_claim": None,
    }


def hard_case_masks(sample: SpatialForecastSample) -> Dict[str, bool]:
    y = np.asarray(sample.y_flood)
    n = y.size
    n_flood = int(np.sum(y == 1))
    n_unk = int(np.sum(y == UNKNOWN))
    rain = float(sample.x_antecedent_24h or 0.0)
    return {
        "weak_flood": 0 < n_flood <= 20,
        "small_flood": 0 < n_flood <= 50,
        "nodata_heavy": (n_unk / n) >= 0.5 if n else False,
        "low_rainfall": rain < 5.0,
        "rare_event": n_flood > 0 and (n_flood / max(int(np.sum(y != UNKNOWN)), 1)) < 0.05,
    }


def subset_metrics(
    samples: Sequence[SpatialForecastSample],
    pred_fn: Callable[[SpatialForecastSample], np.ndarray],
    flag: str,
    threshold: float = 0.5,
) -> dict:
    chosen = [s for s in samples if hard_case_masks(s).get(flag)]
    ys, ps = [], []
    for sample in chosen:
        y, p = _valid_yp(sample, pred_fn(sample))
        if y.size:
            ys.append(y)
            ps.append(p)
    if not ys:
        return {"flag": flag, "n_maps": 0, "accuracy_claim": None}
    row = map_metrics(np.concatenate(ys), np.concatenate(ps), threshold=threshold)
    row["flag"] = flag
    row["n_maps"] = len(chosen)
    return row


def uncertainty_error_correlation(
    samples: Sequence[SpatialForecastSample],
    prob_fn: Callable[[SpatialForecastSample], np.ndarray],
    width_fn: Callable[[SpatialForecastSample], np.ndarray],
) -> dict:
    """High interval width should trend with |p-y| if uncertainty is informative."""
    widths = []
    errs = []
    for sample in samples:
        yb = sample.y_binary()
        pb = np.asarray(prob_fn(sample), dtype=np.float64)
        wb = np.asarray(width_fn(sample), dtype=np.float64)
        m = np.isfinite(yb) & np.isfinite(pb) & np.isfinite(wb)
        if not np.any(m):
            continue
        widths.append(wb[m].reshape(-1))
        errs.append(np.abs(pb[m] - yb[m]).reshape(-1))
    if not widths:
        return {"n": 0, "rank_correlation": None, "informative": False, "note": "no valid pixels"}
    w = np.concatenate(widths)
    e = np.concatenate(errs)
    wr = np.argsort(np.argsort(w))
    er = np.argsort(np.argsort(e))
    corr = float(np.corrcoef(wr, er)[0, 1]) if w.size > 2 else float("nan")
    return {
        "n": int(w.size),
        "rank_correlation": corr,
        "informative": bool(np.isfinite(corr) and corr > 0.1),
        "note": (
            "Positive rank correlation means wider conformal bands where |p-y| is larger. "
            "If not informative, do not present the uncertainty map as trustworthy confidence."
        ),
    }


def conformal_heldout(
    samples: Sequence[SpatialForecastSample],
    pred_fn: Callable[[SpatialForecastSample], np.ndarray],
    calibrator: ConformalCalibrator,
) -> dict:
    ys, ps = [], []
    widths = []
    for sample in samples:
        y, p = _valid_yp(sample, pred_fn(sample))
        if y.size == 0:
            continue
        ys.append(y)
        ps.append(p)
        for pi in p:
            interval = calibrator.interval(float(pi))["interval"]
            widths.append(interval[1] - interval[0])
    if not ys:
        return {"n": 0, "target_coverage": 1.0 - calibrator.alpha, "empirical_coverage": None}
    y = np.concatenate(ys)
    p = np.concatenate(ps)
    emp = conformal_coverage(y, p, calibrator)
    return {
        "n": int(y.size),
        "target_coverage": 1.0 - calibrator.alpha,
        "empirical_coverage": emp,
        "mean_interval_width": float(np.mean(widths)) if widths else None,
        "claim_80_percent": False,
        "note": "Do not claim 80% coverage unless empirical_coverage is measured on this test split.",
    }
