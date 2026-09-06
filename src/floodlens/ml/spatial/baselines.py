"""Spatial map baselines: persistence, climatology, rain threshold, pixel GBDT."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.baselines import BoostingModel, LogisticModel
from floodlens.ml.spatial.eval_spatial import map_metrics
from floodlens.ml.spatial.labels import valid_prevalence
from floodlens.ml.spatial.schema import UNKNOWN, SpatialForecastSample
from floodlens.ml.spatial.splits import by_split

PIXEL_FEATURE_NAMES: Tuple[str, ...] = (
    "antecedent_24h",
    "antecedent_72h",
    "precip_24h_local",
    "precip_72h_local",
    "precip_6h",
    "log1p_q",
    "month_sin",
    "month_cos",
    "persistence",
    "persistence_valid",
    "row_norm",
    "col_norm",
    "dem",
    "slope",
    "river_distance",
    "precip_is_aoi_point",
    "q_is_glofas_cell",
    "precip_mean_6h",
)
N_PIXEL_FEATURES = len(PIXEL_FEATURE_NAMES)

PIXEL_FEATURE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "rainfall": (
        "antecedent_24h",
        "antecedent_72h",
        "precip_24h_local",
        "precip_72h_local",
        "precip_6h",
        "precip_mean_6h",
    ),
    "terrain": ("dem", "slope"),
    "river_static": ("river_distance", "row_norm", "col_norm"),
    "persistence": ("persistence", "persistence_valid"),
    "season": ("month_sin", "month_cos"),
    "hydrology": ("log1p_q", "q_is_glofas_cell"),
}

ABLATION_GROUPS: Dict[str, Tuple[str, ...]] = {
    "A_rainfall": ("rainfall",),
    "B_terrain": ("terrain",),
    "C_river_static": ("river_static",),
    "D_rainfall_terrain": ("rainfall", "terrain"),
    "E_rainfall_terrain_river": ("rainfall", "terrain", "river_static"),
    "F_all": tuple(PIXEL_FEATURE_GROUPS.keys()),
}


def feature_indices(group_names: Optional[Sequence[str]] = None) -> Tuple[int, ...]:
    """Column indices into PIXEL_FEATURE_NAMES. None → all columns."""
    if group_names is None:
        return tuple(range(N_PIXEL_FEATURES))
    names: List[str] = []
    for group in group_names:
        if group in {"F_all", "all"}:
            return tuple(range(N_PIXEL_FEATURES))
        names.extend(PIXEL_FEATURE_GROUPS[group])
    seen: List[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return tuple(PIXEL_FEATURE_NAMES.index(n) for n in seen)


def _month(sample: SpatialForecastSample) -> int:
    return int(sample.issue_time[5:7])


def _stack_valid(y: np.ndarray, p: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mask = np.isfinite(y) & (np.asarray(y) != UNKNOWN) & np.isfinite(p)
    return np.asarray(y, dtype=np.float64)[mask], np.asarray(p, dtype=np.float64)[mask]


def persistence_map(sample: SpatialForecastSample) -> np.ndarray:
    h, w = sample.y_flood.shape
    out = np.full((h, w), 0.0, dtype=np.float64)
    if sample.x_persistence is None:
        return out
    pers = np.asarray(sample.x_persistence, dtype=np.float64)
    out = np.where(np.isfinite(pers), np.clip(pers, 0.0, 1.0), 0.0)
    return out


def conv_smooth_map(sample: SpatialForecastSample) -> np.ndarray:
    """One 3×3 mean on lagged inundation (simple convolutional baseline)."""
    pers = persistence_map(sample)
    kernel = np.ones((3, 3), dtype=np.float64) / 9.0
    padded = np.pad(pers, 1, mode="edge")
    out = np.zeros_like(pers)
    for i in range(pers.shape[0]):
        for j in range(pers.shape[1]):
            out[i, j] = float(np.sum(padded[i : i + 3, j : j + 3] * kernel))
    return np.clip(out, 0.0, 1.0)


def rain_threshold_map(sample: SpatialForecastSample, threshold_mm: float) -> np.ndarray:
    h, w = sample.y_flood.shape
    grid = (sample.extra or {}).get("precip_24h_map")
    if grid is not None:
        arr = np.asarray(grid, dtype=np.float64)
        return (arr >= threshold_mm).astype(np.float64)
    wet = 1.0 if float(sample.x_antecedent_24h or 0.0) >= threshold_mm else 0.0
    return np.full((h, w), wet, dtype=np.float64)


def pixel_feature_cube(sample: SpatialForecastSample) -> np.ndarray:
    """(H, W, 18) causal pixel features. Does not include the target map."""
    extra = sample.extra or {}
    y = np.asarray(sample.y_flood)
    hh, ww = y.shape
    cube = np.zeros((hh, ww, N_PIXEL_FEATURES), dtype=np.float64)
    windows = extra.get("precip_windows") or {}
    q = sample.x_glofas_q_lookback or []
    q_last = float(q[-1]) if q and q[-1] is not None else 0.0
    month = _month(sample)
    precip = list(sample.x_precip_hourly)
    p24_map = extra.get("precip_24h_map")
    p72_map = extra.get("precip_72h_map")
    p24_fill = float(sample.x_antecedent_24h or 0.0)
    p72_fill = float(sample.x_antecedent_72h or 0.0)
    if p24_map is None:
        p24_local = np.full((hh, ww), p24_fill, dtype=np.float64)
    else:
        p24_local = np.asarray(p24_map, dtype=np.float64)
    if p72_map is None:
        p72_local = np.full((hh, ww), p72_fill, dtype=np.float64)
    else:
        p72_local = np.asarray(p72_map, dtype=np.float64)
    pers = np.full((hh, ww), 0.5, dtype=np.float64)
    pers_ok = np.zeros((hh, ww), dtype=np.float64)
    if sample.x_persistence is not None:
        pmap = np.asarray(sample.x_persistence, dtype=np.float64)
        ok = np.isfinite(pmap)
        pers = np.where(ok, pmap, 0.5)
        pers_ok = ok.astype(np.float64)
    dem = np.zeros((hh, ww), dtype=np.float64)
    if sample.x_dem is not None:
        dmap = np.asarray(sample.x_dem, dtype=np.float64)
        dem = np.where(np.isfinite(dmap), dmap, 0.0)
    slope = extra.get("slope")
    sl = np.zeros((hh, ww), dtype=np.float64) if slope is None else np.asarray(slope, dtype=np.float64)
    river = extra.get("river_distance")
    rd = np.zeros((hh, ww), dtype=np.float64) if river is None else np.asarray(river, dtype=np.float64)
    ii, jj = np.indices((hh, ww))
    cube[:, :, 0] = p24_fill
    cube[:, :, 1] = p72_fill
    cube[:, :, 2] = p24_local
    cube[:, :, 3] = p72_local
    cube[:, :, 4] = float(windows.get(6) or windows.get("6") or 0.0)
    cube[:, :, 5] = np.log1p(max(q_last, 0.0))
    cube[:, :, 6] = np.sin(2 * np.pi * month / 12.0)
    cube[:, :, 7] = np.cos(2 * np.pi * month / 12.0)
    cube[:, :, 8] = pers
    cube[:, :, 9] = pers_ok
    cube[:, :, 10] = ii / max(hh - 1, 1)
    cube[:, :, 11] = jj / max(ww - 1, 1)
    cube[:, :, 12] = dem
    cube[:, :, 13] = sl
    cube[:, :, 14] = rd
    cube[:, :, 15] = 1.0 if sample.precip_is_aoi_point else 0.0
    cube[:, :, 16] = 1.0 if sample.q_is_glofas_cell else 0.0
    cube[:, :, 17] = float(np.mean(precip[-6:])) if precip else 0.0
    return cube


def pixel_vector(sample: SpatialForecastSample, i: int, j: int) -> np.ndarray:
    return pixel_feature_cube(sample)[i, j]


def pixel_matrix(
    sample: SpatialForecastSample,
    columns: Optional[Sequence[int]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Valid (non-unknown) pixels only. Unknown is never converted to dry."""
    cube = pixel_feature_cube(sample)
    y = np.asarray(sample.y_flood)
    valid = y != UNKNOWN
    X = cube[valid]
    if columns is not None:
        X = X[:, list(columns)]
    return X, y[valid].astype(np.float64)


