"""AI forecast provider and job runner. No fake depth rasters."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Optional

from floodlens.application.canonical import ForecastPoint
from floodlens.application.city_data import create_city_registry
from floodlens.application.data_contracts import envelope
from floodlens.application.forecast import HORIZONS_H
from floodlens.application.ingest import fetch_open_meteo_precipitation
from floodlens.application.provenance import isoformat, utcnow
from floodlens.application.repository import get_repository
from floodlens.application.risk import categorize
from floodlens.ml.baselines import BoostingModel
from floodlens.ml.features import TrainScaler, vectorize
from floodlens.ml.real_dataset import q_lookback_before_issue
from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample
from floodlens.ml.uncertainty import ConformalCalibrator

AI_MODEL_ID = "FLOOD-OCCURRENCE-GBDT-v0.1"


def _unavailable(city_id: str, reason: str) -> dict:
    return {
        "city_id": city_id,
        "available": False,
        "data_status": "UNAVAILABLE",
        "model_kind": "AI",
        "model_id": None,
        "reason": reason,
        "horizons": [],
        "expected_depth": None,
        "overlay": None,
        "clock": "meteorological_hours",
        "not_simulation_time": True,
        "provenance": envelope(
            data_status="UNAVAILABLE",
            provider="ai-forecast",
            dataset="flood-nowcast",
            freshness="UNAVAILABLE",
        ),
        "disclaimer": (
            "No validated AI flood model is deployed. "
            "This endpoint does not invent flood depth or extent."
        ),
    }


def _lookback_from_store(city_id: str, q_thresholds: Optional[dict] = None):
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
        return None, (
            "GloFAS Q lookback (t-7d..t-1d) unavailable. Live flood API failed and "
            "the committed snapshot ends 2024-12-31; missing Q is not treated as dry."
        )
    q_hist = [None if v is None else float(v) for v in q_pack["values"]]
    precip = values[-LOOKBACK_HOURS:]
    windows = {
        1: float(sum(precip[-1:])),
        3: float(sum(precip[-3:])),
        6: float(sum(precip[-6:])),
        12: float(sum(precip[-12:])),
        24: float(sum(precip)),
    }
    thr = None
    if q_thresholds and city_id in q_thresholds:
        thr = float(q_thresholds[city_id])
    y_now = int(q_hist[-1] >= thr) if thr is not None and q_hist[-1] is not None else 0
    sample = ForecastSample(
        city_id=city_id,
        issue_time=isoformat(issue),
        horizon_hours=24,
        valid_at=isoformat(issue + timedelta(hours=24)),
        x_precip_hourly=precip,
        x_precip_hourly_kind=kinds[-LOOKBACK_HOURS:],
        x_precip_forecast_to_h=None,
        x_precip_forecast_issued_at=None,
        x_antecedent_24h=windows[24],
        x_antecedent_72h=None,
        x_dem_stats=None,
        x_glofas_q_lookback=q_hist,
        y_track_a=None,
        y_track_b=None,
        y_track_b_available=False,
        lookback_complete_frac=len(tail) / float(LOOKBACK_HOURS),
        label_source="live-inference",
        label_kind="MODELLED",
        issue_precip_forecast_id=None,
        extra={
            "y_at_issue": y_now,
            "precip_windows": windows,
            "q_source": q_pack["source"],
            "q_lookback_end_day": q_pack["end_day"],
        },
    )
    return sample, issue


def load_checkpoint(path: str) -> dict:
    candidates = [Path(path)]
    bundled = Path(__file__).resolve().parent / "data" / "ml" / "real" / "checkpoint.json"
    candidates.append(bundled)
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"AI checkpoint missing: {path}")


def _predict_horizons(sample: ForecastSample, ckpt: dict, issue) -> list:
    scaler = TrainScaler.from_dict(ckpt["scaler"])
    boosting = BoostingModel.from_dict(ckpt["boosting"])
    conformal = ConformalCalibrator.from_dict(ckpt["conformal"])
    supported = set(int(h) for h in (ckpt.get("supported_horizons") or ckpt.get("horizons") or [24, 48, 72]))
    data_status = "PARTIAL"
    points = []
    for hours in HORIZONS_H:
        sample.horizon_hours = int(hours)
        sample.valid_at = isoformat(issue + timedelta(hours=hours))
        if int(hours) not in supported:
            points.append(
                {
                    "horizon_hours": int(hours),
                    "available": False,
                    "data_status": "UNAVAILABLE",
                    "expected_depth": None,
                    "artifact_id": None,
                    "reason": "Daily GloFAS labels do not support sub-daily 6h/12h targets.",
                    "valid_at": sample.valid_at,
                }
            )
            continue
        x = scaler.transform(vectorize(sample).reshape(1, -1))
        prob = float(boosting.predict_proba(x)[0])
        interval = conformal.interval(prob)
        severity = min(1.0, 0.35 + 0.5 * prob)
        score = prob * 0.5 * severity
        point = ForecastPoint(
            horizon_hours=int(hours),
            timestamp=sample.valid_at,
            valid_at=sample.valid_at,
            generated_at=isoformat(issue),
            probability=round(prob, 4),
            severity=round(severity, 4),
            expected_depth=None,
            confidence=round(interval["interval"][1] - interval["interval"][0], 4),
            confidence_kind="conformal",
            risk_category=categorize(score),
            model_id=AI_MODEL_ID,
            data_status=data_status,
        )
        row = point.to_dict()
        row["flood_probability"] = row["probability"]
        row["interval"] = interval["interval"]
        row["q10"] = interval["q10"]
        row["q90"] = interval["q90"]
        row["artifact_id"] = None
        row["available"] = True
        points.append(row)
    return points


class AIModelForecastProvider:
    def forecast(self, city_id: str, allow_unvalidated: bool = False) -> dict:
        city = create_city_registry().get_city(city_id)
        if city is None:
            return _unavailable(city_id, "unknown city")
        record = load_registry()
        catalog_status = public_status(record)
        ckpt_path = record.get("checkpoint")
        can_run = record.get("status") in {"TRAINED", "VALIDATED", "DEPLOYED"} and ckpt_path
        if catalog_status != "VALIDATED" and not allow_unvalidated:
            return _unavailable(
                city_id,
                record.get("note") or "No trained AI flood model is deployed.",
            )
        if not can_run:
            return _unavailable(city_id, "No AI checkpoint is registered.")
        fetch_open_meteo_precipitation(city_id)
        ckpt = load_checkpoint(ckpt_path)
        packed = _lookback_from_store(city_id, ckpt.get("q_thresholds_m3s"))
        if packed[0] is None:
            return _unavailable(city_id, packed[1])
        sample, issue = packed
        if sample.lookback_complete_frac < 0.80:
            return _unavailable(city_id, "Precip lookback completeness < 80%.")
        points = _predict_horizons(sample, ckpt, issue)
        data_status = "PARTIAL" if record.get("status") == "VALIDATED" else "DEMO"
        return {
            "city_id": city_id,
            "available": True,
            "data_status": data_status,
            "model_kind": "AI",
            "model_id": AI_MODEL_ID,
            "run_id": record.get("run_id"),
            "dataset_version": record.get("dataset_version") or ckpt.get("dataset_version"),
            "clock": "meteorological_hours",
            "not_simulation_time": True,
            "horizons": points,
            "overlay": None,
            "registry_status": record.get("status"),
            "catalog_status": catalog_status,
            "provenance": envelope(
                data_status=data_status,
                provider="ai-forecast",
                dataset="flood-nowcast",
                freshness="SNAPSHOT",
                simulated=data_status == "DEMO",
                extra={"model_kind": "AI", "model_id": AI_MODEL_ID, "confidence_kind": "conformal"},
            ),
            "disclaimer": (
                "AI flood-occurrence probabilities for 24/48/72h from a GBDT trained on "
                "Open-Meteo GloFAS reanalysis exceedance (MODELLED hydrology, not gauges). "
                "6h/12h are UNAVAILABLE. expected_depth is null. No flood-extent overlay. "
                if record.get("status") == "VALIDATED"
                else "Research checkpoint only (not VALIDATED). Not an operational forecast. "
            )
            + "confidence_kind=conformal. Not a heuristic score. "
            "Not a 24h shallow-water forecast.",
        }


def run_ai_forecast_job(city_id: str) -> dict:
    return AIModelForecastProvider().forecast(city_id, allow_unvalidated=False)
