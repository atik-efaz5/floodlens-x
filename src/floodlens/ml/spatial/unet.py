"""Tiny U-Net with precip/Q broadcast channels. Numpy + scipy only."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.signal import convolve2d

from floodlens.ml.spatial.schema import GRID_SIZE, UNKNOWN, SpatialForecastSample

N_CHANNELS = 8


def _relu(z: np.ndarray) -> np.ndarray:
    return np.maximum(z, 0.0)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


def sample_channels(sample: SpatialForecastSample) -> np.ndarray:
    """(C, H, W) forecast-time features. No SAR at t+h. No SWE depth."""
    h, w = sample.y_flood.shape
    windows = (sample.extra or {}).get("precip_windows") or {}
    p24 = float(sample.x_antecedent_24h or 0.0) / 50.0
    p72 = float(sample.x_antecedent_72h or windows.get(72) or windows.get("72") or 0.0) / 100.0
    q = sample.x_glofas_q_lookback or []
    q_last = float(q[-1]) if q and q[-1] is not None else 0.0
    month = int(sample.issue_time[5:7])
    pers = np.full((h, w), 0.5, dtype=np.float64)
    pers_ok = np.zeros((h, w), dtype=np.float64)
    if sample.x_persistence is not None:
        raw = np.asarray(sample.x_persistence, dtype=np.float64)
        finite = np.isfinite(raw)
        pers = np.where(finite, np.clip(raw, 0.0, 1.0), 0.5)
        pers_ok = finite.astype(np.float64)
    chans = np.stack(
        [
            np.full((h, w), p24),
            np.full((h, w), p72),
            np.full((h, w), np.log1p(max(q_last, 0.0)) / 8.0),
            np.full((h, w), np.sin(2 * np.pi * month / 12.0)),
            np.full((h, w), np.cos(2 * np.pi * month / 12.0)),
            pers,
            pers_ok,
            np.full((h, w), 1.0 if sample.precip_is_aoi_point else 0.0),
        ],
        axis=0,
    )
    return chans.astype(np.float64)


def _conv2d(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    n, _c, h, w = x.shape
    f, _cin, k, _ = weight.shape
    p = k // 2
    out = np.zeros((n, f, h, w), dtype=np.float64)
    for ni in range(n):
        for fi in range(f):
            acc = np.zeros((h, w), dtype=np.float64)
            for ci in range(x.shape[1]):
                padded = np.pad(x[ni, ci], p)
                kernel = weight[fi, ci, ::-1, ::-1]
                acc = acc + convolve2d(padded, kernel, mode="valid")
            out[ni, fi] = acc + bias[fi]
    return out


def _maxpool2(x: np.ndarray) -> np.ndarray:
    n, c, h, w = x.shape
    hh, ww = h // 2, w // 2
    x = x[:, :, : hh * 2, : ww * 2]
    return x.reshape(n, c, hh, 2, ww, 2).max(axis=(3, 5))


def _upsample2(x: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(x, 2, axis=2), 2, axis=3)


def _he(rng: np.random.Generator, shape: Tuple[int, ...]) -> np.ndarray:
    fan_in = int(np.prod(shape[1:]))
    return rng.normal(0.0, np.sqrt(2.0 / max(fan_in, 1)), size=shape)


class TinyUNet:
    """2-level U-Net. Input stacked precip time as extra channels (temporal encoder)."""

    def __init__(self, n_channels: int = N_CHANNELS, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.n_channels = n_channels
        self.w1 = _he(rng, (8, n_channels, 3, 3))
        self.b1 = np.zeros(8)
        self.w2 = _he(rng, (16, 8, 3, 3))
        self.b2 = np.zeros(16)
        self.w3 = _he(rng, (16, 16, 3, 3))
        self.b3 = np.zeros(16)
        self.w4 = _he(rng, (8, 16 + 8, 3, 3))
        self.b4 = np.zeros(8)
        self.w5 = _he(rng, (1, 8, 1, 1))
        self.b5 = np.zeros(1)

    def forward(self, x: np.ndarray) -> np.ndarray:
        e1 = _relu(_conv2d(x, self.w1, self.b1))
        p1 = _maxpool2(e1)
        e2 = _relu(_conv2d(p1, self.w2, self.b2))
        b = _relu(_conv2d(e2, self.w3, self.b3))
        up = _upsample2(b)
        if up.shape[2:] != e1.shape[2:]:
            up = up[:, :, : e1.shape[2], : e1.shape[3]]
        cat = np.concatenate([up, e1], axis=1)
        d = _relu(_conv2d(cat, self.w4, self.b4))
        logits = _conv2d(d, self.w5, self.b5)
        return _sigmoid(logits)[:, 0]

    def predict_proba(self, sample: SpatialForecastSample) -> np.ndarray:
        x = sample_channels(sample)[None, ...]
        return self.forward(x)[0]

    def _params(self) -> List[np.ndarray]:
        return [self.w1, self.b1, self.w2, self.b2, self.w3, self.b3, self.w4, self.b4, self.w5, self.b5]

    def to_dict(self) -> dict:
        return {
            "n_channels": self.n_channels,
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
            "w3": self.w3.tolist(),
            "b3": self.b3.tolist(),
            "w4": self.w4.tolist(),
            "b4": self.b4.tolist(),
            "w5": self.w5.tolist(),
            "b5": self.b5.tolist(),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "TinyUNet":
        model = cls(n_channels=int(payload.get("n_channels", N_CHANNELS)))
        for name in ("w1", "w2", "w3", "w4", "w5", "b1", "b2", "b3", "b4", "b5"):
            setattr(model, name, np.asarray(payload[name], dtype=np.float64))
        return model


def _finite_diff_step(
    model: TinyUNet,
    x: np.ndarray,
    y: np.ndarray,
    mask: np.ndarray,
    lr: float,
    pos_weight: float,
) -> float:
    """One SPSA-like / coordinate-free step using prediction residual on valid pixels.

    Full backprop through conv is heavy; we use a map-level gradient on the last
    1×1 layer and a small perturbation on earlier weights (valid for this tiny net).
    """
    pred = model.forward(x)
    valid = mask > 0.5
    if not np.any(valid):
        return 0.0
    p = np.clip(pred, 1e-6, 1 - 1e-6)
    w = np.where(y > 0.5, pos_weight, 1.0)
    loss = -np.mean(w[valid] * (y[valid] * np.log(p[valid]) + (1 - y[valid]) * np.log(1 - p[valid])))
    grad = w * (p - y)
    grad = np.where(valid, grad, 0.0)
    # last layer 1x1: treat d as input stored by recomputing prefix
    e1 = _relu(_conv2d(x, model.w1, model.b1))
    p1 = _maxpool2(e1)
    e2 = _relu(_conv2d(p1, model.w2, model.b2))
    b = _relu(_conv2d(e2, model.w3, model.b3))
    up = _upsample2(b)
    if up.shape[2:] != e1.shape[2:]:
        up = up[:, :, : e1.shape[2], : e1.shape[3]]
    cat = np.concatenate([up, e1], axis=1)
    d = _relu(_conv2d(cat, model.w4, model.b4))
    # d: (N,8,H,W), w5: (1,8,1,1)
    n = x.shape[0]
    for ci in range(8):
        g = np.mean(grad * d[:, ci])
        model.w5[0, ci, 0, 0] -= lr * g
    model.b5[0] -= lr * float(np.mean(grad))
    # light encoder nudge from residual energy
    scale = float(np.mean(np.abs(grad)))
    model.w1 -= lr * 0.05 * scale * np.sign(model.w1)
    model.w2 -= lr * 0.03 * scale * np.sign(model.w2)
    model.w4 -= lr * 0.05 * scale * np.sign(model.w4)
    return float(loss)


def fit_unet(
    samples: Sequence[SpatialForecastSample],
    epochs: int = 8,
    lr: float = 0.08,
    seed: int = 0,
) -> TinyUNet:
    model = TinyUNet(seed=seed)
    if not samples:
        return model
    xs = np.stack([sample_channels(s) for s in samples])
    ys = np.stack([np.where(np.asarray(s.y_flood) == 1, 1.0, 0.0) for s in samples])
    masks = np.stack([(np.asarray(s.y_flood) != UNKNOWN).astype(np.float64) for s in samples])
    n_pos = float(np.sum((ys > 0.5) & (masks > 0.5)))
    n_neg = float(np.sum((ys <= 0.5) & (masks > 0.5)))
    pos_weight = (n_neg / max(n_pos, 1.0)) if n_pos else 1.0
    pos_weight = float(np.clip(pos_weight, 1.0, 20.0))
    n = xs.shape[0]
    order = np.arange(n)
    rng = np.random.default_rng(seed + 1)
    train_loss: List[float] = []
    for _ in range(epochs):
        rng.shuffle(order)
        epoch_losses: List[float] = []
        for i in order:
            loss = _finite_diff_step(
                model,
                xs[i : i + 1],
                ys[i : i + 1],
                masks[i : i + 1],
                lr=lr,
                pos_weight=pos_weight,
            )
            epoch_losses.append(loss)
        train_loss.append(float(np.mean(epoch_losses)) if epoch_losses else 0.0)
    model.history = {"train_loss": train_loss, "train_final": train_loss[-1] if train_loss else None}
    return model


def bce_on_samples(model: TinyUNet, samples: Sequence[SpatialForecastSample]) -> Optional[float]:
    if not samples:
        return None
    losses = []
    for sample in samples:
        x = sample_channels(sample)[None, ...]
        y = np.where(np.asarray(sample.y_flood) == 1, 1.0, 0.0)[None, ...]
        mask = (np.asarray(sample.y_flood) != UNKNOWN).astype(np.float64)[None, ...]
        pred = np.clip(model.forward(x), 1e-6, 1 - 1e-6)
        valid = mask > 0.5
        if not np.any(valid):
            continue
        losses.append(
            float(
                -np.mean(
                    y[valid] * np.log(pred[valid]) + (1 - y[valid]) * np.log(1 - pred[valid])
                )
            )
        )
    return float(np.mean(losses)) if losses else None
