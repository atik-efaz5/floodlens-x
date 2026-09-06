"""Classical baselines: persistence, climatology, logistic, gradient boosting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from floodlens.ml.evaluate import summarize
from floodlens.ml.features import FEATURE_NAMES, TrainScaler, fit_scaler, matrix, vectorize
from floodlens.ml.schema import ForecastSample
from floodlens.ml.splits import by_split

HORIZON_WEIGHTS = {6: 0.8, 12: 1.0, 24: 1.5, 48: 1.2, 72: 1.1}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


@dataclass
class LogisticModel:
    name: str = "logistic"
    coef: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "LogisticModel":
        n, d = X.shape
        w = np.zeros(d + 1)
        Xb = np.c_[np.ones(n), X]
        sw = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)
        sw = sw / np.sum(sw)
        y = np.asarray(y, dtype=np.float64)
        lr = 0.4
        for _ in range(250):
            p = _sigmoid(Xb @ w)
            g = Xb.T @ (sw * (p - y))
            g[1:] += 2e-3 * w[1:]
            w = w - lr * g
        self.coef = w
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xb = np.c_[np.ones(X.shape[0]), X]
        return _sigmoid(Xb @ self.coef)

    def to_dict(self) -> dict:
        return {"name": self.name, "coef": None if self.coef is None else self.coef.tolist()}

    @classmethod
    def from_dict(cls, payload: dict) -> "LogisticModel":
        model = cls(name=payload.get("name", "logistic"))
        model.coef = None if payload.get("coef") is None else np.asarray(payload["coef"])
        return model


def _best_stump(X: np.ndarray, residual: np.ndarray, hessian: np.ndarray) -> dict:
    n, d = X.shape
    best = {"gain": -1.0, "feature": 0, "threshold": 0.0, "left": 0.0, "right": 0.0}
    for j in range(d):
        col = X[:, j]
        qs = np.quantile(col, [0.2, 0.4, 0.6, 0.8])
        for thr in np.unique(qs):
            left = col <= thr
            right = ~left
            if left.sum() < 8 or right.sum() < 8:
                continue
            sum_l = float(np.sum(residual[left]))
            sum_r = float(np.sum(residual[right]))
            h_l = float(np.sum(hessian[left])) + 1.0
            h_r = float(np.sum(hessian[right])) + 1.0
            gain = (sum_l * sum_l) / h_l + (sum_r * sum_r) / h_r
            if gain > best["gain"]:
                best = {
                    "gain": gain,
                    "feature": j,
                    "threshold": float(thr),
                    "left": sum_l / h_l,
                    "right": sum_r / h_r,
                }
    return best


@dataclass
class BoostingModel:
    """XGBoost-class binary GBDT (numpy). Optional ``xgboost`` package unused on purpose."""

    name: str = "xgboost_class"
    n_estimators: int = 30
    learning_rate: float = 0.08
    trees: List[dict] = field(default_factory=list)
    base_score: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "BoostingModel":
        y = np.asarray(y, dtype=np.float64)
        n = y.shape[0]
        sw = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)
        prev = float(np.clip(np.average(y, weights=sw), 1e-3, 1 - 1e-3))
        self.base_score = float(np.log(prev / (1 - prev)))
        raw = np.full(n, self.base_score)
        self.trees = []
        for _ in range(self.n_estimators):
            p = 1.0 / (1.0 + np.exp(-np.clip(raw, -40.0, 40.0)))
            residual = sw * (y - p)
            hessian = sw * p * (1.0 - p)
            stump = _best_stump(X, residual, hessian)
            self.trees.append(stump)
            mask = X[:, stump["feature"]] <= stump["threshold"]
            raw = raw + self.learning_rate * np.where(mask, stump["left"], stump["right"])
        return self

    def predict_raw(self, X: np.ndarray) -> np.ndarray:
        raw = np.full(X.shape[0], self.base_score)
        for stump in self.trees:
            mask = X[:, stump["feature"]] <= stump["threshold"]
            raw = raw + self.learning_rate * np.where(mask, stump["left"], stump["right"])
        return raw

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(self.predict_raw(X), -40.0, 40.0)))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "trees": self.trees,
            "base_score": self.base_score,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "BoostingModel":
        model = cls(
            name=payload.get("name", "xgboost_class"),
            n_estimators=int(payload.get("n_estimators", 40)),
            learning_rate=float(payload.get("learning_rate", 0.08)),
        )
        model.trees = list(payload.get("trees") or [])
        model.base_score = float(payload.get("base_score", 0.0))
        return model


def persistence_proba(samples: Sequence[ForecastSample]) -> np.ndarray:
    return np.asarray([float((s.extra or {}).get("y_at_issue", 0)) for s in samples], dtype=np.float64)


def climatology_proba(train: Sequence[ForecastSample], target: Sequence[ForecastSample]) -> np.ndarray:
    rates: Dict[int, float] = {}
    for month in range(1, 13):
        ys = [s.y_track_a for s in train if s.issue_time[5:7] == f"{month:02d}" and s.y_track_a is not None]
        rates[month] = float(np.mean(ys)) if ys else 0.1
    out = []
    for sample in target:
        month = int(sample.issue_time[5:7])
        out.append(rates.get(month, 0.1))
    return np.asarray(out, dtype=np.float64)


def horizon_weights(samples: Sequence[ForecastSample]) -> np.ndarray:
    return np.asarray([HORIZON_WEIGHTS.get(s.horizon_hours, 1.0) for s in samples], dtype=np.float64)


@dataclass
class FittedBaselines:
    scaler: TrainScaler
    logistic: LogisticModel
    boosting: BoostingModel
    climatology_rate: float
    threshold: float
    track: str
    feature_names: List[str] = field(default_factory=lambda: list(FEATURE_NAMES))


def fit_baselines(samples: Sequence[ForecastSample], track: str = "A") -> FittedBaselines:
    train = by_split(samples, "train")
    X_raw, y, kept = matrix(train, track=track, scaler=None)
    scaler = fit_scaler(X_raw)
    X = scaler.transform(X_raw)
    weights = horizon_weights(kept)
    logistic = LogisticModel().fit(X, y.astype(np.float64), sample_weight=weights)
    boosting = BoostingModel().fit(X, y.astype(np.float64), sample_weight=weights)
    return FittedBaselines(
        scaler=scaler,
        logistic=logistic,
        boosting=boosting,
        climatology_rate=float(np.mean(y)) if y.size else 0.1,
        threshold=0.5,
        track=track,
    )


def predict_model(model, samples: Sequence[ForecastSample], fitted: FittedBaselines) -> np.ndarray:
    X, _, kept_idx = matrix(samples, track=fitted.track, scaler=None)
    # matrix filters; align by rebuilding from the same filter
    kept = []
    for sample in samples:
        if sample.lookback_complete_frac < 0.80:
            continue
        if fitted.track == "A" and sample.y_track_a is None:
            continue
        if fitted.track == "B" and (not sample.y_track_b_available or sample.y_track_b is None):
            continue
        kept.append(sample)
    if not kept:
        return np.zeros((0,))
    X = np.vstack([vectorize(s) for s in kept])
    Xs = fitted.scaler.transform(X)
    return model.predict_proba(Xs)


def evaluate_baselines(samples: Sequence[ForecastSample], fitted: FittedBaselines, split: str) -> dict:
    subset = by_split(samples, split)
    X, y, kept = matrix(subset, track=fitted.track, scaler=fitted.scaler)
    if y.size == 0:
        return {"split": split, "track": fitted.track, "n": 0, "note": "no labeled rows"}
    persist = persistence_proba(kept)
    clim = climatology_proba(by_split(samples, "train"), kept)
    log_p = fitted.logistic.predict_proba(X)
    boost_p = fitted.boosting.predict_proba(X)
    clim_rate = fitted.climatology_rate
    by_horizon = {}
    for hours in sorted({s.horizon_hours for s in kept}):
        mask = np.array([s.horizon_hours == hours for s in kept])
        by_horizon[str(hours)] = {
            "xgboost_class": summarize(y[mask], boost_p[mask], fitted.threshold, climatology=clim_rate),
            "persistence": summarize(y[mask], persist[mask], fitted.threshold, climatology=clim_rate),
        }
    return {
        "split": split,
        "track": fitted.track,
        "label_kind": "MODELLED" if fitted.track == "A" else "OBSERVED",
        "n": int(y.size),
        "prevalence": float(np.mean(y)),
        "models": {
            "persistence": summarize(y, persist, fitted.threshold, climatology=clim_rate),
            "climatology": summarize(y, clim, fitted.threshold, climatology=clim_rate),
            "logistic": summarize(y, log_p, fitted.threshold, climatology=clim_rate),
            "xgboost_class": summarize(y, boost_p, fitted.threshold, climatology=clim_rate),
        },
        "beats_persistence": {
            "xgboost_class": bool(
                summarize(y, boost_p, fitted.threshold, climatology=clim_rate)["auprc"]
                > summarize(y, persist, fitted.threshold, climatology=clim_rate)["auprc"]
            )
        },
        "by_horizon": by_horizon,
        "accuracy_claim": None,
        "note": "Tracks A and B must not be mixed. Accuracy is not reported.",
    }
