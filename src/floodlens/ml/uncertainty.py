"""Quantile residuals and split-conformal 80% intervals on validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class ConformalCalibrator:
    q80: float
    q10: float
    q90: float
    alpha: float = 0.2
    kind: str = "conformal"

    def interval(self, probability: float) -> dict:
        p = float(np.clip(probability, 0.0, 1.0))
        low = float(np.clip(p - self.q80, 0.0, 1.0))
        high = float(np.clip(p + self.q80, 0.0, 1.0))
        return {
            "probability": p,
            "interval": [low, high],
            "q10": float(np.clip(p - self.q90, 0.0, 1.0)),
            "q50": p,
            "q90": float(np.clip(p + self.q90, 0.0, 1.0)),
            "confidence_kind": "conformal",
            "coverage_target": 1.0 - self.alpha,
        }

    def to_dict(self) -> dict:
        return {"q80": self.q80, "q10": self.q10, "q90": self.q90, "alpha": self.alpha, "kind": self.kind}

    @classmethod
    def from_dict(cls, payload: dict) -> "ConformalCalibrator":
        return cls(
            q80=float(payload["q80"]),
            q10=float(payload.get("q10", payload["q80"])),
            q90=float(payload.get("q90", payload["q80"])),
            alpha=float(payload.get("alpha", 0.2)),
        )


def fit_conformal(y_true: np.ndarray, y_prob: np.ndarray, alpha: float = 0.2) -> ConformalCalibrator:
    resid = np.abs(np.asarray(y_true, dtype=np.float64) - np.asarray(y_prob, dtype=np.float64))
    if resid.size == 0:
        return ConformalCalibrator(q80=0.5, q10=0.5, q90=0.5, alpha=alpha)
    q80 = float(np.quantile(resid, 1.0 - alpha))
    q10 = float(np.quantile(resid, 0.10))
    q90 = float(np.quantile(resid, 0.90))
    return ConformalCalibrator(q80=q80, q10=q10, q90=q90, alpha=alpha)


def coverage(y_true: np.ndarray, y_prob: np.ndarray, calibrator: ConformalCalibrator) -> float:
    y = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_prob, dtype=np.float64)
    if y.size == 0:
        return float("nan")
    hits = 0
    for yi, pi in zip(y, p):
        interval = calibrator.interval(float(pi))["interval"]
        if interval[0] <= yi <= interval[1]:
            hits += 1
    return float(hits / y.size)
