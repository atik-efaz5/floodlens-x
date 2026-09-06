"""Feature matrices. Train-split statistics only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample

FEATURE_NAMES = [f"precip_h{i}" for i in range(LOOKBACK_HOURS)] + [
    "antecedent_24h",
    "antecedent_72h",
    "forecast_to_h",
    "forecast_present",
    "dem_min",
    "dem_mean",
    "dem_p10",
    "dem_present",
    "q_last",
    "q_present",
    "month_sin",
    "month_cos",
    "horizon_hours",
    "precip_1h",
    "precip_3h",
    "precip_6h",
    "precip_12h",
    "precip_48h",
]


def _month_from_issue(issue_time: str) -> int:
    return int(issue_time[5:7])


def vectorize(sample: ForecastSample) -> np.ndarray:
    precip = list(sample.x_precip_hourly)
    if len(precip) != LOOKBACK_HOURS:
        precip = (precip + [0.0] * LOOKBACK_HOURS)[:LOOKBACK_HOURS]
    dem = sample.x_dem_stats or {}
    dem_present = 1.0 if sample.x_dem_stats else 0.0
    q = sample.x_glofas_q_lookback or []
    q_last = float(q[-1]) if q and q[-1] is not None else 0.0
    q_present = 1.0 if q and q[-1] is not None else 0.0
    windows = (sample.extra or {}).get("precip_windows") or {}
    def _win(hours: int, fallback: float = 0.0) -> float:
        raw = windows.get(hours, windows.get(str(hours)))
        if raw is not None:
            return float(raw)
        if hours <= LOOKBACK_HOURS:
            return float(sum(precip[-hours:]))
        return fallback

    month = _month_from_issue(sample.issue_time)
    forecast = sample.x_precip_forecast_to_h
    row = precip + [
        float(sample.x_antecedent_24h or 0.0),
        float(sample.x_antecedent_72h or 0.0),
        float(forecast or 0.0),
        1.0 if forecast is not None else 0.0,
        float(dem.get("min") or 0.0),
        float(dem.get("mean") or 0.0),
        float(dem.get("p10") or 0.0),
        dem_present,
        np.log1p(max(q_last, 0.0)),
        q_present,
        np.sin(2 * np.pi * month / 12.0),
        np.cos(2 * np.pi * month / 12.0),
        float(sample.horizon_hours),
        _win(1),
        _win(3),
        _win(6),
        _win(12),
        _win(48, float(sample.x_antecedent_72h or 0.0)),
    ]
    return np.asarray(row, dtype=np.float64)


def sequence_precip(sample: ForecastSample) -> np.ndarray:
    precip = list(sample.x_precip_hourly)
    if len(precip) != LOOKBACK_HOURS:
        precip = (precip + [0.0] * LOOKBACK_HOURS)[:LOOKBACK_HOURS]
    return np.asarray(precip, dtype=np.float64).reshape(LOOKBACK_HOURS, 1)


@dataclass
class TrainScaler:
    mean: np.ndarray
    std: np.ndarray

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean) / self.std

    def to_dict(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_dict(cls, payload: dict) -> "TrainScaler":
        return cls(mean=np.asarray(payload["mean"]), std=np.asarray(payload["std"]))


def fit_scaler(X: np.ndarray) -> TrainScaler:
    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    return TrainScaler(mean=mean, std=std)


def matrix(
    samples: Sequence[ForecastSample],
    track: str = "A",
    scaler: Optional[TrainScaler] = None,
) -> Tuple[np.ndarray, np.ndarray, List[ForecastSample]]:
    kept: List[ForecastSample] = []
    rows: List[np.ndarray] = []
    labels: List[int] = []
    for sample in samples:
        if sample.lookback_complete_frac < 0.80:
            continue
        if track == "A":
            if sample.y_track_a is None:
                continue
            y = int(sample.y_track_a)
        else:
            if not sample.y_track_b_available or sample.y_track_b is None:
                continue
            y = int(sample.y_track_b)
        kept.append(sample)
        rows.append(vectorize(sample))
        labels.append(y)
    if not rows:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,)), []
    X = np.vstack(rows)
    y = np.asarray(labels, dtype=np.int32)
    if scaler is not None:
        X = scaler.transform(X)
    return X, y, kept
