"""Phase 5.5 evaluation: inventory, baselines, U-Net, holdouts, uncertainty.

Never marks the spatial registry VALIDATED. Writes a JSON report only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from floodlens.ml.spatial.baselines import evaluate_spatial_baselines, fit_spatial_baselines
from floodlens.ml.spatial.builder import build_spatial_samples, load_index
from floodlens.ml.spatial.dem_plan import DEM_INGESTION_PLAN
from floodlens.ml.spatial.events import (
    MIN_EVENTS_FOR_VALIDATION,
    inventory,
    same_event_across_splits,
    same_event_in_train_and_test,
)
from floodlens.ml.spatial.eval_spatial import (
    conformal_heldout,
    event_metrics,
    map_metrics,
    subset_metrics,
    uncertainty_error_correlation,
)
from floodlens.ml.spatial.labels import scene_quality_table
from floodlens.ml.spatial.schema import SPATIAL_DIR, SPATIAL_MODEL_ID, SpatialForecastSample
from floodlens.ml.spatial.splits import by_split, geographic_split
from floodlens.ml.spatial.unet import bce_on_samples, fit_unet
from floodlens.ml.uncertainty import fit_conformal

REPORT_PATH = SPATIAL_DIR / "phase55_eval.json"


def _geo_holdout(samples):
    train = [s for s in samples if geographic_split(s.city_id) == "train"]
    test = [s for s in samples if geographic_split(s.city_id) == "test"]
    return train, test


def evaluate_phase55(processed_dir: Optional[Path] = None, epochs: int = 6) -> dict:
    samples, meta = build_spatial_samples(processed_dir=processed_dir)
    inv = inventory(samples) if samples else {"n_independent_events": 0, "verdict": "INSUFFICIENT FOR VALIDATION"}
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model_id": SPATIAL_MODEL_ID,
        "dataset": meta,
        "inventory": inv,
        "target": {
            "definition": "P(cell flooded) from GFM ensemble extent, tau=0.25, unknown=255 never dry",
            "horizon_hours": 192,
            "supported_product_horizons": [192],
            "unavailable_horizons": [6, 12, 24, 48, 72],
            "unavailable_reason": (
                "GFM is Sentinel-1 scene-based (typically 6–12 day revisit). "
                "There is no observed flood map 6/12/24 h after issue_time. Labels are not invented."
            ),
        },
        "features": {
            "channels": [
                "precip_24h_broadcast",
                "precip_72h_broadcast",
                "log1p_q_broadcast",
                "month_sin",
                "month_cos",
                "persistence_map",
                "persistence_valid_flag",
                "precip_is_aoi_point_flag",
            ],
            "spatial_forcing": "AOI-point rain and GloFAS cell Q broadcast to every pixel",
            "dem_present": any(s.dem_present for s in samples),
            "dem_ingestion_plan": DEM_INGESTION_PLAN,
            "constant_channel_fraction": 6 / 8,
            "spatial_information_loss": (
                "Six of eight U-Net channels are spatially constant. Only persistence (and its flag) "
                "vary in space. This is acceptable for a leakage-safe PoC, not a 500 m rainfall field."
            ),
        },
        "status": "TRAINED",
        "public_status": "NOT_TRAINED",
        "validation_verdict": inv.get("verdict"),
        "promoted_to_validated": False,
        "comparable_to_physics": False,
        "accuracy_claim": None,
    }
    if not samples or not by_split(samples, "train"):
        report["status"] = "NOT_TRAINED"
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    train = by_split(samples, "train")
    val = by_split(samples, "val")
    test = by_split(samples, "test")
    report["label_quality"] = scene_quality_table(load_index(processed_dir))
    fitted = fit_spatial_baselines(samples)
    unet = fit_unet(train, epochs=epochs)
    y_bits, p_bits = [], []
    for sample in val or train[: max(1, len(train) // 4)]:
        y = sample.y_binary().reshape(-1)
        p = unet.predict_proba(sample).reshape(-1)
        m = np.isfinite(y)
        y_bits.extend(y[m].tolist())
        p_bits.extend(p[m].tolist())
    conformal = fit_conformal(np.asarray(y_bits), np.asarray(p_bits))

    def unet_width(sample: SpatialForecastSample) -> np.ndarray:
        p = unet.predict_proba(sample)
        return np.full(p.shape, 2.0 * conformal.q80)

    geo_train, geo_test = _geo_holdout(samples)
    report["baselines"] = {
        "val": evaluate_spatial_baselines(samples, fitted, "val") if val else {"n_maps": 0},
        "test": evaluate_spatial_baselines(samples, fitted, "test") if test else {"n_maps": 0},
    }
    report["unet"] = {
        "architecture": "TinyUNet 8ch → 8 → 16 bottleneck, numpy/scipy",
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "loss": {
            "train_curve": (getattr(unet, "history", {}) or {}).get("train_loss"),
            "train": (getattr(unet, "history", {}) or {}).get("train_final"),
            "val": bce_on_samples(unet, val),
            "test": bce_on_samples(unet, test),
        },
        "val": event_metrics(val, unet.predict_proba) if val else {"n_maps": 0},
        "test": event_metrics(test, unet.predict_proba) if test else {"n_maps": 0},
        "test_pixel": None,
    }
    # clean pixel metrics
    tys, tps = [], []
    for sample in test:
        yb = sample.y_binary()
        pb = unet.predict_proba(sample)
        m = np.isfinite(yb)
        tys.append(yb[m])
        tps.append(pb[m])
    if tys:
        report["unet"]["test_pixel"] = map_metrics(np.concatenate(tys), np.concatenate(tps))
    geo_model = fit_unet(geo_train, epochs=epochs) if geo_train else None
    report["generalization"] = {
        "temporal_holdout": "train issue years ≤2018; val 2019–2021; test 2022+ and named NE holdout",
        "same_event_train_test": same_event_in_train_and_test(samples),
        "same_event_train_val": same_event_across_splits(samples, "train", "val"),
        "same_event_val_test": same_event_across_splits(samples, "val", "test"),
        "geographic_holdout_train_cities": sorted({s.city_id for s in geo_train}),
        "geographic_holdout_test_cities": sorted({s.city_id for s in geo_test}),
        "geographic_test_temporal_model": event_metrics(geo_test, unet.predict_proba) if geo_test else {"n_maps": 0},
        "geographic_retrained": (
            event_metrics(geo_test, geo_model.predict_proba) if geo_model and geo_test else {"n_maps": 0}
        ),
        "note": (
            "Geographic retrain fits only Dhaka tiles, then scores Sunamganj/Sylhet. "
            "Test geography is not used in that fit. Temporal-model-on-other-cities is also reported."
        ),
    }
    report["hard_cases"] = {
        flag: subset_metrics(test or val, unet.predict_proba, flag)
        for flag in ("weak_flood", "small_flood", "nodata_heavy", "low_rainfall", "rare_event")
    }
    report["uncertainty"] = {
        "conformal_test": conformal_heldout(test or val, unet.predict_proba, conformal),
        "error_correlation": uncertainty_error_correlation(test or val, unet.predict_proba, unet_width),
    }
    report["decision"] = {
        "option": "A",
        "text": (
            "Limited proof-of-concept only. Independent-event count, broadcast rain, missing DEM, "
            "Bangladesh-only geography, and 8-day (not 6–72 h) labels do not support VALIDATED "
            "spatial forecasting. Expand toward more independent flood episodes before any promotion."
        ),
        "never_promote_from_this_script": True,
    }
    if not inv.get("sufficient_for_validation"):
        report["decision"]["option"] = "A"
        report["decision"]["missing"] = (
            f"Need ≥{MIN_EVENTS_FOR_VALIDATION} independent meteorological episodes; have "
            f"{inv.get('n_independent_events')}."
        )
    # Even if the event floor is met, remaining scientific gaps forbid VALIDATED.
    report["promoted_to_validated"] = False
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    # persist checkpoint + TRAINED only
    from floodlens.ml.spatial.train import train_spatial

    train_spatial(processed_dir=processed_dir, epochs=epochs)
    return report
