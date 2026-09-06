"""Phase 6.7 Track A diagnostic baselines. Never promotes VALIDATED.

Fits only persistence, climatology, rain-threshold, logistic, pixel GBDT, and
3×3 neighborhood smoothing. Does not train a CNN/U-Net/transformer. Does not
enable the spatial API. Does not touch the solver.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.baselines import BoostingModel, LogisticModel
from floodlens.ml.evaluate import brier
from floodlens.ml.spatial.aois_v2 import GEO_TEST_AOIS
from floodlens.ml.spatial.baselines import (
    ABLATION_GROUPS,
    AoiMonthClimatology,
    N_PIXEL_FEATURES,
    PIXEL_FEATURE_NAMES,
    conv_smooth_map,
    feature_indices,
    fit_rain_threshold,
    flatten_pixels,
    persistence_map,
    pixel_matrix,
    pixel_predict_fn,
    rain_threshold_map,
)
from floodlens.ml.spatial.builder import build_spatial_samples_v2
from floodlens.ml.spatial.events import inventory, same_event_across_splits, same_event_in_train_and_test
from floodlens.ml.spatial.eval_spatial import map_metrics
from floodlens.ml.spatial.gates import unknown_never_scored_as_dry
from floodlens.ml.spatial.leakage import assert_no_spatial_leakage, assert_persistence_is_lagged, check_spatial_sample
from floodlens.ml.spatial.schema import (
    FLOOD_FRACTION_TAU,
    GRID_SIZE_V2,
    HORIZON_HOURS,
    SPATIAL_DATASET_VERSION_V21,
    SPATIAL_DIR,
    UNKNOWN,
    SpatialForecastSample,
)
from floodlens.ml.spatial.splits import by_split, geographic_split
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

EXPERIMENT_ID = "phase6.7-track-a-baselines-v1"
LABEL_RESOLUTION_M = 20.0
LABEL_CRS = "Equi7 Asia AS020M E039N021T3"
WORKING_GRID = GRID_SIZE_V2
RAIN_CANDIDATE_MM = (10.0, 25.0, 50.0, 75.0)
PIXEL_SUBSAMPLE = 8000
GBDT_TREES = 20
GBDT_LR = 0.1
BOOTSTRAP_DRAWS = 1000
RNG_SEED = 0
OPERATING_THRESHOLD = 0.5
SPLITS_PATH = SPATIAL_DIR / "splits_v2" / "splits.json"
OUT_DIR = SPATIAL_DIR / "phase67"
REPORT_JSON = SPATIAL_DIR / "phase67_eval.json"
HEADLINE_MODELS = (
    "persistence",
    "climatology",
    "rain_threshold",
    "pixel_logistic",
    "pixel_gbdt",
    "conv_smooth",
    "pixel_gbdt_no_persistence",
)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return None
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if np.isfinite(val) else None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    return obj


def _finite(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    return num if np.isfinite(num) else None


def load_frozen_splits(path: Optional[Path] = None) -> dict:
    path = Path(path or SPLITS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"frozen split manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def event_ids_for_split(samples: Sequence[SpatialForecastSample], name: str) -> List[str]:
    return sorted(
        {
            (s.extra or {}).get("event_id")
            for s in samples
            if s.split == name and (s.extra or {}).get("event_id")
        }
    )


def assert_frozen_splits(
    samples: Sequence[SpatialForecastSample],
    expected: Optional[dict] = None,
) -> dict:
    """Fail closed if event membership drifted from the frozen 7/5/3 split."""
    expected = expected or load_frozen_splits()
    observed = {
        "train_events": event_ids_for_split(samples, "train"),
        "validation_events": event_ids_for_split(samples, "val"),
        "test_events": event_ids_for_split(samples, "test"),
    }
    mismatches = {
        key: {"expected": expected.get(key), "observed": observed[key]}
        for key in observed
        if list(expected.get(key) or []) != observed[key]
    }
    if mismatches:
        raise ValueError(f"frozen Track A split mismatch: {mismatches}")
    leaks = {
        "train_test": same_event_in_train_and_test(samples),
        "train_val": same_event_across_splits(samples, "train", "val"),
        "val_test": same_event_across_splits(samples, "val", "test"),
    }
    if any(leaks.values()):
        raise ValueError(f"event leak across frozen splits: {leaks}")
    return {"ok": True, "observed": observed, "leaks": leaks}


def freeze_identifier(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def dataset_freeze(
    samples: Sequence[SpatialForecastSample],
    meta: dict,
    expected_splits: Optional[dict] = None,
    lock_splits: bool = True,
) -> dict:
    inv = inventory(samples) if samples else {}
    resolutions = sorted({float(s.resolution_m) for s in samples}) if samples else []
    freeze = {
        "experiment_id": EXPERIMENT_ID,
        "dataset_version": meta.get("dataset_version") or (samples[0].dataset_version if samples else None),
        "expected_dataset_version": SPATIAL_DATASET_VERSION_V21,
        "n_independent_events": inv.get("n_independent_events"),
        "event_ids": inv.get("event_ids"),
        "train_events": event_ids_for_split(samples, "train"),
        "validation_events": event_ids_for_split(samples, "val"),
        "test_events": event_ids_for_split(samples, "test"),
        "regions": sorted({s.city_id for s in samples}),
        "n_maps": len(samples),
        "feature_channels": list(PIXEL_FEATURE_NAMES),
        "n_pixel_features": N_PIXEL_FEATURES,
        "target_horizon_hours": HORIZON_HOURS,
        "supported_horizons": [HORIZON_HOURS],
        "unsupported_horizons": [6, 12, 24, 48, 72],
        "label_resolution_m": LABEL_RESOLUTION_M,
        "label_crs": LABEL_CRS,
        "working_grid": f"{WORKING_GRID}x{WORKING_GRID}",
        "working_cell_size_m_by_aoi": {
            aoi: float(next(s.resolution_m for s in samples if s.city_id == aoi))
            for aoi in sorted({s.city_id for s in samples})
        }
        if samples
        else {},
        "working_cell_sizes_m": resolutions,
        "flood_fraction_tau": FLOOD_FRACTION_TAU,
        "unknown_code": UNKNOWN,
        "label_kind": meta.get("label_kind"),
        "pixels": inv.get("pixels"),
        "note": (
            "Observation / label native resolution is 20 m Equi7. The working tensor is 64×64 "
            "on AOI geographic bounds (~0.5–1 km/cell). They are not equivalent."
        ),
    }
    freeze["config_sha256"] = freeze_identifier(
        {
            "dataset_version": freeze["dataset_version"],
            "event_ids": freeze["event_ids"],
            "train_events": freeze["train_events"],
            "validation_events": freeze["validation_events"],
            "test_events": freeze["test_events"],
            "horizon_hours": HORIZON_HOURS,
            "grid": WORKING_GRID,
            "tau": FLOOD_FRACTION_TAU,
            "experiment_id": EXPERIMENT_ID,
        }
    )
    if lock_splits:
        freeze["split_lock"] = assert_frozen_splits(samples, expected=expected_splits)
    else:
        freeze["split_lock"] = {
            "ok": True,
            "observed": {
                "train_events": freeze["train_events"],
                "validation_events": freeze["validation_events"],
                "test_events": freeze["test_events"],
            },
            "unlocked": True,
        }
    return freeze


def valid_yp(sample: SpatialForecastSample, pred: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    y = sample.y_binary()
    p = np.asarray(pred, dtype=np.float64)
    mask = np.isfinite(y) & np.isfinite(p)
    return y[mask], p[mask]


def pixel_counts(sample: SpatialForecastSample) -> dict:
    y = np.asarray(sample.y_flood)
    n = int(y.size)
    n_unk = int(np.sum(y == UNKNOWN))
    n_flood = int(np.sum(y == 1))
    n_dry = int(np.sum(y == 0))
    n_valid = n_flood + n_dry
    return {
        "n_pixels": n,
        "n_valid": n_valid,
        "n_flood": n_flood,
        "n_dry": n_dry,
        "n_unknown": n_unk,
        "unknown_fraction": (n_unk / n) if n else None,
        "flood_fraction_valid": (n_flood / n_valid) if n_valid else None,
    }


def score_vectors(y: np.ndarray, p: np.ndarray, threshold: float = OPERATING_THRESHOLD) -> dict:
    if y.size == 0:
        return {
            "n_valid_pixels": 0,
            "iou": None,
            "dice": None,
            "precision": None,
            "recall": None,
            "auprc": None,
            "auroc": None,
            "brier": None,
            "prevalence": None,
        }
    row = map_metrics(y, p, threshold=threshold)
    op = row.get("operating_point") or {}
    return {
        "n_valid_pixels": int(y.size),
        "iou": _finite(row.get("iou")),
        "dice": _finite(row.get("dice")),
        "precision": _finite(op.get("precision")),
        "recall": _finite(op.get("recall")),
        "auprc": _finite(row.get("auprc")),
        "auroc": _finite(row.get("auroc")),
        "brier": _finite(row.get("brier")),
        "prevalence": _finite(row.get("prevalence")),
        "tp": op.get("tp"),
        "fp": op.get("fp"),
        "fn": op.get("fn"),
        "tn": op.get("tn"),
    }


def map_row(sample: SpatialForecastSample, pred: np.ndarray, threshold: float = OPERATING_THRESHOLD) -> dict:
    y, p = valid_yp(sample, pred)
    row = score_vectors(y, p, threshold=threshold)
    extra = sample.extra or {}
    counts = pixel_counts(sample)
    row.update(counts)
    row.update(
        {
            "event_id": extra.get("event_id"),
            "city_id": sample.city_id,
            "basin_id": extra.get("basin_id"),
            "flood_mechanism": extra.get("flood_mechanism"),
            "valid_at": sample.valid_at,
            "issue_time": sample.issue_time,
            "year": int(sample.valid_at[:4]),
            "split": sample.split,
            "scene_id": sample.scene_id,
        }
    )
    return row


def predict_all(samples: Sequence[SpatialForecastSample], pred_fn) -> List[dict]:
    rows = []
    for sample in samples:
        rows.append(map_row(sample, pred_fn(sample)))
    return rows


def event_rows(map_rows: Sequence[dict], y_store: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> List[dict]:
    """Pool valid pixels of every map that shares an event_id."""
    by_event: Dict[str, List[str]] = {}
    for row in map_rows:
        eid = row.get("event_id")
        if not eid:
            continue
        by_event.setdefault(str(eid), []).append(_map_key_from_row(row))
    out = []
    for eid, keys in sorted(by_event.items()):
        ys = []
        ps = []
        n_unk = n_pix = n_flood = 0
        cities = set()
        years = set()
        mechanisms = set()
        basins = set()
        split = None
        for key in keys:
            if key not in y_store:
                continue
            y, p = y_store[key]
            if y.size:
                ys.append(y)
                ps.append(p)
        matching = [r for r in map_rows if r.get("event_id") == eid]
        for row in matching:
            n_unk += int(row.get("n_unknown") or 0)
            n_pix += int(row.get("n_pixels") or 0)
            n_flood += int(row.get("n_flood") or 0)
            cities.add(row.get("city_id"))
            years.add(row.get("year"))
            mechanisms.add(row.get("flood_mechanism"))
            basins.add(row.get("basin_id"))
            split = row.get("split")
        if not ys:
            scored = score_vectors(np.zeros((0,)), np.zeros((0,)))
        else:
            scored = score_vectors(np.concatenate(ys), np.concatenate(ps))
        scored.update(
            {
                "event_id": eid,
                "n_maps": len(matching),
                "city_ids": sorted(c for c in cities if c),
                "basin_ids": sorted(b for b in basins if b),
                "flood_mechanisms": sorted(m for m in mechanisms if m),
                "years": sorted(int(y) for y in years if y is not None),
                "split": split,
                "n_unknown": n_unk,
                "n_pixels": n_pix,
                "n_flood": n_flood,
                "unknown_fraction": (n_unk / n_pix) if n_pix else None,
            }
        )
        out.append(scored)
    return out


def _map_key(sample: SpatialForecastSample) -> str:
    return f"{sample.city_id}|{sample.scene_id}|{sample.valid_at}"


def _map_key_from_row(row: dict) -> str:
    return f"{row.get('city_id')}|{row.get('scene_id')}|{row.get('valid_at')}"


def store_vectors(samples: Sequence[SpatialForecastSample], pred_fn) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for sample in samples:
        out[_map_key(sample)] = valid_yp(sample, pred_fn(sample))
    return out


def summarize_scores(rows: Sequence[dict], keys: Sequence[str] = ("iou", "dice", "precision", "recall", "auprc", "auroc", "brier")) -> dict:
    summary = {}
    for key in keys:
        vals = [_finite(r.get(key)) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            summary[key] = {"mean": None, "median": None, "std": None, "iqr": None, "n": 0}
            continue
        arr = np.asarray(vals, dtype=np.float64)
        q25, q75 = np.percentile(arr, [25, 75])
        summary[key] = {
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr)),
            "iqr": float(q75 - q25),
            "n": int(arr.size),
        }
    return summary


def micro_from_store(store: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> dict:
    ys = [y for y, _ in store.values() if y.size]
    ps = [p for y, p in store.values() if y.size]
    if not ys:
        return score_vectors(np.zeros((0,)), np.zeros((0,)))
    return score_vectors(np.concatenate(ys), np.concatenate(ps))


def group_event_rows(event_rows_: Sequence[dict], field: str) -> dict:
    buckets: Dict[str, List[dict]] = {}
    for row in event_rows_:
        raw = row.get(field)
        if isinstance(raw, list):
            tokens = [str(x) for x in raw if x]
            if not tokens:
                tokens = ["unknown"]
        else:
            tokens = [str(raw or "unknown")]
        for token in tokens:
            buckets.setdefault(token, []).append(row)
    return {key: summarize_scores(vals) for key, vals in sorted(buckets.items())}


def reliability_diagram(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict:
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    p = np.clip(np.asarray(p, dtype=np.float64).reshape(-1), 0.0, 1.0)
    if y.size == 0:
        return {"ece": None, "n": 0, "bins": [], "status": "NOT CALIBRATED"}
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    ece = 0.0
    occupied = 0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        n = int(np.sum(mask))
        if n == 0:
            bins.append({"bin": i, "lo": float(lo), "hi": float(hi), "n": 0, "mean_pred": None, "mean_obs": None})
            continue
        occupied += 1
        mean_p = float(np.mean(p[mask]))
        mean_y = float(np.mean(y[mask]))
        ece += (n / y.size) * abs(mean_y - mean_p)
        bins.append(
            {
                "bin": i,
                "lo": float(lo),
                "hi": float(hi),
                "n": n,
                "mean_pred": mean_p,
                "mean_obs": mean_y,
                "gap": abs(mean_y - mean_p),
            }
        )
    if occupied <= 1 or ece >= 0.15:
        status = "NOT CALIBRATED"
    elif ece >= 0.05:
        status = "PARTIALLY CALIBRATED"
    else:
        status = "ACCEPTABLE"
    return {
        "ece": float(ece),
        "n": int(y.size),
        "n_occupied_bins": occupied,
        "bins": bins,
        "brier": _finite(brier(y, p)),
        "status": status,
        "note": "Do not reuse Phase 5.5 conformal coverage. Recalibrated on this Track A split only.",
    }


def event_bootstrap_ci(
    event_rows_a: Sequence[dict],
    event_rows_b: Optional[Sequence[dict]] = None,
    metric: str = "iou",
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = RNG_SEED,
) -> dict:
    """Event-level bootstrap. Pixels are not treated as independent trials."""
    ids = [r.get("event_id") for r in event_rows_a if _finite(r.get(metric)) is not None]
    map_a = {r.get("event_id"): _finite(r.get(metric)) for r in event_rows_a}
    map_b = None
    if event_rows_b is not None:
        map_b = {r.get("event_id"): _finite(r.get(metric)) for r in event_rows_b}
        ids = [i for i in ids if map_b.get(i) is not None]
    n = len(ids)
    if n == 0:
        return {"n_events": 0, "mean": None, "ci95": [None, None], "draws": 0}
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_draws):
        take = rng.choice(ids, size=n, replace=True)
        if map_b is None:
            means.append(float(np.mean([map_a[i] for i in take])))
        else:
            means.append(float(np.mean([map_a[i] - map_b[i] for i in take])))
    arr = np.asarray(means, dtype=np.float64)
    lo, hi = np.percentile(arr, [2.5, 97.5])
    point = float(np.mean([map_a[i] if map_b is None else map_a[i] - map_b[i] for i in ids]))
    return {
        "n_events": n,
        "metric": metric,
        "mean": point,
        "bootstrap_mean": float(np.mean(arr)),
        "ci95": [float(lo), float(hi)],
        "draws": n_draws,
        "unit": "event",
        "note": "Event-resampled. Do not interpret pixel counts as independent n.",
    }


def _fit_pixel_models(train: Sequence[SpatialForecastSample], columns: Optional[Sequence[int]], seed: int = RNG_SEED):
    X, y = flatten_pixels(train, columns=columns)
    logistic = LogisticModel(name="pixel_logistic")
    boosting = BoostingModel(name="pixel_gbdt", n_estimators=GBDT_TREES, learning_rate=GBDT_LR)
    if not y.size:
        return logistic, boosting
    if y.size > PIXEL_SUBSAMPLE:
        rng = np.random.default_rng(seed)
        take = rng.choice(y.size, PIXEL_SUBSAMPLE, replace=False)
        X, y = X[take], y[take]
    if y.max() > y.min():
        w = np.where(y > 0.5, (y.size / max(float(np.sum(y > 0.5)), 1.0)), 1.0)
        logistic.fit(X, y, sample_weight=w)
        boosting.fit(X, y, sample_weight=w)
    else:
        logistic.fit(X, y)
        boosting.fit(X, y)
    return logistic, boosting


def _event_macro_iou(samples: Sequence[SpatialForecastSample], pred_fn) -> float:
    store = store_vectors(samples, pred_fn)
    rows = event_rows(predict_all(samples, pred_fn), store)
    vals = [_finite(r.get("iou")) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else 0.0


def choose_rain_threshold(train: Sequence[SpatialForecastSample]) -> dict:
    quantile = fit_rain_threshold(train)
    candidates = sorted(set(RAIN_CANDIDATE_MM) | {round(quantile, 3)})
    scores = []
    for thr in candidates:
        fn = lambda s, t=thr: rain_threshold_map(s, t)
        scores.append({"threshold_mm": float(thr), "train_event_macro_iou": _event_macro_iou(train, fn)})
    best = max(scores, key=lambda r: (r["train_event_macro_iou"] if r["train_event_macro_iou"] is not None else -1.0))
    return {"chosen_mm": best["threshold_mm"], "quantile_0p7_mm": float(quantile), "candidates": scores}


def fit_diagnostic_baselines(samples: Sequence[SpatialForecastSample]) -> dict:
    train = by_split(samples, "train") or list(samples)
    clim = AoiMonthClimatology().fit(train)
    rain = choose_rain_threshold(train)
    all_idx = feature_indices(None)
    no_pers_idx = tuple(i for i, name in enumerate(PIXEL_FEATURE_NAMES) if name not in {"persistence", "persistence_valid"})
    logistic, boosting = _fit_pixel_models(train, all_idx)
    logistic_np, boosting_np = _fit_pixel_models(train, no_pers_idx)
    predict = {
        "persistence": persistence_map,
        "climatology": clim.predict,
        "rain_threshold": lambda s, t=rain["chosen_mm"]: rain_threshold_map(s, t),
        "pixel_logistic": pixel_predict_fn(logistic, columns=all_idx),
        "pixel_gbdt": pixel_predict_fn(boosting, columns=all_idx),
        "conv_smooth": conv_smooth_map,
        "pixel_gbdt_no_persistence": pixel_predict_fn(boosting_np, columns=no_pers_idx),
        "pixel_logistic_no_persistence": pixel_predict_fn(logistic_np, columns=no_pers_idx),
    }
    return {
        "climatology": clim,
        "rain": rain,
        "logistic": logistic,
        "boosting": boosting,
        "logistic_no_persistence": logistic_np,
        "boosting_no_persistence": boosting_np,
        "columns_all": all_idx,
        "columns_no_persistence": no_pers_idx,
        "predict": predict,
        "feature_names": list(PIXEL_FEATURE_NAMES),
    }


def evaluate_model_on_samples(samples: Sequence[SpatialForecastSample], pred_fn, model_name: str) -> dict:
    maps = predict_all(samples, pred_fn)
    store = store_vectors(samples, pred_fn)
    events = event_rows(maps, store)
    micro = micro_from_store(store)
    macro = summarize_scores(events)
    return {
        "model": model_name,
        "n_maps": len(samples),
        "n_events": len(events),
        "micro": micro,
        "event_macro": macro,
        "event_rows": events,
        "map_rows": maps,
        "by_region": group_event_rows(events, "city_ids"),
        "by_basin": group_event_rows(events, "basin_ids"),
        "by_mechanism": group_event_rows(events, "flood_mechanisms"),
        "by_year": group_event_rows(events, "years"),
    }


def permutation_importance(
    samples: Sequence[SpatialForecastSample],
    model,
    columns: Sequence[int],
    seed: int = RNG_SEED,
) -> List[dict]:
    """Event-mean Brier increase after shuffling one feature. Association, not causality."""
    if not samples:
        return []
    rng = np.random.default_rng(seed)
    pred_fn = pixel_predict_fn(model, columns=columns)
    baseline_rows = event_rows(predict_all(samples, pred_fn), store_vectors(samples, pred_fn))
    base_vals = [_finite(r.get("brier")) for r in baseline_rows]
    base_vals = [v for v in base_vals if v is not None]
    base = float(np.mean(base_vals)) if base_vals else None
    names = [PIXEL_FEATURE_NAMES[i] for i in columns]
    out = []
    for local_j, name in enumerate(names):

        def shuffled(sample, j=local_j):
            h, w = sample.y_flood.shape
            ymap = np.asarray(sample.y_flood)
            valid = ymap != UNKNOWN
            result = np.zeros((h, w), dtype=np.float64)
            X, _ = pixel_matrix(sample, columns=columns)
            if X.size == 0:
                return result
            X = np.array(X, copy=True)
            rng.shuffle(X[:, j])
            probs = np.asarray(model.predict_proba(X), dtype=np.float64).reshape(-1)
            result[valid] = probs
            return result

        rows = event_rows(predict_all(samples, shuffled), store_vectors(samples, shuffled))
        vals = [_finite(r.get("brier")) for r in rows]
        vals = [v for v in vals if v is not None]
        mean_b = float(np.mean(vals)) if vals else None
        delta = None if base is None or mean_b is None else float(mean_b - base)
        out.append({"feature": name, "event_macro_brier": mean_b, "delta_brier": delta})
    out.sort(key=lambda r: -(r["delta_brier"] if r["delta_brier"] is not None else -1e9))
    return out


def logistic_coefficients(model: LogisticModel, columns: Sequence[int]) -> List[dict]:
    if model.coef is None:
        return []
    coef = np.asarray(model.coef, dtype=np.float64)
    rows = [{"feature": "intercept", "coefficient": float(coef[0])}]
    for i, col in enumerate(columns):
        rows.append({"feature": PIXEL_FEATURE_NAMES[col], "coefficient": float(coef[i + 1])})
    rows[1:] = sorted(rows[1:], key=lambda r: abs(r["coefficient"]), reverse=True)
    return rows


def compare_to_persistence(model_eval: dict, persist_eval: dict) -> dict:
    a = {r["event_id"]: r for r in model_eval.get("event_rows") or []}
    b = {r["event_id"]: r for r in persist_eval.get("event_rows") or []}
    shared = sorted(set(a) & set(b))
    wins = []
    losses = []
    ties = []
    deltas = []
    for eid in shared:
        ia = _finite(a[eid].get("iou"))
        ib = _finite(b[eid].get("iou"))
        if ia is None or ib is None:
            continue
        d = ia - ib
        deltas.append(d)
        if d > 1e-12:
            wins.append(eid)
        elif d < -1e-12:
            losses.append(eid)
        else:
            ties.append(eid)
    macro_a = (model_eval.get("event_macro") or {}).get("iou") or {}
    macro_b = (persist_eval.get("event_macro") or {}).get("iou") or {}
    return {
        "n_shared_events": len(shared),
        "n_beats_persistence": len(wins),
        "n_loses_to_persistence": len(losses),
        "n_ties": len(ties),
        "beat_event_ids": wins,
        "lose_event_ids": losses,
        "mean_delta_iou": float(np.mean(deltas)) if deltas else None,
        "event_macro_iou_model": macro_a.get("mean"),
        "event_macro_iou_persistence": macro_b.get("mean"),
        "micro_iou_model": (model_eval.get("micro") or {}).get("iou"),
        "micro_iou_persistence": (persist_eval.get("micro") or {}).get("iou"),
        "bootstrap_delta_iou": event_bootstrap_ci(
            model_eval.get("event_rows") or [],
            persist_eval.get("event_rows") or [],
            metric="iou",
        ),
    }


def failure_analysis(evals: Dict[str, dict]) -> dict:
    persist = evals.get("persistence") or {}
    gbdt = evals.get("pixel_gbdt") or {}
    rain = evals.get("rain_threshold") or {}
    clim = evals.get("climatology") or {}
    events_p = {r["event_id"]: r for r in persist.get("event_rows") or []}
    events_g = {r["event_id"]: r for r in gbdt.get("event_rows") or []}
    events_r = {r["event_id"]: r for r in rain.get("event_rows") or []}

    def _best_worst(rows, metric="iou"):
        scored = [r for r in rows if _finite(r.get(metric)) is not None]
        if not scored:
            return {"best": None, "worst": None}
        best = max(scored, key=lambda r: r[metric])
        worst = min(scored, key=lambda r: r[metric])
        return {
            "best": {"event_id": best.get("event_id"), metric: best.get(metric), "unknown_fraction": best.get("unknown_fraction")},
            "worst": {"event_id": worst.get("event_id"), metric: worst.get(metric), "unknown_fraction": worst.get("unknown_fraction")},
        }

    high_unknown = [
        {"event_id": r.get("event_id"), "unknown_fraction": r.get("unknown_fraction"), "n_flood": r.get("n_flood")}
        for r in persist.get("event_rows") or []
        if (r.get("unknown_fraction") or 0) >= 0.5
    ]
    low_flood = [
        {"event_id": r.get("event_id"), "n_flood": r.get("n_flood"), "unknown_fraction": r.get("unknown_fraction")}
        for r in persist.get("event_rows") or []
        if int(r.get("n_flood") or 0) <= 50
    ]
    persist_dominates = []
    rain_helps = []
    for eid, prow in events_p.items():
        grow = events_g.get(eid) or {}
        rrow = events_r.get(eid) or {}
        pi = _finite(prow.get("iou")) or 0.0
        gi = _finite(grow.get("iou"))
        ri = _finite(rrow.get("iou"))
        if gi is not None and pi >= gi:
            persist_dominates.append(eid)
        if ri is not None and pi is not None and ri > pi:
            rain_helps.append(eid)
    return {
        "persistence": _best_worst(persist.get("event_rows") or []),
        "pixel_gbdt": _best_worst(gbdt.get("event_rows") or []),
        "climatology": _best_worst(clim.get("event_rows") or []),
        "high_unknown_events": high_unknown,
        "low_flood_events": low_flood,
        "persistence_dominates_gbdt": persist_dominates,
        "rain_beats_persistence": rain_helps,
        "note": (
            "Winter residual GFM clusters have very few flood pixels. High unknown is a label-quality "
            "issue, not a model ranking. Persistence can dominate when inundation is slow-moving."
        ),
    }


def run_ablations(train: Sequence[SpatialForecastSample], eval_samples: Sequence[SpatialForecastSample]) -> dict:
    rows = {}
    for name, groups in ABLATION_GROUPS.items():
        cols = feature_indices(None if name == "F_all" else groups)
        _logistic, boosting = _fit_pixel_models(train, cols)
        pred = pixel_predict_fn(boosting, columns=cols)
        scored = evaluate_model_on_samples(eval_samples, pred, f"gbdt_{name}")
        rows[name] = {
            "groups": list(groups),
            "n_features": len(cols),
            "features": [PIXEL_FEATURE_NAMES[i] for i in cols],
            "event_macro_iou": (scored.get("event_macro") or {}).get("iou"),
            "micro_iou": (scored.get("micro") or {}).get("iou"),
            "event_macro_auprc": (scored.get("event_macro") or {}).get("auprc"),
            "n_events": scored.get("n_events"),
        }
    return rows


def geographic_holdout_eval(samples: Sequence[SpatialForecastSample]) -> dict:
    geo_train = [s for s in samples if geographic_split(s.city_id) != "test"]
    geo_test = [s for s in samples if geographic_split(s.city_id) == "test"]
    geo_test_aois = sorted(GEO_TEST_AOIS)
    train_only = []
    test_only = []
    mixed = []
    by_event: Dict[str, set] = {}
    for sample in samples:
        eid = (sample.extra or {}).get("event_id")
        if not eid:
            continue
        by_event.setdefault(eid, set()).add(sample.city_id)
    for eid, cities in by_event.items():
        test_hit = bool(cities & set(GEO_TEST_AOIS))
        train_hit = bool(cities - set(GEO_TEST_AOIS))
        if test_hit and train_hit:
            mixed.append(eid)
        elif test_hit:
            test_only.append(eid)
        else:
            train_only.append(eid)
    strict_status = "INSUFFICIENT DATA" if len(test_only) < 3 or len(train_only) < 3 else "RUNNABLE"
    city_level = None
    if geo_train and geo_test:
        saved = [(s, s.split) for s in geo_train + geo_test]
        try:
            for s in geo_train:
                s.split = "train"
            for s in geo_test:
                s.split = "test"
            fitted = fit_diagnostic_baselines(geo_train + geo_test)
            city_level = {
                "persistence": evaluate_model_on_samples(geo_test, fitted["predict"]["persistence"], "persistence"),
                "pixel_gbdt": evaluate_model_on_samples(geo_test, fitted["predict"]["pixel_gbdt"], "pixel_gbdt"),
            }
            for name in ("persistence", "pixel_gbdt"):
                city_level[name] = {
                    "event_macro_iou": (city_level[name].get("event_macro") or {}).get("iou"),
                    "micro_iou": (city_level[name].get("micro") or {}).get("iou"),
                    "n_events": city_level[name].get("n_events"),
                    "n_maps": city_level[name].get("n_maps"),
                }
        finally:
            for s, split in saved:
                s.split = split
    return {
        "status": strict_status,
        "headline": "GEOGRAPHIC GENERALIZATION TEST: INSUFFICIENT DATA"
        if strict_status == "INSUFFICIENT DATA"
        else "RAN EXISTING CITY HOLDOUT",
        "geo_test_aois": geo_test_aois,
        "n_geo_train_maps": len(geo_train),
        "n_geo_test_maps": len(geo_test),
        "strict_event_holdout": {
            "train_only_events": sorted(train_only),
            "test_only_events": sorted(test_only),
            "mixed_events": sorted(mixed),
            "note": (
                "Most meteorological events span Dhaka subtiles and haor AOIs. A city-level "
                "geographic split therefore leaks the same event_id into both sides. The strict "
                "event-exclusive holdout is the scientifically valid test; n is too small here."
            ),
        },
        "city_level_existing_split": city_level,
        "warning": (
            "The existing geographic_split is AOI-based, not event-based. Same-event tiles can "
            "appear in both geographic train and test. Do not claim geographic generalization."
        ),
    }


def leakage_report(samples: Sequence[SpatialForecastSample]) -> dict:
    problems = []
    for i, sample in enumerate(samples):
        errs = check_spatial_sample(sample)
        if errs:
            problems.append(f"{sample.city_id} {sample.issue_time}: {errs}")
        try:
            assert_persistence_is_lagged(sample)
        except Exception as exc:  # LeakageError
            problems.append(f"persistence {sample.city_id} {sample.issue_time}: {exc}")
        kinds = sample.x_precip_hourly_kind or []
        if any(k == "FORECAST" for k in kinds):
            problems.append(f"forecast rain {sample.city_id} {sample.issue_time}")
        extra = sample.extra or {}
        if extra.get("future_rain_as_feature") or extra.get("era5_at_valid_as_feature"):
            problems.append(f"future rain flag {sample.city_id}")
    try:
        assert_no_spatial_leakage(samples)
        closed = True
    except Exception as exc:
        closed = False
        problems.append(str(exc))
    return {
        "pass": closed and not problems,
        "n_problems": len(problems),
        "problems": problems[:20],
        "unknown_never_dry": unknown_never_scored_as_dry(samples),
        "horizon_hours_unique": sorted({s.horizon_hours for s in samples}),
        "future_horizons_used": False,
    }


def classify_outcome(gate: dict) -> str:
    a_ok = bool((gate.get("A") or {}).get("pass"))
    b_ok = bool((gate.get("B") or {}).get("pass"))
    c_ok = bool((gate.get("C") or {}).get("pass"))
    d_ok = bool((gate.get("D") or {}).get("pass"))
    if not (a_ok and b_ok and c_ok and d_ok):
        return "INSUFFICIENT DATA"
    f = gate.get("F") or {}
    g = gate.get("G") or {}
    if f.get("diagnostically_promising") and g.get("pass"):
        return "DIAGNOSTICALLY PROMISING"
    if f.get("diagnostically_promising"):
        return "MIXED"
    if f.get("mixed") or f.get("learned_beats_persistence_macro"):
        return "MIXED"
    if f.get("persistence_strongest"):
        return "WEAK"
    if g.get("status") == "INSUFFICIENT DATA":
        return "INSUFFICIENT DATA"
    return "WEAK"


def evaluate_gates_67(report: dict) -> dict:
    freeze = report.get("freeze") or {}
    leakage = report.get("leakage") or {}
    metrics_ok = bool(report.get("splits"))
    event_ok = all(
        (row.get("pixel_gbdt") or {}).get("n_events", 0) >= 1
        for row in (report.get("splits") or {}).values()
        if isinstance(row, dict) and "pixel_gbdt" in row
    )
    ablations = report.get("ablations") or {}
    held = (report.get("splits") or {}).get("val_test") or (report.get("splits") or {}).get("test") or {}
    persist = held.get("persistence") or {}
    gbdt = held.get("pixel_gbdt") or {}
    gbdt_np = held.get("pixel_gbdt_no_persistence") or {}
    cmp_all = (held.get("comparisons") or {}).get("pixel_gbdt") or {}
    cmp_np = (held.get("comparisons") or {}).get("pixel_gbdt_no_persistence") or {}
    n_shared = int(cmp_np.get("n_shared_events") or cmp_all.get("n_shared_events") or 0)
    n_beats = int(cmp_np.get("n_beats_persistence") or 0)
    macro_delta = cmp_np.get("mean_delta_iou")
    ci = ((cmp_np.get("bootstrap_delta_iou") or {}).get("ci95") or [None, None])
    ci_lo, ci_hi = ci[0], ci[1]
    beats_macro = (
        _finite((gbdt_np.get("event_macro") or {}).get("iou", {}).get("mean")) is not None
        and _finite((persist.get("event_macro") or {}).get("iou", {}).get("mean")) is not None
        and (gbdt_np.get("event_macro") or {}).get("iou", {}).get("mean")
        > (persist.get("event_macro") or {}).get("iou", {}).get("mean")
    )
    ci_excludes_zero = ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0)
    calib_status = ((report.get("splits") or {}).get("val_test") or {}).get("calibration_pixel_gbdt", {}).get("status")
    promising = bool(
        beats_macro
        and n_beats >= 2
        and n_shared >= 3
        and leakage.get("pass")
        and calib_status in {"PARTIALLY CALIBRATED", "ACCEPTABLE"}
    )
    mixed = (bool(beats_macro) or n_beats >= 1) and not promising
    persist_mean = _finite(((persist.get("event_macro") or {}).get("iou") or {}).get("mean"))
    gbdt_mean = _finite(((gbdt.get("event_macro") or {}).get("iou") or {}).get("mean"))
    persist_strongest = persist_mean is not None and gbdt_mean is not None and persist_mean >= gbdt_mean and not beats_macro
    geo = report.get("geographic") or {}
    gates = {
        "A": {
            "name": "Baseline reproducibility",
            "pass": bool(freeze.get("config_sha256")) and bool((freeze.get("split_lock") or {}).get("ok")),
            "detail": freeze.get("config_sha256"),
        },
        "B": {"name": "No leakage", "pass": bool(leakage.get("pass")), "detail": leakage.get("n_problems")},
        "C": {
            "name": "Metric integrity",
            "pass": bool(metrics_ok) and bool(leakage.get("unknown_never_dry")),
            "detail": "valid pixels only; unknown=255 never dry; micro and event-macro both reported",
        },
        "D": {"name": "Event-level evaluation", "pass": bool(event_ok), "detail": "per-event IoU/Dice/AUPRC/Brier"},
        "E": {
            "name": "Feature-signal diagnosis",
            "pass": bool(ablations),
            "detail": sorted(ablations.keys()),
        },
        "F": {
            "name": "Baseline competitiveness",
            "pass": None,
            "learned_beats_persistence_macro": bool(beats_macro),
            "n_events_learned_beats_persistence": n_beats,
            "n_shared_events": n_shared,
            "mean_delta_iou_no_persistence": macro_delta,
            "bootstrap_ci95_delta_iou": [ci_lo, ci_hi],
            "ci_excludes_zero": bool(ci_excludes_zero),
            "diagnostically_promising": promising,
            "mixed": mixed and not promising,
            "persistence_strongest": persist_strongest,
            "note": (
                "Learned models that include persistence as a feature are not a fair beat-persistence "
                "test. Gate F uses pixel_gbdt_no_persistence on held-out events."
            ),
        },
        "G": {
            "name": "Generalization evidence",
            "pass": geo.get("status") == "RUNNABLE" and bool((geo.get("city_level_existing_split") or {}).get("pixel_gbdt")),
            "status": geo.get("status") or "INSUFFICIENT DATA",
            "headline": geo.get("headline"),
        },
    }
    outcome = classify_outcome(gates)
    gates["F"]["classification"] = outcome
    return {"gates": gates, "classification": outcome, "validated": False}


def ranking_table(evals: Dict[str, dict]) -> List[dict]:
    rows = []
    for name in HEADLINE_MODELS:
        ev = evals.get(name)
        if not ev:
            continue
        macro = ev.get("event_macro") or {}
        micro = ev.get("micro") or {}
        rows.append(
            {
                "model": name,
                "event_macro_iou": (macro.get("iou") or {}).get("mean"),
                "micro_iou": micro.get("iou"),
                "event_macro_dice": (macro.get("dice") or {}).get("mean"),
                "micro_dice": micro.get("dice"),
                "event_macro_auprc": (macro.get("auprc") or {}).get("mean"),
                "micro_auprc": micro.get("auprc"),
                "event_macro_recall": (macro.get("recall") or {}).get("mean"),
                "event_macro_precision": (macro.get("precision") or {}).get("mean"),
                "event_macro_brier": (macro.get("brier") or {}).get("mean"),
                "micro_brier": micro.get("brier"),
                "n_events": ev.get("n_events"),
            }
        )
    rows.sort(key=lambda r: (r["event_macro_iou"] is None, -(r["event_macro_iou"] or -1)))
    return rows


def _eval_split_bundle(samples: Sequence[SpatialForecastSample], fitted: dict) -> dict:
    evals = {}
    for name, fn in fitted["predict"].items():
        evals[name] = evaluate_model_on_samples(samples, fn, name)
    persist = evals["persistence"]
    comparisons = {
        name: compare_to_persistence(evals[name], persist)
        for name in evals
        if name != "persistence"
    }
    y_val = []
    p_val = []
    gbdt_store = store_vectors(samples, fitted["predict"]["pixel_gbdt"])
    for y, p in gbdt_store.values():
        if y.size:
            y_val.append(y)
            p_val.append(p)
    calib = reliability_diagram(
        np.concatenate(y_val) if y_val else np.zeros((0,)),
        np.concatenate(p_val) if p_val else np.zeros((0,)),
    )
    return {
        "n_maps": len(samples),
        "n_events": len({(s.extra or {}).get("event_id") for s in samples}),
        "models": evals,
        "ranking": ranking_table(evals),
        "comparisons": comparisons,
        "calibration_pixel_gbdt": calib,
        "persistence": persist,
        "pixel_gbdt": evals.get("pixel_gbdt"),
        "pixel_gbdt_no_persistence": evals.get("pixel_gbdt_no_persistence"),
        "climatology": evals.get("climatology"),
        "rain_threshold": evals.get("rain_threshold"),
        "pixel_logistic": evals.get("pixel_logistic"),
        "conv_smooth": evals.get("conv_smooth"),
        "failure": failure_analysis(evals),
    }


def write_markdown_report(report: dict) -> str:
    freeze = report.get("freeze") or {}
    gates = (report.get("gates_67") or {}).get("gates") or {}
    classification = (report.get("gates_67") or {}).get("classification")
    test = (report.get("splits") or {}).get("test") or {}
    val = (report.get("splits") or {}).get("val") or {}
    held = (report.get("splits") or {}).get("val_test") or {}
    geo = report.get("geographic") or {}
    lines = [
        "# Phase 6.7 — Track A diagnostic baselines",
        "",
        "**Status:** DIAGNOSTIC BASELINE STUDY. Not a VALIDATED claim. Not a production model.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.",
        "",
        "**AOI GBDT:** VALIDATED status **unchanged** (separate registry).",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified.",
        "",
        f"**Dataset version:** `{freeze.get('dataset_version')}`",
        "",
        f"**Experiment id:** `{EXPERIMENT_ID}`",
        "",
        f"**Config hash:** `{freeze.get('config_sha256')}`",
        "",
        f"**Diagnostic classification:** **{classification}**",
        "",
        "---",
        "",
        "## 1. Objective",
        "",
        "Measure whether the frozen 15-event GFM Track A cube contains causal predictive signal",
        "beyond persistence, climatology, and a rainfall threshold. This phase trains only",
        "diagnostic baselines (no CNN, U-Net, or transformer) and does not promote spatial AI.",
        "",
        "## 2. Frozen dataset definition",
        "",
        f"- Dataset version: `{freeze.get('dataset_version')}` (expected `{SPATIAL_DATASET_VERSION_V21}`)",
        f"- Independent events: **{freeze.get('n_independent_events')}**",
        f"- Maps / tiles: **{freeze.get('n_maps')}**",
        f"- Train events ({len(freeze.get('train_events') or [])}): `{', '.join(freeze.get('train_events') or [])}`",
        f"- Val events ({len(freeze.get('validation_events') or [])}): `{', '.join(freeze.get('validation_events') or [])}`",
        f"- Test events ({len(freeze.get('test_events') or [])}): `{', '.join(freeze.get('test_events') or [])}`",
        f"- Regions: `{', '.join(freeze.get('regions') or [])}`",
        f"- Target: binary occurrence at t0+{HORIZON_HOURS} h; τ={FLOOD_FRACTION_TAU}; unknown={UNKNOWN}",
        f"- Pixels (all maps): `{json.dumps(freeze.get('pixels') or {}, default=str)}`",
        "",
        "## 3. Label vs working-grid resolution",
        "",
        "| Quantity | Value |",
        "| --- | --- |",
        f"| Observation / label native resolution | **{LABEL_RESOLUTION_M} m** Equi7 AS020M |",
        f"| Working tensor | **{WORKING_GRID}×{WORKING_GRID}** on AOI bounds |",
        f"| Working cell sizes (m) | `{freeze.get('working_cell_size_m_by_aoi')}` |",
        "",
        "The working grid is **not** a 20 m CNN grid. Do not describe 64×64 tensors as native GFM resolution.",
        "",
        "## 4. Event splits",
        "",
        "Frozen event-temporal split from `splits_v2/splits.json`. Pixel-i.i.d. forbidden.",
        "Primary temporal test = 2022 named holdout + later years. Same `event_id` cannot occupy two splits.",
        "",
        "## 5. Feature inventory",
        "",
        "Causal features known at t0 only (18 pixel columns):",
        "",
        ", ".join(f"`{n}`" for n in PIXEL_FEATURE_NAMES),
        "",
        "Rain lookback ends at t0. Persistence `valid_at < t0`. GloFAS Q is MODELLED scalar lookback.",
        "6/12/24/48/72 h spatial labels are not used.",
        "",
        "## 6. Baseline definitions",
        "",
        "| Baseline | Inputs | Notes |",
        "| --- | --- | --- |",
        "| Persistence | last completed GFM before t0 | unknown persistence → 0 |",
        "| Climatology | train AOI×month flood frequency | AOI-aware; not a stacked multi-AOI grid |",
        "| Rain threshold | causal 24 h rain map | small threshold set, chosen on train event-macro IoU |",
        "| Logistic | 18 causal pixel features | class-weighted |",
        "| Pixel GBDT | 18 causal pixel features | existing numpy GBDT, 20 trees, new Track A experiment |",
        "| Conv-smooth | 3×3 mean of persistence | neighborhood baseline, not a CNN |",
        "| GBDT no-persistence | 16 features, persistence dropped | fair beat-persistence probe |",
        "",
        f"Rain threshold chosen: `{((report.get('fitted') or {}).get('rain') or {})}`",
        "",
        "## 7. Leakage controls",
        "",
        f"`{(report.get('leakage') or {})}`",
        "",
        "Train/val/test event leaks must be empty. FORECAST-kind rain is forbidden in lookback.",
        "",
        "## 8. Unknown-mask handling",
        "",
        "GFM 255 remains unknown. Metrics use finite / non-255 pixels only. Unknown is never scored as dry,",
        "flooded, or probability zero. Every metric table includes valid counts and unknown fraction.",
        "",
        "## 9. Overall metrics",
        "",
        "Headline ranking uses **event-macro IoU** first. Micro-IoU is also reported because large events",
        "would otherwise dominate.",
        "",
        "### Test split ranking",
        "",
        _md_table(test.get("ranking") or []),
        "",
        "### Val+test (held-out temporal, 8 events) ranking",
        "",
        _md_table(held.get("ranking") or []),
        "",
        "## 10. Event-level metrics",
        "",
        "### Test events — persistence",
        "",
        _md_event_table((test.get("persistence") or {}).get("event_rows") or []),
        "",
        "### Test events — pixel GBDT (all features)",
        "",
        _md_event_table((test.get("pixel_gbdt") or {}).get("event_rows") or []),
        "",
        "### Test events — GBDT without persistence",
        "",
        _md_event_table((test.get("pixel_gbdt_no_persistence") or {}).get("event_rows") or []),
        "",
        "### Val events — persistence vs GBDT",
        "",
        _md_event_table((val.get("persistence") or {}).get("event_rows") or []),
        "",
        _md_event_table((val.get("pixel_gbdt") or {}).get("event_rows") or []),
        "",
        "## 11. Geographic metrics",
        "",
        f"Status: **{geo.get('headline') or geo.get('status')}**",
        "",
        "```json",
        json.dumps(_jsonable({k: geo[k] for k in geo if k != "city_level_existing_split"}), indent=2, default=str),
        "```",
        "",
        f"City-level existing holdout (AOI split, event-leak warning): `{_jsonable(geo.get('city_level_existing_split'))}`",
        "",
        "Per-region event-macro (val+test GBDT):",
        "",
        f"`{_jsonable((held.get('pixel_gbdt') or {}).get('by_region'))}`",
        "",
        "Sylhet n is too small to claim generalization. Sunamganj / Netrokona / Dhaka / Kishoreganj are reported separately.",
        "",
        "## 12. Temporal metrics",
        "",
        f"By year (val+test GBDT): `{_jsonable((held.get('pixel_gbdt') or {}).get('by_year'))}`",
        "",
        f"By mechanism: `{_jsonable((held.get('pixel_gbdt') or {}).get('by_mechanism'))}`",
        "",
        "Official test n=3 events. That is not a statistically useful temporal holdout on its own;",
        "val+test (8 events) is the diagnostic temporal window. Still underpowered.",
        "",
        "## 13. Ablation results",
        "",
        "GBDT retrained on train events only; scored on val+test. Persistence is excluded from A–E.",
        "",
        f"`{_jsonable(report.get('ablations'))}`",
        "",
        "## 14. Feature importance",
        "",
        "Association / predictive contribution ≠ physical causality.",
        "",
        "### Logistic coefficients (all features)",
        "",
        f"`{_jsonable(report.get('logistic_coefficients'))}`",
        "",
        "### GBDT permutation importance (val events, Δ event-macro Brier)",
        "",
        f"`{_jsonable(report.get('permutation_importance'))}`",
        "",
        "## 15. Calibration",
        "",
        "Phase 5.5 conformal coverage is **not** reused.",
        "",
        f"Val+test GBDT reliability: `{_jsonable((held.get('calibration_pixel_gbdt')))}`",
        "",
        f"Test GBDT reliability: `{_jsonable((test.get('calibration_pixel_gbdt')))}`",
        "",
        "## 16. Bootstrap / uncertainty",
        "",
        "Event-resampled 95% intervals. Pixel significance tests are not used.",
        "",
        f"Val+test GBDT vs persistence (no-persistence GBDT) ΔIoU: `{_jsonable(((held.get('comparisons') or {}).get('pixel_gbdt_no_persistence') or {}).get('bootstrap_delta_iou'))}`",
        "",
        f"Test persistence event-macro IoU: `{_jsonable(((test.get('persistence') or {}).get('event_macro') or {}).get('iou'))}`",
        "",
        "## 17. Failure analysis",
        "",
        f"Val+test: `{_jsonable(held.get('failure'))}`",
        "",
        f"Test: `{_jsonable(test.get('failure'))}`",
        "",
        "## 18. Persistence comparison",
        "",
        "The fair question is whether a **causal learned model without the persistence map**",
        "beats persistence on event-macro IoU across multiple held-out events.",
        "",
        f"Val+test comparisons: `{_jsonable(held.get('comparisons'))}`",
        "",
        f"Test comparisons: `{_jsonable(test.get('comparisons'))}`",
        "",
        "## 19. Scientific interpretation",
        "",
        f"**Classification: {classification}.**",
        "",
        report.get("interpretation") or "",
        "",
        "## 20. Limitations",
        "",
        "- Official Gate B still FAIL (15 < 20 independent GFM events).",
        "- Test split has 3 events; bootstrap intervals are wide.",
        "- Winter GFM clusters have near-zero flood pixels.",
        "- ~35% unknown GFM pixels; some AOIs (Dhaka NE) are mostly nodata.",
        "- Working grid is ~0.5–1 km, not 20 m.",
        "- Geographic holdout is AOI-based and mixes the same events unless restricted to exclusive events.",
        "- Rain is ERA5-Land / Open-Meteo lattice, coarse on haor AOIs.",
        "- 192 h is not a 6–72 h forecast.",
        "",
        "## 21. Recommendation for next phase",
        "",
        report.get("next_phase") or "",
        "",
        "---",
        "",
        "## Gate 6.7A–G",
        "",
        _md_gates(gates),
        "",
        f"**Overall diagnostic class:** {classification}",
        "",
        "These gates do **not** define VALIDATED.",
        "",
        "---",
        "",
        "SPATIAL AI:",
        "NOT_VALIDATED",
        "",
        "SPATIAL API:",
        "UNAVAILABLE",
        "",
        "MODEL TRAINING:",
        "DIAGNOSTIC BASELINES ONLY",
        "",
        "SOLVER MODIFIED:",
        "NO",
        "",
        "END.",
        "",
    ]
    return "\n".join(lines)


def _md_table(rows: Sequence[dict]) -> str:
    if not rows:
        return "_no rows_"
    keys = [
        "model",
        "event_macro_iou",
        "micro_iou",
        "event_macro_dice",
        "event_macro_auprc",
        "event_macro_recall",
        "event_macro_precision",
        "event_macro_brier",
        "n_events",
    ]
    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_fmt(row.get(k)) for k in keys) + " |")
    return "\n".join([header, sep, *body])


def _md_event_table(rows: Sequence[dict]) -> str:
    if not rows:
        return "_no events_"
    keys = ["event_id", "iou", "dice", "precision", "recall", "auprc", "brier", "n_valid_pixels", "n_flood", "unknown_fraction"]
    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body = ["| " + " | ".join(_fmt(r.get(k)) for k in keys) + " |" for r in rows]
    return "\n".join([header, sep, *body])


def _md_gates(gates: dict) -> str:
    lines = ["| Gate | Name | Pass / status | Detail |", "| --- | --- | --- | --- |"]
    for letter, row in gates.items():
        lines.append(
            f"| 6.7{letter} | {row.get('name')} | {row.get('pass') if letter != 'F' else row.get('classification') or row.get('pass')} | {_fmt(row.get('detail') or row.get('status') or row.get('headline'))} |"
        )
    return "\n".join(lines)


def _fmt(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.4f}"
    if isinstance(val, (list, dict)):
        return "`" + json.dumps(val, default=str)[:180] + "`"
    return str(val)


def evaluate_phase67(
    *,
    processed_dir: Optional[Path] = None,
    samples: Optional[Sequence[SpatialForecastSample]] = None,
    meta: Optional[dict] = None,
    expected_splits: Optional[dict] = None,
    out_dir: Optional[Path] = None,
    write_artifacts: bool = True,
    run_geographic: bool = True,
    run_ablations_flag: bool = True,
    run_importance: bool = True,
    write_docs: bool = False,
    lock_splits: bool = True,
) -> dict:
    if samples is None:
        samples, meta = build_spatial_samples_v2(processed_dir=processed_dir)
    else:
        samples = list(samples)
        meta = meta or {"dataset_version": samples[0].dataset_version if samples else None, "label_kind": samples[0].label_kind if samples else None}
    if not samples:
        raise RuntimeError(meta.get("reason") if isinstance(meta, dict) else "no Track A samples")

    freeze = dataset_freeze(samples, meta, expected_splits=expected_splits, lock_splits=lock_splits)
    leakage = leakage_report(samples)
    fitted = fit_diagnostic_baselines(samples)
    train = by_split(samples, "train")
    val = by_split(samples, "val")
    test = by_split(samples, "test")
    val_test = val + test

    splits = {
        "train": _eval_split_bundle(train, fitted) if train else {},
        "val": _eval_split_bundle(val, fitted) if val else {},
        "test": _eval_split_bundle(test, fitted) if test else {},
        "val_test": _eval_split_bundle(val_test, fitted) if val_test else {},
    }
    ablations = run_ablations(train, val_test) if run_ablations_flag and train and val_test else {}
    geo = geographic_holdout_eval(samples) if run_geographic else {"status": "SKIPPED"}
    importance = []
    coefs = []
    if run_importance and val:
        importance = permutation_importance(val, fitted["boosting"], fitted["columns_all"])
        coefs = logistic_coefficients(fitted["logistic"], fitted["columns_all"])

    held = splits.get("val_test") or {}
    cmp_np = (held.get("comparisons") or {}).get("pixel_gbdt_no_persistence") or {}
    interpretation = (
        "Event-macro metrics are the scientific headline because events, not pixels, are independent. "
        "Micro metrics overweight large, well-observed maps. A pooled-pixel win over persistence is not "
        "enough. With 15 independent events (7/5/3 split) this study is underpowered; intervals are wide."
    )
    next_phase = (
        "Do not promote spatial AI. Do not enable `/api/v1/forecast/ai-spatial`. "
        "If classification is INSUFFICIENT DATA or WEAK: expand independent GFM events or improve "
        "label coverage before any CNN. If MIXED: keep GBDT as the bar and collect more monsoon events. "
        "Track B/C remain blocked. Official Gate B stays FAIL until 20 GFM events."
    )

    spatial_reg = load_spatial_registry()
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "experiment_id": EXPERIMENT_ID,
        "catalog_status": "NOT_VALIDATED",
        "public_spatial_status": public_spatial_status(spatial_reg),
        "spatial_registry_status": spatial_reg.get("status"),
        "promoted_to_validated": False,
        "spatial_api": "UNAVAILABLE",
        "model_training": "DIAGNOSTIC BASELINES ONLY",
        "solver_modified": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
        "freeze": freeze,
        "leakage": leakage,
        "fitted": {"rain": fitted.get("rain"), "n_pixel_features": N_PIXEL_FEATURES, "gbdt_trees": GBDT_TREES},
        "splits": {
            name: {
                k: v
                for k, v in bundle.items()
                if k
                not in {
                    # map_rows are large; keep event_rows
                }
            }
            for name, bundle in splits.items()
        },
        "ablations": ablations,
        "geographic": geo,
        "permutation_importance": importance,
        "logistic_coefficients": coefs,
        "interpretation": interpretation,
        "next_phase": next_phase,
        "cnn_trained": False,
        "unet_trained": False,
        "transformer_trained": False,
    }
    # Drop bulky per-map rows from the persisted JSON; keep event_rows.
    for bundle in (report["splits"] or {}).values():
        for model_name in list((bundle.get("models") or {}).keys()):
            model = bundle["models"][model_name]
            model.pop("map_rows", None)
        for alias in HEADLINE_MODELS:
            if isinstance(bundle.get(alias), dict):
                bundle[alias].pop("map_rows", None)
                if "models" in bundle and alias in bundle["models"]:
                    bundle[alias]["event_rows"] = bundle["models"][alias].get("event_rows")
                    bundle[alias]["event_macro"] = bundle["models"][alias].get("event_macro")
                    bundle[alias]["micro"] = bundle["models"][alias].get("micro")
                    bundle[alias]["n_events"] = bundle["models"][alias].get("n_events")
                    bundle[alias]["by_region"] = bundle["models"][alias].get("by_region")
                    bundle[alias]["by_year"] = bundle["models"][alias].get("by_year")
                    bundle[alias]["by_mechanism"] = bundle["models"][alias].get("by_mechanism")
                    bundle[alias]["by_basin"] = bundle["models"][alias].get("by_basin")
                    bundle[alias].pop("map_rows", None)

    report["gates_67"] = evaluate_gates_67(report)
    report["headline"] = {
        "classification": report["gates_67"]["classification"],
        "n_independent_events": freeze.get("n_independent_events"),
        "train_val_test_events": [
            len(freeze.get("train_events") or []),
            len(freeze.get("validation_events") or []),
            len(freeze.get("test_events") or []),
        ],
        "label_resolution_m": LABEL_RESOLUTION_M,
        "working_grid": freeze.get("working_grid"),
        "test_ranking": (splits.get("test") or {}).get("ranking"),
        "val_test_ranking": (splits.get("val_test") or {}).get("ranking"),
        "persistence_comparison_val_test": cmp_np,
    }

    if write_artifacts:
        dest = Path(out_dir or OUT_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        payload = _jsonable(report)
        (dest / "config.json").write_text(
            json.dumps(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "dataset_version": freeze.get("dataset_version"),
                    "config_sha256": freeze.get("config_sha256"),
                    "operating_threshold": OPERATING_THRESHOLD,
                    "gbdt_trees": GBDT_TREES,
                    "pixel_subsample": PIXEL_SUBSAMPLE,
                    "rng_seed": RNG_SEED,
                    "rain": fitted.get("rain"),
                    "label_resolution_m": LABEL_RESOLUTION_M,
                    "working_grid": WORKING_GRID,
                    "horizon_hours": HORIZON_HOURS,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / "dataset_freeze.json").write_text(json.dumps(_jsonable(freeze), indent=2), encoding="utf-8")
        (dest / "split_manifest_ref.json").write_text(
            json.dumps({"path": str(SPLITS_PATH), "lock": freeze.get("split_lock")}, indent=2, default=str),
            encoding="utf-8",
        )
        (dest / "metrics.json").write_text(json.dumps(_jsonable(report.get("headline")), indent=2), encoding="utf-8")
        (dest / "event_metrics.json").write_text(
            json.dumps(
                {
                    name: {
                        model: (bundle.get("models") or {}).get(model, {}).get("event_rows")
                        for model in HEADLINE_MODELS
                    }
                    for name, bundle in (report.get("splits") or {}).items()
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / "ablations.json").write_text(json.dumps(_jsonable(ablations), indent=2), encoding="utf-8")
        (dest / "feature_importance.json").write_text(
            json.dumps({"permutation": _jsonable(importance), "logistic": _jsonable(coefs)}, indent=2),
            encoding="utf-8",
        )
        (dest / "calibration.json").write_text(
            json.dumps(
                {
                    "val_test": _jsonable((held.get("calibration_pixel_gbdt"))),
                    "test": _jsonable(((splits.get("test") or {}).get("calibration_pixel_gbdt"))),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / "phase67_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if write_docs:
            REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        md = write_markdown_report(report)
        (dest / "PHASE_6_7_TRACK_A_BASELINES_REPORT.md").write_text(md, encoding="utf-8")
        if write_docs:
            report_path = Path("docs/PHASE_6_7_TRACK_A_BASELINES_REPORT.md")
            report_path.write_text(md, encoding="utf-8")
            report["report_md"] = str(report_path)
        report["artifact_dir"] = str(dest)
    return report
