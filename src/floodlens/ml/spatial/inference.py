"""Spatial inference: probability / extent / uncertainty maps as artifacts, not JSON arrays."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from floodlens.application.artifact_store import put_depth_artifact
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.ingest import fetch_open_meteo_precipitation
from floodlens.application.provenance import isoformat, utcnow
from floodlens.ml.real_dataset import q_lookback_before_issue
from floodlens.ml.schema import LOOKBACK_HOURS
from floodlens.ml.spatial.schema import (
    GRID_SIZE,
    HORIZON_HOURS,
    SPATIAL_DIR,
    SPATIAL_MODEL_ID,
    SpatialForecastSample,
)
from floodlens.ml.spatial.tiles import city_bounds, grid_spec
from floodlens.ml.spatial.unet import TinyUNet, sample_channels
from floodlens.ml.uncertainty import ConformalCalibrator

SPATIAL_CHECKPOINT = SPATIAL_DIR / "checkpoint.json"


def _unavailable(city_id: str, reason: str) -> dict:
    return {
        "city_id": city_id,
        "available": False,
        "data_status": "UNAVAILABLE",
        "model_kind": "AI_SPATIAL",
        "model_id": None,
        "reason": reason,
        "horizons": [],
        "overlay": None,
        "clock": "meteorological_hours",
        "not_simulation_time": True,
        "comparable_to_physics": False,
        "provenance": envelope(
            data_status="UNAVAILABLE",
            provider="ai-spatial-forecast",
            dataset="gfm-occurrence",
            freshness="UNAVAILABLE",
        ),
        "catalog_status": "NOT_VALIDATED",
        "disclaimer": (
            "No validated spatial flood model is deployed. "
            "6h/12h/24h spatial labels do not exist. Maps are not invented."
        ),
    }


def load_spatial_checkpoint(path: Optional[str] = None) -> dict:
    bundled = SPATIAL_CHECKPOINT
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(bundled)
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"spatial checkpoint missing: {path or bundled}")


def _lookback_sample(city_id: str) -> tuple[Optional[SpatialForecastSample], Optional[str]]:
    from floodlens.application.repository import get_repository

    rows = [
        r
        for r in get_repository().list_rainfall(city_id)
        if getattr(r, "kind", None) in {"OBSERVED", "SIMULATED"}
    ]
    rows = sorted(rows, key=lambda r: r.valid_at)
    if len(rows) < int(LOOKBACK_HOURS * 0.8):
        return None, "Precip lookback completeness < 80%."
    tail = rows[-LOOKBACK_HOURS:]
    values = [float(r.value_mm) for r in tail]
    if len(values) < LOOKBACK_HOURS:
        values = [0.0] * (LOOKBACK_HOURS - len(values)) + values
    kinds = []
    for r in tail:
        kinds.append("OBSERVED" if r.kind == "OBSERVED" else "SIMULATED")
    if len(kinds) < LOOKBACK_HOURS:
        kinds = ["UNAVAILABLE"] * (LOOKBACK_HOURS - len(kinds)) + kinds
    issue = utcnow()
    q_pack = q_lookback_before_issue(city_id, issue, allow_live=True)
    if q_pack is None:
        return None, "GloFAS Q lookback unavailable."
    spec = grid_spec(city_id)
    dummy = np.full((GRID_SIZE, GRID_SIZE), 255, dtype=np.uint8)
    sample = SpatialForecastSample(
        city_id=city_id,
        issue_time=isoformat(issue),
        valid_at=isoformat(issue + timedelta(hours=HORIZON_HOURS)),
        horizon_hours=HORIZON_HOURS,
        y_flood=dummy,
        y_flood_frac=np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32),
        x_precip_hourly=values[-LOOKBACK_HOURS:],
        x_precip_hourly_kind=kinds[-LOOKBACK_HOURS:],
        x_antecedent_24h=float(sum(values[-LOOKBACK_HOURS:])),
        x_antecedent_72h=None,
        x_glofas_q_lookback=[None if v is None else float(v) for v in q_pack["values"]],
        x_persistence=None,
        x_dem=None,
        precip_is_aoi_point=True,
        q_is_glofas_cell=True,
        dem_present=False,
        label_kind="OBSERVED",
        label_source="live-inference",
        lookback_complete_frac=len(tail) / float(LOOKBACK_HOURS),
        bounds=list(city_bounds(city_id)),
        extra={"precip_windows": {24: float(sum(values[-LOOKBACK_HOURS:]))}, "grid": spec},
    )
    return sample, None


def probability_maps(prob: np.ndarray, conformal: ConformalCalibrator) -> dict:
    p = np.clip(np.asarray(prob, dtype=np.float64), 0.0, 1.0)
    low = np.clip(p - conformal.q80, 0.0, 1.0)
    high = np.clip(p + conformal.q80, 0.0, 1.0)
    extent = (p >= 0.5).astype(np.float64)
    return {"probability": p, "q10": low, "q90": high, "extent": extent}


class SpatialForecastProvider:
    def forecast(self, city_id: str, allow_unvalidated: bool = False) -> dict:
        from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status

        city = create_city_registry().get_city(city_id)
        if city is None:
            return _unavailable(city_id, "unknown city")
        record = load_spatial_registry()
        catalog = public_spatial_status(record)
        ckpt_path = record.get("checkpoint")
        can_run = record.get("status") in {"TRAINED", "VALIDATED", "DEPLOYED"} and ckpt_path
        if catalog != "VALIDATED" and not allow_unvalidated:
            return _unavailable(
                city_id,
                record.get("note") or "Spatial AI is NOT_TRAINED until held-out maps are validated.",
            )
        if not can_run:
            return _unavailable(city_id, "No spatial checkpoint is registered.")
        fetch_open_meteo_precipitation(city_id)
        try:
            ckpt = load_spatial_checkpoint(ckpt_path)
        except FileNotFoundError:
            return _unavailable(city_id, "Spatial checkpoint file missing.")
        packed, err = _lookback_sample(city_id)
        if packed is None:
            return _unavailable(city_id, err or "lookback unavailable")
        sample = packed
        if not ckpt.get("unet"):
            return _unavailable(
                city_id,
                "No spatial CNN in checkpoint. Phase 6 Gate 2 is not passed; maps are not served.",
            )
        unet = TinyUNet.from_dict(ckpt["unet"])
        conformal = ConformalCalibrator.from_dict(ckpt["conformal"])
        prob = unet.predict_proba(sample)
        maps = probability_maps(prob, conformal)
        artifact_id = f"spatial-{city_id}-{sample.issue_time[:13]}"
        west, south, east, north = sample.bounds
        meta = {
            "kind": "probability_map",
            "variable": "flood_probability",
            "label_kind": ckpt.get("label_kind"),
            "model_id": SPATIAL_MODEL_ID,
            "horizon_hours": HORIZON_HOURS,
            "bounds": {"west": west, "south": south, "east": east, "north": north},
            "crs": "EPSG:4326",
            "max_depth_m": None,
            "mean_probability": float(np.mean(prob)),
            "validation_status": record.get("status"),
        }
        put_depth_artifact(artifact_id, maps["probability"], meta)
        put_depth_artifact(artifact_id + "-extent", maps["extent"], {**meta, "kind": "extent_map"})
        put_depth_artifact(artifact_id + "-q90", maps["q90"], {**meta, "kind": "uncertainty_map"})
        points = []
        for hours in (6, 12, 24, 48, 72, HORIZON_HOURS):
            if hours != HORIZON_HOURS:
                points.append(
                    {
                        "horizon_hours": hours,
                        "available": False,
                        "data_status": "UNAVAILABLE",
                        "expected_depth": None,
                        "artifact_id": None,
                        "reason": "GFM labels are scene/8-day slots, not 6–72 h maps.",
                    }
                )
                continue
            points.append(
                {
                    "horizon_hours": HORIZON_HOURS,
                    "available": True,
                    "data_status": "PARTIAL" if catalog == "VALIDATED" else "DEMO",
                    "flood_probability_mean": float(np.mean(prob)),
                    "expected_depth": None,
                    "artifact_id": artifact_id,
                    "extent_artifact_id": artifact_id + "-extent",
                    "uncertainty_artifact_id": artifact_id + "-q90",
                    "valid_at": sample.valid_at,
                    "confidence_kind": "conformal",
                    "interval": conformal.interval(float(np.mean(prob)))["interval"],
                }
            )
        return {
            "city_id": city_id,
            "available": True,
            "data_status": "PARTIAL" if catalog == "VALIDATED" else "DEMO",
            "model_kind": "AI_SPATIAL",
            "model_id": SPATIAL_MODEL_ID,
            "run_id": record.get("run_id"),
            "dataset_version": record.get("dataset_version"),
            "clock": "meteorological_hours",
            "not_simulation_time": True,
            "comparable_to_physics": False,
            "horizons": points,
            "overlay": None,
            "artifact_id": artifact_id,
            "registry_status": record.get("status"),
            "catalog_status": catalog,
            "label_kind": ckpt.get("label_kind"),
            "channels": int(sample_channels(sample).shape[0]),
            "provenance": envelope(
                data_status="PARTIAL" if catalog == "VALIDATED" else "DEMO",
                provider="ai-spatial-forecast",
                dataset="gfm-occurrence",
                freshness="SNAPSHOT",
                extra={"model_id": SPATIAL_MODEL_ID, "horizon_hours": HORIZON_HOURS},
            ),
            "disclaimer": (
                "Spatial P(cell flooded) on a coarse AOI grid from GFM OBSERVED 8-day scenes. "
                "6h/12h/24h remain UNAVAILABLE. Not a depth forecast. "
                "COMPARISON NOT YET COMPARABLE to the sub-second SWE burst."
            ),
        }


def run_spatial_forecast_job(city_id: str) -> dict:
    return SpatialForecastProvider().forecast(city_id, allow_unvalidated=False)
