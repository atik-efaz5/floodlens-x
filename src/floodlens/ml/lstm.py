"""Tiny LSTM with five horizon heads. CPU-only numpy. Not shipped unless it beats boosting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from floodlens.application.forecast import HORIZONS_H
from floodlens.ml.baselines import HORIZON_WEIGHTS
from floodlens.ml.features import sequence_precip
from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample

HORIZON_INDEX = {h: i for i, h in enumerate(HORIZONS_H)}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0)))


def _tanh(z: np.ndarray) -> np.ndarray:
    return np.tanh(np.clip(z, -20.0, 20.0))


@dataclass
class TinyLSTM:
    n_in: int = 1
    hidden: int = 16
    n_heads: int = 5
    seed: int = 0
    W: Optional[np.ndarray] = None  # (n_in + hidden, 4 * hidden)
    b: Optional[np.ndarray] = None
    Why: Optional[np.ndarray] = None  # (hidden, n_heads)
    by: Optional[np.ndarray] = None

    def init_weights(self) -> None:
        rng = np.random.default_rng(self.seed)
        scale = 0.08
        self.W = rng.normal(0.0, scale, size=(self.n_in + self.hidden, 4 * self.hidden))
        self.b = np.zeros(4 * self.hidden)
        self.b[self.hidden : 2 * self.hidden] = 1.0  # forget-gate bias
        self.Why = rng.normal(0.0, scale, size=(self.hidden, self.n_heads))
        self.by = np.zeros(self.n_heads)

    def _forward_seq(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h = np.zeros(self.hidden)
        c = np.zeros(self.hidden)
        for t in range(x.shape[0]):
            inp = np.concatenate([x[t], h])
            gates = inp @ self.W + self.b
            i = _sigmoid(gates[: self.hidden])
            f = _sigmoid(gates[self.hidden : 2 * self.hidden])
            o = _sigmoid(gates[2 * self.hidden : 3 * self.hidden])
            g = _tanh(gates[3 * self.hidden :])
            c = f * c + i * g
            h = o * _tanh(c)
        logits = h @ self.Why + self.by
        return h, logits

    def predict_logits(self, sequences: np.ndarray) -> np.ndarray:
        if self.W is None:
            self.init_weights()
        out = np.zeros((sequences.shape[0], self.n_heads))
        for n in range(sequences.shape[0]):
            _, logits = self._forward_seq(sequences[n])
            out[n] = logits
        return out

    def predict_proba_seq(self, sequences: np.ndarray) -> np.ndarray:
        return _sigmoid(self.predict_logits(sequences))

    def predict_proba_samples(self, samples: Sequence[ForecastSample]) -> np.ndarray:
        seq = np.stack([sequence_precip(s) for s in samples])
        probs = self.predict_proba_seq(seq)
        out = np.zeros(len(samples))
        for i, sample in enumerate(samples):
            out[i] = probs[i, HORIZON_INDEX[sample.horizon_hours]]
        return out

    def fit(
        self,
        sequences: np.ndarray,
        y: np.ndarray,
        horizons: np.ndarray,
        lr: float = 0.05,
        epochs: int = 12,
        batch_size: int = 64,
    ) -> "TinyLSTM":
        """SGD on horizon-weighted BCE. Sequences are unique issue times; y is (N, 5)."""
        if self.W is None:
            self.init_weights()
        n = sequences.shape[0]
        hw = np.array([HORIZON_WEIGHTS[h] for h in HORIZONS_H], dtype=np.float64)
        rng = np.random.default_rng(self.seed + 1)
        for _ in range(epochs):
            order = rng.permutation(n)
            for start in range(0, n, batch_size):
                idx = order[start : start + batch_size]
                dW = np.zeros_like(self.W)
                db = np.zeros_like(self.b)
                dWhy = np.zeros_like(self.Why)
                dby = np.zeros_like(self.by)
                for j in idx:
                    x = sequences[j]
                    h, logits = self._forward_seq(x)
                    p = _sigmoid(logits)
                    # dL/dlogit
                    delta = hw * (p - y[j]) / max(float(np.sum(hw)), 1.0)
                    dWhy += np.outer(h, delta)
                    dby += delta
                    dh = self.Why @ delta
                    # truncated BPTT: last-step LSTM grads only (MVP, documented)
                    # Reconstruct last input
                    # Use numerical-free last-step: treat dh as gradient on h_T
                    # Approximate W update via last concatenated input.
                    # Store last inp by re-running last step:
                    h_prev = np.zeros(self.hidden)
                    c = np.zeros(self.hidden)
                    last_inp = None
                    last_i = last_f = last_o = last_g = last_c_prev = None
                    h = np.zeros(self.hidden)
                    for t in range(x.shape[0]):
                        last_c_prev = c
                        inp = np.concatenate([x[t], h])
                        gates = inp @ self.W + self.b
                        i = _sigmoid(gates[: self.hidden])
                        f = _sigmoid(gates[self.hidden : 2 * self.hidden])
                        o = _sigmoid(gates[2 * self.hidden : 3 * self.hidden])
                        g = _tanh(gates[3 * self.hidden :])
                        c = f * c + i * g
                        h_prev = h
                        h = o * _tanh(c)
                        last_inp = inp
                        last_i, last_f, last_o, last_g = i, f, o, g
                    tanh_c = _tanh(c)
                    do = dh * tanh_c
                    dc = dh * last_o * (1.0 - tanh_c ** 2)
                    di = dc * last_g
                    dg = dc * last_i
                    df = dc * last_c_prev
                    di_raw = last_i * (1.0 - last_i) * di
                    df_raw = last_f * (1.0 - last_f) * df
                    do_raw = last_o * (1.0 - last_o) * do
                    dg_raw = (1.0 - last_g ** 2) * dg
                    dgates = np.concatenate([di_raw, df_raw, do_raw, dg_raw])
                    dW += np.outer(last_inp, dgates)
                    db += dgates
                scale = 1.0 / max(len(idx), 1)
                self.W -= lr * dW * scale
                self.b -= lr * db * scale
                self.Why -= lr * dWhy * scale
                self.by -= lr * dby * scale
                self.W = np.clip(self.W, -5.0, 5.0)
        return self

    def to_dict(self) -> dict:
        return {
            "n_in": self.n_in,
            "hidden": self.hidden,
            "n_heads": self.n_heads,
            "seed": self.seed,
            "W": None if self.W is None else self.W.tolist(),
            "b": None if self.b is None else self.b.tolist(),
            "Why": None if self.Why is None else self.Why.tolist(),
            "by": None if self.by is None else self.by.tolist(),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "TinyLSTM":
        model = cls(
            n_in=int(payload.get("n_in", 1)),
            hidden=int(payload.get("hidden", 16)),
            n_heads=int(payload.get("n_heads", 5)),
            seed=int(payload.get("seed", 0)),
        )
        if payload.get("W") is not None:
            model.W = np.asarray(payload["W"])
            model.b = np.asarray(payload["b"])
            model.Why = np.asarray(payload["Why"])
            model.by = np.asarray(payload["by"])
        return model


def pack_issue_sequences(samples: Sequence[ForecastSample]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """One sequence per (city, issue_time); y shape (N, 5)."""
    groups = {}
    for sample in samples:
        if sample.y_track_a is None:
            continue
        key = (sample.city_id, sample.issue_time)
        groups.setdefault(key, {})[sample.horizon_hours] = sample
    seqs = []
    labels = []
    keys = []
    for key, by_h in groups.items():
        if len(by_h) < len(HORIZONS_H):
            continue
        first = by_h[HORIZONS_H[0]]
        seqs.append(sequence_precip(first))
        labels.append([int(by_h[h].y_track_a) for h in HORIZONS_H])
        keys.append(f"{key[0]}|{key[1]}")
    if not seqs:
        return np.zeros((0, LOOKBACK_HOURS, 1)), np.zeros((0, 5)), []
    return np.stack(seqs), np.asarray(labels, dtype=np.float64), keys