def flatten_pixels(
    samples: Sequence[SpatialForecastSample],
    columns: Optional[Sequence[int]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    xs: List[np.ndarray] = []
    ys: List[np.ndarray] = []
    n_col = N_PIXEL_FEATURES if columns is None else len(tuple(columns))
    for sample in samples:
        X, y = pixel_matrix(sample, columns=columns)
        if y.size:
            xs.append(X)
            ys.append(y)
    if not xs:
        return np.zeros((0, n_col)), np.zeros((0,))
    return np.vstack(xs), np.concatenate(ys)


def pixel_predict_fn(model, columns: Optional[Sequence[int]] = None):
    """Map-valued predict using only valid pixels; unknown cells stay 0 and are not scored."""

    def _pred(sample: SpatialForecastSample) -> np.ndarray:
        h, w = sample.y_flood.shape
        out = np.zeros((h, w), dtype=np.float64)
        ymap = np.asarray(sample.y_flood)
        valid = ymap != UNKNOWN
        if not np.any(valid):
            return out
        X, _ = pixel_matrix(sample, columns=columns)
        if X.size == 0:
            return out
        probs = np.asarray(model.predict_proba(X), dtype=np.float64).reshape(-1)
        out[valid] = probs
        return out

    return _pred


class AoiMonthClimatology:
    """Train-only flood probability keyed by AOI and calendar month.

    Legacy CellClimatology stacks every AOI onto one 64×64 grid and is not a
    location climatology. Phase 6.7 uses this AOI-aware version.
    """

    def __init__(self):
        self.by_key: Dict[Tuple[str, int], np.ndarray] = {}
        self.by_aoi: Dict[str, np.ndarray] = {}
        self.global_mean: float = 0.0

    def fit(self, samples: Sequence[SpatialForecastSample]) -> "AoiMonthClimatology":
        buckets: Dict[Tuple[str, int], List[np.ndarray]] = {}
        aoi_buckets: Dict[str, List[np.ndarray]] = {}
        all_y = []
        for sample in samples:
            y = sample.y_binary()
            key = (sample.city_id, _month(sample))
            buckets.setdefault(key, []).append(y)
            aoi_buckets.setdefault(sample.city_id, []).append(y)
            all_y.append(y)
        stacked_all = np.stack(all_y) if all_y else np.zeros((1, 1, 1))
        finite = np.isfinite(stacked_all)
        if finite.any():
            self.global_mean = float(np.sum(np.where(finite, stacked_all, 0.0)) / np.sum(finite))
        else:
            self.global_mean = 0.0

        def _mean_stack(maps: List[np.ndarray], fill: float) -> np.ndarray:
            stacked = np.stack(maps)
            ok = np.isfinite(stacked)
            denom = np.maximum(np.sum(ok, axis=0), 1)
            mean = np.sum(np.where(ok, stacked, 0.0), axis=0) / denom
            return np.where(np.sum(ok, axis=0) > 0, mean, fill)

        for aoi_id, maps in aoi_buckets.items():
            self.by_aoi[aoi_id] = _mean_stack(maps, self.global_mean)
        for key, maps in buckets.items():
            aoi_grid = self.by_aoi.get(key[0])
            fill = self.global_mean if aoi_grid is None else float(np.nanmean(aoi_grid))
            if not np.isfinite(fill):
                fill = self.global_mean
            self.by_key[key] = _mean_stack(maps, fill)
        return self

    def predict(self, sample: SpatialForecastSample) -> np.ndarray:
        grid = self.by_key.get((sample.city_id, _month(sample)))
        if grid is None:
            grid = self.by_aoi.get(sample.city_id)
        if grid is None:
            return np.full(sample.y_flood.shape, self.global_mean, dtype=np.float64)
        return np.where(np.isfinite(grid), grid, self.global_mean)


class CellClimatology:
    def __init__(self):
        self.by_month: Dict[int, np.ndarray] = {}
        self.global_mean: float = 0.0

    def fit(self, samples: Sequence[SpatialForecastSample]) -> "CellClimatology":
        buckets: Dict[int, List[np.ndarray]] = {}
        all_y = []
        for sample in samples:
            y = sample.y_binary()
            buckets.setdefault(_month(sample), []).append(y)
            all_y.append(y)
        stacked_all = np.stack(all_y) if all_y else np.zeros((1, 1, 1))
        finite = np.isfinite(stacked_all)
        if finite.any():
            self.global_mean = float(np.sum(np.where(finite, stacked_all, 0.0)) / np.sum(finite))
        else:
            self.global_mean = 0.0
        for month, maps in buckets.items():
            stacked = np.stack(maps)
            ok = np.isfinite(stacked)
            denom = np.maximum(np.sum(ok, axis=0), 1)
            summed = np.sum(np.where(ok, stacked, 0.0), axis=0)
            mean = summed / denom
            mean = np.where(np.sum(ok, axis=0) > 0, mean, self.global_mean)
            self.by_month[month] = mean
        return self

    def predict(self, sample: SpatialForecastSample) -> np.ndarray:
        grid = self.by_month.get(_month(sample))
        if grid is None:
            return np.full(sample.y_flood.shape, self.global_mean, dtype=np.float64)
        return np.where(np.isfinite(grid), grid, self.global_mean)


def fit_rain_threshold(samples: Sequence[SpatialForecastSample]) -> float:
    rains = [float(s.x_antecedent_24h or 0.0) for s in samples]
    if not rains:
        return 50.0
    return float(np.quantile(rains, 0.7))


def evaluate_maps(
    samples: Sequence[SpatialForecastSample],
    pred_fn,
    name: str,
    threshold: float = 0.5,
) -> dict:
    ys = []
    ps = []
    for sample in samples:
        y = sample.y_binary()
        p = np.asarray(pred_fn(sample), dtype=np.float64)
        yv, pv = _stack_valid(y, p)
        ys.append(yv)
        ps.append(pv)
    if not ys:
        return {"n": 0, "prevalence": float("nan"), "model": name, "accuracy_claim": None}
    y_all = np.concatenate(ys)
    p_all = np.concatenate(ps)
    n, prev = valid_prevalence(y_all)
    row = map_metrics(y_all, p_all, threshold=threshold)
    row["model"] = name
    row["n_maps"] = len(samples)
    row["label_kind"] = samples[0].label_kind if samples else None
    row["horizon_hours"] = samples[0].horizon_hours if samples else None
    row["split"] = samples[0].split if samples else None
    row["n_valid_pixels"] = n
    row["prevalence"] = prev
    row["accuracy_claim"] = None
    return row


def fit_spatial_baselines(samples: Sequence[SpatialForecastSample]) -> dict:
    train = by_split(samples, "train") or list(samples)
    clim = CellClimatology().fit(train)
    rain_thr = fit_rain_threshold(train)
    X, y = flatten_pixels(train)
    logistic = LogisticModel(name="pixel_logistic")
    boosting = BoostingModel(name="pixel_gbdt", n_estimators=20, learning_rate=0.1)
    forest = BoostingModel(name="pixel_rf_bag", n_estimators=12, learning_rate=0.12)
    if y.size and y.max() > y.min():
        if y.size > 8000:
            rng = np.random.default_rng(0)
            take = rng.choice(y.size, 8000, replace=False)
            Xf, yf = X[take], y[take]
        else:
            Xf, yf = X, y
        w = np.where(yf > 0.5, (yf.size / max(float(np.sum(yf > 0.5)), 1.0)), 1.0)
        logistic.fit(Xf, yf, sample_weight=w)
        boosting.fit(Xf, yf, sample_weight=w)
        forest.fit(Xf, yf, sample_weight=w)
    elif y.size:
        logistic.fit(X, y)
        boosting.fit(X, y)
        forest.fit(X, y)

    def pixel_model_map(model):
        return pixel_predict_fn(model)

    return {
        "climatology": clim,
        "rain_threshold_mm": rain_thr,
        "logistic": logistic,
        "boosting": boosting,
        "forest": forest,
        "predict": {
            "persistence": persistence_map,
            "climatology": clim.predict,
            "rain_threshold": lambda s, t=rain_thr: rain_threshold_map(s, t),
            "pixel_logistic": pixel_model_map(logistic),
            "pixel_gbdt": pixel_model_map(boosting),
            "pixel_rf": pixel_model_map(forest),
            "conv_smooth": conv_smooth_map,
        },
    }


def evaluate_spatial_baselines(samples: Sequence[SpatialForecastSample], fitted: dict, split: str) -> dict:
    subset = by_split(samples, split)
    rows = {}
    for name, fn in fitted["predict"].items():
        rows[name] = evaluate_maps(subset, fn, name)
    return {
        "split": split,
        "n_maps": len(subset),
        "label_kind": subset[0].label_kind if subset else None,
        "horizon_hours": subset[0].horizon_hours if subset else None,
        "models": rows,
        "accuracy_claim": None,
        "note": "Do not mix OBSERVED/DERIVED/MODELLED. Accuracy is not reported.",
    }
