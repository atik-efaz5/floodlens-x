"""Classification metrics. Accuracy is intentionally not computed."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def _as_1d(y) -> np.ndarray:
    return np.asarray(y, dtype=np.float64).reshape(-1)


def brier(y_true, y_prob) -> float:
    y = _as_1d(y_true)
    p = np.clip(_as_1d(y_prob), 0.0, 1.0)
    if y.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def brier_skill(y_true, y_prob, climatology: Optional[float] = None) -> float:
    y = _as_1d(y_true)
    if y.size == 0:
        return float("nan")
    clim = float(np.mean(y) if climatology is None else climatology)
    bs = brier(y, y_prob)
    bs_ref = brier(y, np.full_like(y, clim))
    if bs_ref < 1e-12:
        return 0.0
    return float(1.0 - bs / bs_ref)


def auroc(y_true, y_prob) -> float:
    y = _as_1d(y_true)
    p = _as_1d(y_prob)
    pos = p[y > 0.5]
    neg = p[y <= 0.5]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    # Mann–Whitney U / Wilcoxon: P(pos > neg) + 0.5 P(tie)
    greater = 0.0
    for pv in pos:
        greater += float(np.sum(neg < pv) + 0.5 * np.sum(neg == pv))
    return float(greater / (pos.size * neg.size))


def average_precision(y_true, y_prob) -> float:
    y = _as_1d(y_true)
    p = _as_1d(y_prob)
    n_pos = float(np.sum(y > 0.5))
    if y.size == 0 or n_pos == 0:
        return float("nan")
    order = np.argsort(-p, kind="mergesort")
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1.0 - y_sorted)
    precision = tp / np.maximum(tp + fp, 1e-12)
    recall = tp / n_pos
    recall = np.concatenate([[0.0], recall])
    precision = np.concatenate([[precision[0] if precision.size else 1.0], precision])
    return float(np.sum((recall[1:] - recall[:-1]) * precision[1:]))


def confusion_at_threshold(y_true, y_prob, threshold: float) -> Dict[str, float]:
    y = _as_1d(y_true) > 0.5
    pred = _as_1d(y_prob) >= threshold
    tp = float(np.sum(y & pred))
    fp = float(np.sum(~y & pred))
    fn = float(np.sum(y & ~pred))
    tn = float(np.sum(~y & ~pred))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    csi = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "csi": csi,
        "f1": f1,
        "threshold": float(threshold),
    }


def recall_at_precision(y_true, y_prob, min_precision: float = 0.7) -> Dict[str, float]:
    y = _as_1d(y_true)
    p = _as_1d(y_prob)
    if y.size == 0:
        return {"recall": float("nan"), "threshold": float("nan"), "precision_target": min_precision}
    order = np.argsort(-p, kind="mergesort")
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1.0 - y_sorted)
    precision = tp / np.maximum(tp + fp, 1e-12)
    n_pos = max(float(np.sum(y > 0.5)), 1.0)
    recall = tp / n_pos
    ok = np.where(precision >= min_precision)[0]
    if ok.size == 0:
        return {"recall": 0.0, "threshold": 1.0, "precision_target": min_precision}
    i = int(ok[-1])
    return {
        "recall": float(recall[i]),
        "threshold": float(p[order][i]),
        "precision_target": min_precision,
    }


def choose_threshold(y_true, y_prob, grid=None) -> float:
    grid = np.linspace(0.05, 0.95, 19) if grid is None else grid
    best_t, best = 0.5, -1.0
    for t in grid:
        f1 = confusion_at_threshold(y_true, y_prob, float(t))["f1"]
        if f1 > best:
            best, best_t = f1, float(t)
    return best_t


def summarize(y_true, y_prob, threshold: float, climatology: Optional[float] = None) -> dict:
    y = _as_1d(y_true)
    return {
        "n": int(y.size),
        "prevalence": float(np.mean(y)) if y.size else float("nan"),
        "auprc": average_precision(y_true, y_prob),
        "auroc": auroc(y_true, y_prob),
        "brier": brier(y_true, y_prob),
        "bss": brier_skill(y_true, y_prob, climatology=climatology),
        "recall_at_precision_0.7": recall_at_precision(y_true, y_prob, 0.7),
        "operating_point": confusion_at_threshold(y_true, y_prob, threshold),
        "accuracy_claim": None,
    }
