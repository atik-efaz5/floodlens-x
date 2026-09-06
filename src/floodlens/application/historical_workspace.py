"""Historical flood replay and model-audit workspace.

Observation + audit only. Does not invent retrospective forecasts, flood maps,
timestamps, depth, or accuracy claims.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Sequence

import numpy as np

from floodlens.application.data_contracts import envelope
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import (
    FORECAST_MODEL_VERSION,
    PHYSICS_MODEL_VERSION,
)
from floodlens.ml.evaluate import brier, confusion_at_threshold
from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import UNKNOWN

DATA_ROOT = Path(__file__).resolve().parent / "data" / "ml"
GFM_EVENTS_PATH = DATA_ROOT / "spatial" / "event_inventory" / "gfm_events_v21.json"
PAIRS_PATH = DATA_ROOT / "spatial" / "phase68a" / "transition_pairs.json"
INDEX_PATH = DATA_ROOT / "spatial" / "gfm" / "processed" / "index.json"

SEMANTIC_OBSERVATION = "OBSERVATION"
SEMANTIC_FORECAST = "FORECAST"
SEMANTIC_SCENARIO = "SCENARIO"
SEMANTIC_SIMULATION = "SIMULATION"
SEMANTIC_MODELLED_AOI = "MODELLED_AOI_PROBABILITY"
SEMANTIC_EXPERIMENT = "EXPERIMENT"

TARGET_BINARY_EXTENT = "BINARY_FLOOD_EXTENT"
TARGET_NEWLY_FLOODED = "NEWLY_FLOODED"
TARGET_AOI_Q = "AOI_Q_EXCEEDANCE_MODELLED"
TARGET_HEURISTIC_AOI = "AOI_PROBABILITY_HEURISTIC"
TARGET_PHYSICS_DEPTH = "PHYSICS_WATER_DEPTH_M"

CLASS_TN = 0
CLASS_TP = 1
CLASS_FP = 2  # predicted flood, observed dry (false alarm)
CLASS_FN = 3  # observed flood, predicted dry (missed flood)
CLASS_UNKNOWN = int(UNKNOWN)

SPATIAL_AI_STATUS = "NOT_VALIDATED"
SPATIAL_API_STATUS = "UNAVAILABLE"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _gfm_payload() -> dict:
    return _read_json(GFM_EVENTS_PATH) or {"events": [], "dataset_version": None}


@lru_cache(maxsize=1)
def _pairs() -> List[dict]:
    payload = _read_json(PAIRS_PATH)
    return payload if isinstance(payload, list) else []


@lru_cache(maxsize=1)
def _processed_index() -> dict:
    return _read_json(INDEX_PATH) or {"scenes": [], "dataset_version": None}


def _year_of(stamp: Optional[str]) -> Optional[int]:
    if not stamp:
        return None
    try:
        return int(str(stamp)[:4])
    except (TypeError, ValueError):
        return None


def _in_window(stamp: Optional[str], start: Optional[str], end: Optional[str]) -> bool:
    if not stamp:
        return False
    day = str(stamp)[:10]
    if start and day < str(start)[:10]:
        return False
    if end and day > str(end)[:10]:
        return False
    return True


def semantic_type_of_job(job: dict) -> str:
    """Map a platform job to an artifact semantic type. Scenario is never FORECAST."""
    kind = str(job.get("kind") or "").lower()
    if kind == "scenario":
        return SEMANTIC_SCENARIO
    if kind in {"simulation", "physics", "physics_forecast"}:
        return SEMANTIC_SIMULATION
    if kind == "ai_spatial_forecast":
        return SEMANTIC_EXPERIMENT
    if kind == "ai_forecast":
        return SEMANTIC_MODELLED_AOI
    if kind in {"forecast", "heuristic_forecast"}:
        return SEMANTIC_FORECAST
    label = str(job.get("label_kind") or job.get("semantic_type") or "").upper()
    if label == SEMANTIC_OBSERVATION:
        return SEMANTIC_OBSERVATION
    if label in {SEMANTIC_FORECAST, SEMANTIC_SCENARIO, SEMANTIC_SIMULATION}:
        return label
    return "UNKNOWN"


def _catalog_envelope_status(status: Optional[str]) -> str:
    if status in {"REAL", "SIMULATED", "DEMO", "STALE", "UNAVAILABLE", "PARTIAL"}:
        return status
    if status in {"OBSERVED", "OBSERVED_METADATA"}:
        return "PARTIAL"
    return "UNAVAILABLE"


def _job_matches_event(job: dict, regions: Sequence[str]) -> bool:
    city = job.get("city_id")
    if not city or not regions:
        return False
    if city in regions:
        return True
    return any(str(region).startswith(str(city)) or str(city).startswith(str(region)) for region in regions)


def _pairs_for_event(event_id: str) -> List[dict]:
    return [row for row in _pairs() if row.get("event_id") == event_id]


def _scenes_for_event(start: Optional[str], end: Optional[str]) -> List[dict]:
    scenes = []
    for scene in _processed_index().get("scenes") or []:
        stamp = scene.get("datetime") or scene.get("observed_at")
        if _in_window(stamp, start, end):
            scenes.append(scene)
    scenes.sort(key=lambda row: str(row.get("datetime") or ""))
    return scenes


def _observation_count(event: dict) -> int:
    stamps = set()
    for pair in _pairs_for_event(event["event_id"]):
        if pair.get("t0"):
            stamps.add(str(pair["t0"]))
        if pair.get("t1"):
            stamps.add(str(pair["t1"]))
    for scene in _scenes_for_event(event.get("event_start"), event.get("event_end")):
        if scene.get("datetime"):
            stamps.add(str(scene["datetime"]))
    return len(stamps)


def _gfm_catalog_row(raw: dict) -> dict:
    event_id = raw["event_id"]
    n_obs = _observation_count(raw)
    raster_on_disk = any(
        Path(scene.get("href") or "").exists()
        for scene in _scenes_for_event(raw.get("event_start"), raw.get("event_end"))
    )
    if n_obs == 0:
        data_status = "UNAVAILABLE"
    elif raster_on_disk:
        data_status = "OBSERVED"
    else:
        data_status = "OBSERVED_METADATA"
    return {
        "event_id": event_id,
        "name": None,
        "label": event_id,
        "start": raw.get("event_start"),
        "peak": raw.get("event_peak"),
        "end": raw.get("event_end"),
        "regions": list(raw.get("region_ids") or []),
        "basin_ids": list(raw.get("basin_ids") or []),
        "flood_mechanism": raw.get("flood_mechanism"),
        "observation_source": raw.get("source"),
        "n_observations": n_obs,
        "data_status": data_status,
        "quality_status": raw.get("quality_status"),
        "label_kind": raw.get("label_kind") or "OBSERVED",
        "spatial_resolution_m": raw.get("spatial_resolution_m"),
        "dataset_version": _gfm_payload().get("dataset_version"),
        "catalog_family": "GFM",
        "pixels_flood": raw.get("pixels_flood"),
        "pixels_dry": raw.get("pixels_dry"),
        "pixels_unknown": raw.get("pixels_unknown"),
        "unknown_fraction": raw.get("unknown_fraction"),
        "cube_eligible": raw.get("cube_eligible"),
        "gfm_available": raw.get("gfm_available"),
        "observed_flood_extent": None,
        "semantic_type": SEMANTIC_OBSERVATION,
    }


def _emsr_catalog_rows() -> List[dict]:
    from floodlens.ml.dataset_builder import historical_events_from_catalog

    rows = []
    for raw in historical_events_from_catalog():
        rows.append(
            {
                "event_id": raw["event_id"],
                "name": raw.get("name"),
                "label": raw.get("name") or raw["event_id"],
                "start": raw.get("start_time"),
                "peak": None,
                "end": raw.get("end_time"),
                "regions": [part.strip() for part in str(raw.get("region") or "").split(",") if part.strip()],
                "basin_ids": [],
                "flood_mechanism": None,
                "observation_source": raw.get("source"),
                "n_observations": 0,
                "data_status": "UNAVAILABLE",
                "quality_status": "catalog_only",
                "label_kind": "OBSERVED",
                "spatial_resolution_m": None,
                "dataset_version": None,
                "catalog_family": "EMSR",
                "pixels_flood": None,
                "pixels_dry": None,
                "pixels_unknown": None,
                "unknown_fraction": None,
                "cube_eligible": False,
                "gfm_available": False,
                "observed_flood_extent": None,
                "semantic_type": SEMANTIC_OBSERVATION,
                "note": "Metadata catalog only. Polygons were not downloaded.",
            }
        )
    return rows


def event_catalog(
    year: Optional[int] = None,
    region: Optional[str] = None,
    flood_mechanism: Optional[str] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    events = [_gfm_catalog_row(raw) for raw in _gfm_payload().get("events") or []]
    events.extend(_emsr_catalog_rows())
    from floodlens.application.demo_fixtures import demo_event_row, demo_fixtures_enabled

    if demo_fixtures_enabled():
        events.insert(0, demo_event_row())
    if year is not None:
        events = [row for row in events if _year_of(row.get("start")) == int(year)]
    if region:
        needle = region.lower()
        events = [
            row
            for row in events
            if needle in [str(item).lower() for item in row.get("regions") or []]
        ]
    if flood_mechanism:
        needle = flood_mechanism.lower()
        events = [
            row
            for row in events
            if str(row.get("flood_mechanism") or "").lower() == needle
        ]
    if source:
        needle = source.lower()
        events = [
            row
            for row in events
            if needle in str(row.get("observation_source") or "").lower()
            or needle in str(row.get("catalog_family") or "").lower()
        ]
    if status:
        needle = status.lower()
        events = [
            row
            for row in events
            if needle in str(row.get("data_status") or "").lower()
            or needle in str(row.get("quality_status") or "").lower()
        ]
    if model:
        needle = model.lower()
        kept = []
        for row in events:
            preds = discover_predictions(row["event_id"]).get("predictions") or []
            if any(needle in str(item.get("model") or item.get("model_id") or "").lower() for item in preds):
                kept.append(row)
        events = kept
    return {
        "data": events,
        "n": len(events),
        "filters": {
            "year": year,
            "region": region,
            "flood_mechanism": flood_mechanism,
            "source": source,
            "model": model,
            "status": status,
        },
        "note": (
            "GFM rows use catalog event_id as the label; human-readable names are not invented. "
            "EMSR rows keep published activation names. observed_flood_extent is null unless a raster exists on disk."
        ),
        "provenance": envelope(
            data_status="PARTIAL",
            provider="copernicus-gfm-and-cems-catalog",
            dataset="historical-events",
            freshness="UNAVAILABLE",
        ),
    }


def _find_event(event_id: str) -> Optional[dict]:
    from floodlens.application.demo_fixtures import DEMO_EVENT_ID, demo_event_row, demo_fixtures_enabled

    if demo_fixtures_enabled() and event_id == DEMO_EVENT_ID:
        return demo_event_row()
    for raw in _gfm_payload().get("events") or []:
        if raw.get("event_id") == event_id:
            return _gfm_catalog_row(raw)
    for row in _emsr_catalog_rows():
        if row["event_id"] == event_id:
            return row
    return None


def _scene_city_stats(scene: dict) -> dict:
    cities = scene.get("cities") or {}
    n_flood = n_dry = n_unknown = 0
    resolution_notes = []
    overlay_available = False
    href = scene.get("href")
    if href and Path(href).exists():
        overlay_available = True
    for city_id, stats in cities.items():
        n_flood += int(stats.get("n_flood") or 0)
        n_dry += int(stats.get("n_dry") or 0)
        n_unknown += int(stats.get("n_unknown") or 0)
        grid = stats.get("grid") or {}
        if grid.get("note"):
            resolution_notes.append(str(grid["note"]))
    valid = n_flood + n_dry
    total = valid + n_unknown
    return {
        "n_flood": n_flood,
        "n_dry": n_dry,
        "n_unknown": n_unknown,
        "valid_coverage": (valid / total) if total else None,
        "unknown_coverage": (n_unknown / total) if total else None,
        "overlay_available": overlay_available,
        "resolution_note": resolution_notes[0] if resolution_notes else None,
        "city_ids": sorted(cities),
    }


def event_observations(event_id: str) -> dict:
    event = _find_event(event_id)
    if event is None:
        raise KeyError(event_id)
    from floodlens.application.demo_fixtures import DEMO_EVENT_ID, demo_event_observation, demo_fixtures_enabled

    if demo_fixtures_enabled() and event_id == DEMO_EVENT_ID:
        obs = demo_event_observation()
        return {
            "event_id": event_id,
            "observations": [obs],
            "n": 1,
            "note": obs.get("resolution_note"),
            "provenance": envelope(
                data_status="DEMO",
                provider="demo-historical-fixture",
                dataset="historical-observations",
                freshness="SNAPSHOT",
                simulated=True,
            ),
        }
    observations: List[dict] = []
    seen = set()
    for scene in _scenes_for_event(event.get("start"), event.get("end")):
        stamp = scene.get("datetime")
        scene_id = scene.get("id") or stamp
        if scene_id in seen:
            continue
        seen.add(scene_id)
        stats = _scene_city_stats(scene)
        observations.append(
            {
                "observation_id": scene_id,
                "timestamp": stamp,
                "source": _processed_index().get("source") or event.get("observation_source"),
                "resolution_m": event.get("spatial_resolution_m"),
                "dataset_version": _processed_index().get("dataset_version") or event.get("dataset_version"),
                "label_kind": "OBSERVED",
                "semantic_type": SEMANTIC_OBSERVATION,
                "target_definition": TARGET_BINARY_EXTENT,
                "valid_coverage": stats["valid_coverage"],
                "unknown_coverage": stats["unknown_coverage"],
                "flood_extent": {
                    "n_flood": stats["n_flood"],
                    "n_dry": stats["n_dry"],
                    "n_unknown": stats["n_unknown"],
                    "units": "pixels",
                    "unknown_code": CLASS_UNKNOWN,
                },
                "overlay_available": stats["overlay_available"],
                "resolution_note": stats["resolution_note"],
                "city_ids": stats["city_ids"],
            }
        )
    for pair in _pairs_for_event(event_id):
        for key, stamp, scene_id in (
            ("t0", pair.get("t0"), pair.get("earlier_scene_id")),
            ("t1", pair.get("t1"), pair.get("later_scene_id")),
        ):
            token = scene_id or stamp
            if not token or token in seen:
                continue
            seen.add(token)
            observations.append(
                {
                    "observation_id": token,
                    "timestamp": stamp,
                    "source": event.get("observation_source"),
                    "resolution_m": event.get("spatial_resolution_m"),
                    "dataset_version": event.get("dataset_version"),
                    "label_kind": "OBSERVED",
                    "semantic_type": SEMANTIC_OBSERVATION,
                    "target_definition": TARGET_BINARY_EXTENT,
                    "valid_coverage": None,
                    "unknown_coverage": None,
                    "flood_extent": {
                        "n_flood": pair.get("flood_area_t0") if key == "t0" else pair.get("flood_area_t1"),
                        "n_dry": None,
                        "n_unknown": pair.get("unknown_pixels_t0") if key == "t0" else pair.get("unknown_pixels_t1"),
                        "units": "pixels",
                        "unknown_code": CLASS_UNKNOWN,
                        "scope": f"pair {pair.get('region')} working tensor",
                    },
                    "overlay_available": False,
                    "pair_id": pair.get("pair_id"),
                    "region": pair.get("region") or pair.get("city_id"),
                }
            )
    observations.sort(key=lambda row: str(row.get("timestamp") or ""))
    return {
        "event_id": event_id,
        "observations": observations,
        "n": len(observations),
        "note": (
            "Timeline timestamps are actual GFM scene times or Target-B pair times. "
            "T-72h / T-48h / T-24h slots are not invented. "
            "Raster overlay stays UNAVAILABLE when the GeoTIFF is not on disk. "
            "Unknown pixels remain unknown."
        ),
        "provenance": envelope(
            data_status=_catalog_envelope_status(event.get("data_status")),
            provider=event.get("observation_source") or "historical-catalog",
            dataset="gfm-observations",
            freshness="UNAVAILABLE",
        ),
    }


def observation_transition_metrics(event_id: str) -> dict:
    pairs = _pairs_for_event(event_id)
    if not pairs:
        return {
            "event_id": event_id,
            "available": False,
            "reason": "No Target-B transition pairs for this event. Metrics are not invented.",
            "metrics": None,
        }
    n_new = sum(int(row.get("n_newly_flooded") or 0) for row in pairs)
    n_rec = sum(int(row.get("n_receding") or 0) for row in pairs)
    n_persist = sum(int(row.get("n_persistent_flood") or 0) for row in pairs)
    n_joint = sum(int(row.get("n_jointly_valid") or 0) for row in pairs)
    n_unknown = sum(int(row.get("n_unknown_transition") or 0) for row in pairs)
    n_pixels = sum(int(row.get("n_pixels") or 0) for row in pairs)
    area_t0 = sum(int(row.get("flood_area_t0") or 0) for row in pairs)
    area_t1 = sum(int(row.get("flood_area_t1") or 0) for row in pairs)
    return {
        "event_id": event_id,
        "available": True,
        "kind": "DESCRIPTIVE_OBSERVATION",
        "not": ["FORECAST_SKILL", "PREDICTION_ACCURACY"],
        "n_pairs": len(pairs),
        "metrics": {
            "flood_area_t0_pixels": area_t0,
            "flood_area_t1_pixels": area_t1,
            "flood_fraction_t0": (area_t0 / n_joint) if n_joint else None,
            "flood_fraction_t1": (area_t1 / n_joint) if n_joint else None,
            "newly_flooded_area_pixels": n_new,
            "receding_area_pixels": n_rec,
            "persistent_flooded_area_pixels": n_persist,
            "valid_coverage": (n_joint / n_pixels) if n_pixels else None,
            "unknown_coverage": (n_unknown / n_pixels) if n_pixels else None,
        },
        "note": (
            "Aggregated over observed consecutive GFM pairs on jointly valid pixels. "
            "Δt is the measured scene gap, not a 24/48/72h horizon."
        ),
        "pairs": [
            {
                "pair_id": row.get("pair_id"),
                "region": row.get("region") or row.get("city_id"),
                "t0": row.get("t0"),
                "t1": row.get("t1"),
                "delta_t_hours": row.get("delta_t_hours"),
                "delta_t_days": row.get("delta_t_days"),
                "horizon_relabeled": bool(row.get("horizon_relabeled")),
                "n_newly_flooded": row.get("n_newly_flooded"),
                "n_receding": row.get("n_receding"),
                "n_persistent_flood": row.get("n_persistent_flood"),
                "n_jointly_valid": row.get("n_jointly_valid"),
                "unknown_fraction": row.get("unknown_fraction"),
                "split": row.get("split"),
            }
            for row in pairs
        ],
    }


def discover_predictions(event_id: str) -> dict:
    event = _find_event(event_id)
    if event is None:
        raise KeyError(event_id)
    regions = list(event.get("regions") or [])
    predictions: List[dict] = []
    from floodlens.application.demo_fixtures import DEMO_EVENT_ID, demo_fixtures_enabled, demo_forecast_prediction

    if demo_fixtures_enabled() and event_id == DEMO_EVENT_ID:
        predictions.append(demo_forecast_prediction())
    store = get_platform_store()
    for job in store.jobs.values():
        if not _job_matches_event(job, regions):
            continue
        city = job.get("city_id")
        semantic = semantic_type_of_job(job)
        result = job.get("result") or {}
        predictions.append(
            {
                "prediction_id": job.get("id"),
                "artifact_id": result.get("artifact_id") or job.get("result_reference"),
                "model": job.get("model_version") or job.get("kind"),
                "model_version": job.get("model_version"),
                "dataset": None,
                "issue_time": job.get("created_at") or job.get("queued_at"),
                "forecast_horizon": None,
                "target_definition": TARGET_PHYSICS_DEPTH if semantic in {SEMANTIC_SCENARIO, SEMANTIC_SIMULATION} else "UNKNOWN",
                "spatial_resolution": None,
                "artifact": result.get("artifact_id") or job.get("result_reference"),
                "status": job.get("status"),
                "semantic_type": semantic,
                "kind": job.get("kind"),
                "city_id": city,
                "note": (
                    "Platform job associated with a city in this event's regions. "
                    "A scenario or simulation is not an issued historical forecast."
                ),
            }
        )
    spatial = load_spatial_registry()
    predictions.append(
        {
            "prediction_id": "ai-spatial-forecast",
            "artifact_id": None,
            "model": spatial.get("title"),
            "model_version": spatial.get("model_id"),
            "dataset": spatial.get("dataset_version"),
            "issue_time": None,
            "forecast_horizon": spatial.get("horizon_hours"),
            "target_definition": "SPATIAL_FLOOD_OCCURRENCE",
            "spatial_resolution": None,
            "artifact": None,
            "status": SPATIAL_AI_STATUS,
            "semantic_type": SEMANTIC_EXPERIMENT,
            "kind": "AI_SPATIAL",
            "note": (
                "Spatial AI is NOT_VALIDATED. No operational spatial flood-map forecast artifact is published. "
                "TRAINED checkpoint status is not a historical issued forecast."
            ),
        }
    )
    ai = load_registry()
    predictions.append(
        {
            "prediction_id": "ai-forecast",
            "artifact_id": None,
            "model": ai.get("title") or "AOI GBDT",
            "model_version": ai.get("model_id"),
            "dataset": ai.get("dataset_version"),
            "issue_time": None,
            "forecast_horizon": "24/48/72h (AOI scalar)",
            "target_definition": TARGET_AOI_Q,
            "spatial_resolution": "AOI scalar, not a flood map",
            "artifact": None,
            "status": public_status(ai),
            "semantic_type": SEMANTIC_MODELLED_AOI,
            "kind": "AI",
            "task": "AOI flood-occurrence probability (MODELLED GloFAS Q exceedance)",
            "note": (
                "Validated AOI GBDT is not a spatial flood map. "
                "It is not comparable to GFM binary extent."
            ),
        }
    )
    return {
        "event_id": event_id,
        "predictions": predictions,
        "n_forecast_maps": sum(1 for row in predictions if row["semantic_type"] == SEMANTIC_FORECAST and row.get("artifact_id")),
        "note": (
            "Candidates are listed with semantic type. "
            "A raster is not a forecast. Scenario and simulation jobs are not historical forecasts."
        ),
        "provenance": envelope(
            data_status="PARTIAL",
            provider="artifact-registry",
            dataset="prediction-discovery",
            freshness="UNAVAILABLE",
        ),
    }


def check_compatibility(predicted: dict, observed: dict) -> dict:
    reasons: List[str] = []
    pred_type = predicted.get("semantic_type")
    obs_type = observed.get("semantic_type")
    if pred_type == SEMANTIC_SCENARIO:
        reasons.append("SCENARIO artifacts are not forecasts and cannot be scored as forecast-vs-reality.")
    if pred_type == SEMANTIC_SIMULATION:
        reasons.append("SIMULATION artifacts are not issued historical forecasts.")
    if pred_type == SEMANTIC_MODELLED_AOI:
        reasons.append("AOI probability (MODELLED) is a different target than spatial flood extent.")
    if pred_type == SEMANTIC_EXPERIMENT:
        reasons.append("Spatial experiment is NOT_VALIDATED; no operational forecast map exists.")
    if pred_type and pred_type != SEMANTIC_FORECAST:
        reasons.append(f"predicted semantic_type={pred_type} is not FORECAST.")
    if obs_type and obs_type != SEMANTIC_OBSERVATION:
        reasons.append(f"observed semantic_type={obs_type} is not OBSERVATION.")
    if predicted.get("event_id") and observed.get("event_id") and predicted["event_id"] != observed["event_id"]:
        reasons.append("different event_id")
    pred_target = predicted.get("target_definition")
    obs_target = observed.get("target_definition")
    if pred_target and obs_target and pred_target != obs_target:
        reasons.append(f"different target definition ({pred_target} vs {obs_target})")
    pred_shape = predicted.get("grid_shape")
    obs_shape = observed.get("grid_shape")
    if pred_shape and obs_shape and tuple(pred_shape) != tuple(obs_shape):
        reasons.append(f"incompatible spatial grid {pred_shape} vs {obs_shape}")
    pred_res = predicted.get("spatial_resolution_m")
    obs_res = observed.get("spatial_resolution_m")
    if pred_res and obs_res and float(pred_res) != float(obs_res):
        reasons.append(
            f"resolution mismatch {pred_res}m vs {obs_res}m; maps are not compared as equivalent"
        )
    if predicted.get("flood_threshold") is not None and observed.get("flood_threshold") is not None:
        if float(predicted["flood_threshold"]) != float(observed["flood_threshold"]):
            reasons.append("incompatible flood threshold")
    if predicted.get("units") and observed.get("units") and predicted["units"] != observed["units"]:
        reasons.append(f"incompatible units ({predicted['units']} vs {observed['units']})")
    pred_time = predicted.get("valid_at") or predicted.get("timestamp")
    obs_time = observed.get("valid_at") or observed.get("timestamp")
    if pred_time and obs_time and str(pred_time)[:19] != str(obs_time)[:19]:
        reasons.append(
            f"timestamps are not paired ({pred_time} vs {obs_time}); no interpolated match is invented"
        )
    comparable = not reasons
    return {
        "comparison": "COMPARABLE" if comparable else "NOT_COMPARABLE",
        "comparable": comparable,
        "reasons": reasons,
        "predicted_semantic_type": pred_type,
        "observed_semantic_type": obs_type,
    }


def compare_binary_maps(
    predicted: np.ndarray,
    observed: np.ndarray,
    unknown: int = CLASS_UNKNOWN,
    threshold: float = 0.5,
) -> dict:
    pred = np.asarray(predicted)
    obs = np.asarray(observed)
    if pred.shape != obs.shape:
        return {
            "comparison": "NOT_COMPARABLE",
            "comparable": False,
            "reason": f"grid_shape_mismatch {pred.shape} vs {obs.shape}",
            "metrics": None,
            "difference_classes": None,
        }
    pred_valid = np.isfinite(pred.astype(float)) & (pred != unknown)
    obs_valid = np.isfinite(obs.astype(float)) & (obs != unknown)
    joint = pred_valid & obs_valid
    n_unknown = int(np.size(obs) - np.sum(joint))
    if int(np.sum(joint)) == 0:
        return {
            "comparison": "NOT_COMPARABLE",
            "comparable": False,
            "reason": "no jointly valid pixels; unknown is not scored as dry",
            "metrics": None,
            "n_unknown": n_unknown,
        }
    y = (obs[joint] >= threshold).astype(np.float64)
    p = pred[joint].astype(np.float64)
    if np.nanmax(p) > 1.0:
        p = (p >= threshold).astype(np.float64)
    else:
        p = np.clip(p, 0.0, 1.0)
    cm = confusion_at_threshold(y, p, threshold)
    pred_bin = p >= threshold
    classes = np.full(obs.shape, CLASS_UNKNOWN, dtype=np.uint8)
    pred_full = np.zeros(obs.shape, dtype=bool)
    obs_full = np.zeros(obs.shape, dtype=bool)
    pred_full[joint] = pred_bin
    obs_full[joint] = y > 0.5
    classes[joint & pred_full & obs_full] = CLASS_TP
    classes[joint & pred_full & ~obs_full] = CLASS_FP
    classes[joint & ~pred_full & obs_full] = CLASS_FN
    classes[joint & ~pred_full & ~obs_full] = CLASS_TN
    dice = float(cm["f1"])
    return {
        "comparison": "COMPARABLE",
        "comparable": True,
        "metrics": {
            "iou": cm["csi"],
            "dice": dice,
            "f1": cm["f1"],
            "precision": cm["precision"],
            "recall": cm["recall"],
            "mae": None,
            "rmse": None,
            "brier": brier(y, p),
            "tp": cm["tp"],
            "fp": cm["fp"],
            "fn": cm["fn"],
            "tn": cm["tn"],
            "n_jointly_valid": int(np.sum(joint)),
            "n_unknown_unscored": n_unknown,
            "accuracy_claim": None,
        },
        "difference_classes": {
            "true_positive": CLASS_TP,
            "false_positive": CLASS_FP,
            "false_negative": CLASS_FN,
            "true_negative": CLASS_TN,
            "unknown": CLASS_UNKNOWN,
            "legend": {
                "predicted_flood": "TP+FP on jointly valid pixels",
                "observed_flood": "TP+FN on jointly valid pixels",
                "missed_flood": "FN",
                "false_alarm": "FP",
            },
            "array": classes,
        },
        "depth_comparison": "UNAVAILABLE",
        "depth_reason": "Binary flood maps do not provide observed depth.",
    }


def classify_difference(predicted: np.ndarray, observed: np.ndarray, unknown: int = CLASS_UNKNOWN) -> np.ndarray:
    result = compare_binary_maps(predicted, observed, unknown=unknown)
    if not result.get("comparable"):
        raise ValueError(result.get("reason") or "NOT_COMPARABLE")
    return result["difference_classes"]["array"]


def timing_error(
    observed_times: Sequence[str],
    predicted_times: Sequence[str],
    *,
    observed_onset: Optional[str] = None,
    predicted_onset: Optional[str] = None,
    temporal_resolution: Optional[str] = None,
) -> dict:
    if not predicted_times:
        return {
            "status": "UNAVAILABLE",
            "reason": "No prediction timestamps exist. Timing error is not inferred.",
            "forecast_lead": None,
            "observed_onset": None,
            "predicted_onset": None,
            "onset_error": None,
            "peak_timing_error": None,
        }
    if not observed_times:
        return {
            "status": "UNAVAILABLE",
            "reason": "No observation timestamps exist.",
            "forecast_lead": None,
            "observed_onset": None,
            "predicted_onset": None,
            "onset_error": None,
            "peak_timing_error": None,
        }
    obs0 = observed_onset or (sorted(observed_times)[0] if observed_times else None)
    pred0 = predicted_onset or (sorted(predicted_times)[0] if predicted_times else None)
    resolution = temporal_resolution or (
        "Sparse scene times only. Onset is the first available timestamp, not a sub-scene onset."
    )
    return {
        "status": "COMPUTED_AT_SCENE_RESOLUTION",
        "forecast_lead": None,
        "observed_onset": obs0,
        "predicted_onset": pred0,
        "onset_error": None,
        "peak_timing_error": None,
        "temporal_resolution": resolution,
        "note": (
            "Onset is not inferred between sparse SAR scenes. "
            "Lead/peak errors stay null unless both series have documented issue and valid times."
        ),
        "n_observed_times": len(list(observed_times)),
        "n_predicted_times": len(list(predicted_times)),
    }


def compare_event(event_id: str, prediction_id: Optional[str] = None) -> dict:
    event = _find_event(event_id)
    if event is None:
        raise KeyError(event_id)
    obs = event_observations(event_id)
    preds = discover_predictions(event_id)
    chosen = None
    if prediction_id:
        chosen = next((row for row in preds["predictions"] if row.get("prediction_id") == prediction_id), None)
        if chosen is None:
            return {
                "event_id": event_id,
                "comparison": "UNAVAILABLE",
                "reason": f"Prediction {prediction_id} was not found in the artifact registry.",
                "metrics": None,
                "spatial_error": None,
                "timing_error": timing_error([row["timestamp"] for row in obs["observations"] if row.get("timestamp")], []),
                "depth_comparison": "UNAVAILABLE",
            }
    forecast_maps = [
        row
        for row in preds["predictions"]
        if row.get("semantic_type") == SEMANTIC_FORECAST and row.get("artifact_id")
    ]
    if chosen is None and not forecast_maps:
        associated = [
            row
            for row in preds["predictions"]
            if row.get("semantic_type") in {SEMANTIC_SCENARIO, SEMANTIC_SIMULATION} and row.get("artifact_id")
        ]
        reason = (
            "No issued historical flood-map forecast artifact exists for this event. "
            "Observed replay remains available. Forecast-vs-reality is not computed."
        )
        if associated:
            reason += (
                f" {len(associated)} scenario/simulation artifact(s) are listed for inspection "
                "and are not labeled FORECAST."
            )
        first_obs = (obs["observations"] or [None])[0]
        compat = check_compatibility(
            chosen or {"semantic_type": SEMANTIC_EXPERIMENT, "event_id": event_id},
            {
                "semantic_type": SEMANTIC_OBSERVATION,
                "event_id": event_id,
                "target_definition": TARGET_BINARY_EXTENT,
                "timestamp": (first_obs or {}).get("timestamp"),
            },
        )
        return {
            "event_id": event_id,
            "comparison": "UNAVAILABLE",
            "compatibility": compat,
            "reason": reason,
            "metrics": None,
            "spatial_error": None,
            "event_level_metrics": None,
            "macro_statistics": None,
            "micro_statistics": None,
            "timing_error": timing_error(
                [row["timestamp"] for row in obs["observations"] if row.get("timestamp")],
                [],
            ),
            "depth_comparison": "UNAVAILABLE",
            "depth_reason": "Observed GFM product is binary flood extent, not water depth. Predicted depth is not paired.",
            "historical_model_timeline": {
                "status": "COMPARISON INCOMPLETE",
                "issue_time": None,
                "input_window": None,
                "forecast_horizon": None,
                "predicted_state": None,
                "observed_state": (first_obs or {}).get("timestamp"),
            },
            "predictions": preds["predictions"],
            "observations": obs["observations"],
        }
    target = chosen or forecast_maps[0]
    first_obs = (obs["observations"] or [{}])[0]
    compat = check_compatibility(
        {
            **target,
            "event_id": event_id,
            "timestamp": target.get("issue_time"),
            "units": target.get("units") or "unknown",
        },
        {
            "semantic_type": SEMANTIC_OBSERVATION,
            "event_id": event_id,
            "target_definition": TARGET_BINARY_EXTENT,
            "timestamp": first_obs.get("timestamp"),
            "spatial_resolution_m": first_obs.get("resolution_m"),
            "units": "binary_flood_extent",
        },
    )
    if not compat["comparable"]:
        return {
            "event_id": event_id,
            "comparison": "NOT_COMPARABLE",
            "compatibility": compat,
            "reason": "; ".join(compat["reasons"]),
            "metrics": None,
            "spatial_error": None,
            "timing_error": timing_error(
                [row["timestamp"] for row in obs["observations"] if row.get("timestamp")],
                [target.get("issue_time")] if target.get("issue_time") else [],
            ),
            "depth_comparison": "UNAVAILABLE",
            "prediction": target,
        }
    from floodlens.application.demo_fixtures import DEMO_EVENT_ID, demo_compare_metrics, demo_fixtures_enabled

    demo_pair = demo_fixtures_enabled() and event_id == DEMO_EVENT_ID
    return {
        "event_id": event_id,
        "comparison": "COMPARABLE",
        "compatibility": compat,
        "prediction": target,
        "metrics": demo_compare_metrics() if demo_pair else None,
        "depth_comparison": "UNAVAILABLE",
        "data_status": "DEMO" if demo_pair else "PARTIAL",
        "note": (
            "DEMO forecast-vs-reality pair. Not a validated skill score. Raster arrays stay out of JSON."
            if demo_pair
            else "Comparable forecast map found. Raster arrays stay out of JSON."
        ),
        "provenance": envelope(
            data_status="DEMO" if demo_pair else "PARTIAL",
            provider="demo-historical-fixture" if demo_pair else "artifact-registry",
            dataset="forecast-vs-reality",
            freshness="SNAPSHOT",
            simulated=demo_pair,
        ),
    }


def event_detail(event_id: str) -> dict:
    event = _find_event(event_id)
    if event is None:
        raise KeyError(event_id)
    obs = event_observations(event_id)
    metrics = observation_transition_metrics(event_id)
    preds = discover_predictions(event_id)
    compare = compare_event(event_id)
    return {
        "event": event,
        "timeline": obs["observations"],
        "observation_metrics": metrics,
        "predictions": preds["predictions"],
        "compare": {
            "comparison": compare.get("comparison"),
            "reason": compare.get("reason"),
            "compatibility": compare.get("compatibility"),
            "metrics": compare.get("metrics"),
            "depth_comparison": compare.get("depth_comparison"),
            "timing_error": compare.get("timing_error"),
            "historical_model_timeline": compare.get("historical_model_timeline"),
        },
        "spatial_ai": {
            "status": SPATIAL_AI_STATUS,
            "spatial_api": SPATIAL_API_STATUS,
        },
        "target_b": {
            "status": "PARTIALLY_FEASIBLE",
            "primary_target": TARGET_NEWLY_FLOODED,
            "n_pairs": metrics.get("n_pairs") if metrics.get("available") else 0,
        },
        "provenance": envelope(
            data_status=_catalog_envelope_status(event.get("data_status")),
            provider=event.get("observation_source") or "historical-catalog",
            dataset="historical-event",
            freshness="UNAVAILABLE",
        ),
        "limitations": [
            "Human-readable GFM names are not invented; event_id is the label.",
            "No retrospective flood-map forecast is fabricated.",
            "Unknown GFM pixels stay unknown.",
            "Scenario and simulation jobs are not historical forecasts.",
            "AOI GBDT is not a spatial flood map.",
            "Spatial AI remains NOT_VALIDATED.",
        ],
    }


def _split_counts(metrics: dict) -> dict:
    out = {}
    for split in ("train", "val", "test"):
        block = (metrics or {}).get(split) or {}
        out[split] = {
            "n": block.get("n"),
            "prevalence": block.get("prevalence"),
            "label_kind": block.get("label_kind"),
            "track": block.get("track"),
        }
    return out


def _gbdt_headline(metrics: dict) -> dict:
    test = (metrics or {}).get("test") or {}
    models = test.get("models") or {}
    xgb = models.get("xgboost_class") or {}
    op = xgb.get("operating_point") or {}
    n_test = test.get("n")
    limited = bool(n_test is not None and n_test < 30) or float(test.get("prevalence") or 0) == 0
    val = (metrics or {}).get("val") or {}
    if float(val.get("prevalence") or 0) == 0:
        limited = True
    return {
        "task": "AOI flood-occurrence probability (MODELLED GloFAS Q exceedance)",
        "not": ["SPATIAL_FLOOD_MAP_MODEL"],
        "dataset": load_registry().get("dataset_version"),
        "dataset_version": load_registry().get("dataset_version"),
        "label_kind": load_registry().get("label_kind") or "MODELLED",
        "iou": None,
        "auprc": xgb.get("auprc"),
        "brier": xgb.get("brier"),
        "f1": op.get("f1"),
        "csi": op.get("csi"),
        "n_test_samples": n_test,
        "test_events": None,
        "horizon": "24/48/72h AOI scalar",
        "target": TARGET_AOI_Q,
        "accuracy_claim": None,
        "statistical_power_limited": limited,
        "statistical_power_note": (
            "Val split prevalence is 0 outside the named holdout; AUPRC/AUROC may be undefined. "
            "n is daily AOI samples, not independent flood-map events. "
            "STATISTICAL POWER LIMITED for event-level flood-map claims."
        ),
        "uncertainty": {
            "status": "not calibrated",
            "calibrated": False,
            "available": False,
            "note": "Metric scores are not converted into confidence.",
        },
    }


def model_registry_payload() -> dict:
    from floodlens.application.monitoring import model_catalog

    catalog = model_catalog()
    ai = load_registry()
    spatial = load_spatial_registry()
    enriched = []
    for row in catalog["models"]:
        item = dict(row)
        if item.get("id") == "ai-forecast":
            item.update(
                {
                    "model_id": ai.get("model_id"),
                    "version": ai.get("version") or "v0.1",
                    "task": "AOI flood-occurrence probability (MODELLED GloFAS Q exceedance)",
                    "training_dataset": ai.get("dataset_version"),
                    "training_time": ai.get("training_run"),
                    "validation_status": ai.get("status"),
                    "public_status": public_status(ai),
                    "splits": ai.get("validated_split_ids"),
                    "split_counts": _split_counts(ai.get("metrics") or {}),
                    "limitations": [
                        "Not a spatial flood map.",
                        "Labels are MODELLED GloFAS Q exceedance, not in-situ flood maps.",
                        "Do not quote accuracy %.",
                    ],
                    "headline": _gbdt_headline(ai.get("metrics") or {}),
                    "uncertainty": {
                        "status": "not calibrated",
                        "calibrated": False,
                        "available": False,
                    },
                }
            )
        elif item.get("kind") == "AI_SPATIAL":
            item.update(
                {
                    "scientific_status": SPATIAL_AI_STATUS,
                    "spatial_api": SPATIAL_API_STATUS,
                    "task": "Spatial flood occurrence (not operational)",
                    "training_dataset": spatial.get("dataset_version"),
                    "training_time": spatial.get("run_id"),
                    "validation_status": SPATIAL_AI_STATUS,
                    "metrics": None,
                    "limitations": [
                        "NOT_VALIDATED. No spatial-AI forecast metrics are shown.",
                        "Does not inherit AOI GBDT VALIDATED status.",
                        "Spatial API remains UNAVAILABLE.",
                    ],
                    "uncertainty": {"status": "unavailable", "calibrated": False, "available": False},
                }
            )
        elif item.get("kind") == "PHYSICS_BASELINE":
            item.update(
                {
                    "task": "Short SWE physics burst",
                    "training_dataset": None,
                    "status": "IMPLEMENTED",
                    "validation_status": "solver protected; not a historical forecast skill score",
                    "metrics": None,
                    "limitations": ["Physics jobs are SIMULATION, not issued historical forecasts."],
                    "uncertainty": {"status": "unavailable", "calibrated": False, "available": False},
                }
            )
        elif item.get("kind") == "HEURISTIC":
            item.update(
                {
                    "task": TARGET_HEURISTIC_AOI,
                    "model_version": FORECAST_MODEL_VERSION,
                    "metrics": None,
                    "limitations": [
                        "DEMO meteorological-horizon product. Not a retrospective GFM flood-map forecast.",
                        "Confidence is NOT_CALIBRATED.",
                    ],
                    "uncertainty": {"status": "not calibrated", "calibrated": False, "available": False},
                }
            )
        else:
            item.setdefault("metrics", None)
            item.setdefault("uncertainty", {"status": "unavailable", "calibrated": False, "available": False})
        item["accuracy_claim"] = None
        enriched.append(item)
    return {
        "models": enriched,
        "spatial_ai": SPATIAL_AI_STATUS,
        "spatial_api": SPATIAL_API_STATUS,
        "target_b": "PARTIALLY_FEASIBLE",
        "model_training": "NOT_AUTHORIZED",
        "accuracy_claim": None,
        "physics": PHYSICS_MODEL_VERSION,
        "forecast_heuristic": FORECAST_MODEL_VERSION,
    }


def model_performance_payload(model_id: Optional[str] = None) -> dict:
    registry = model_registry_payload()
    models = registry["models"]
    if model_id:
        models = [row for row in models if row.get("id") == model_id]
        if not models:
            raise KeyError(model_id)
    selected = models[0] if model_id else next((row for row in models if row.get("id") == "ai-forecast"), models[0])
    return {
        "ai_flood_model": selected.get("model_id") if selected.get("id") == "ai-forecast" else None,
        "accuracy_claim": None,
        "message": (
            "No accuracy percentage is displayed. Metrics are named (AUPRC/Brier/CSI) with dataset, split, "
            "horizon, and target. Spatial AI remains NOT_VALIDATED and has no forecast-map metrics."
        ),
        "physics": PHYSICS_MODEL_VERSION,
        "forecast_heuristic": FORECAST_MODEL_VERSION,
        "spatial_ai": {"status": SPATIAL_AI_STATUS, "spatial_api": SPATIAL_API_STATUS, "metrics": None},
        "models": registry["models"],
        "selected": selected,
        "splits": selected.get("splits") or selected.get("split_counts"),
        "uncertainty": selected.get("uncertainty") or {"status": "unavailable", "calibrated": False, "available": False},
    }


def generate_historical_report(event_id: str, city_id: Optional[str] = None) -> dict:
    detail = event_detail(event_id)
    compare = detail.get("compare") or {}
    has_forecast = compare.get("comparison") == "COMPARABLE"
    body = {
        "event": detail["event"],
        "timeline": detail["timeline"],
        "observations": detail["timeline"],
        "observation_metrics": detail["observation_metrics"],
        "available_predictions": [
            {
                "prediction_id": row.get("prediction_id"),
                "semantic_type": row.get("semantic_type"),
                "model": row.get("model"),
                "status": row.get("status"),
                "artifact": row.get("artifact_id"),
            }
            for row in detail["predictions"]
        ],
        "comparison": {
            "status": compare.get("comparison"),
            "reason": compare.get("reason"),
            "metrics": compare.get("metrics") if has_forecast else None,
        },
        "error_maps": None if not has_forecast else compare.get("spatial_error"),
        "model_information": model_registry_payload(),
        "limitations": detail["limitations"],
        "provenance": detail["provenance"],
        "spatial_ai": detail["spatial_ai"],
        "target_b": detail["target_b"],
    }
    if not has_forecast:
        body["forecast_accuracy"] = None
        body["forecast_accuracy_omitted"] = True
        body["forecast_accuracy_reason"] = compare.get("reason") or "No compatible prediction artifact."
    store = get_platform_store()
    report = store.put_report(
        {
            "city_id": city_id or (detail["event"].get("regions") or ["unknown"])[0],
            "event_id": event_id,
            "kind": "historical",
            "model_version": FORECAST_MODEL_VERSION,
            "physics_model_version": PHYSICS_MODEL_VERSION,
            "body": body,
            "formats": ["json", "csv", "pdf"],
        }
    )
    store.audit("report.historical", detail={"report_id": report["id"], "event_id": event_id})
    from floodlens.application.reports import _finalize_snapshot

    report["kind"] = "historical"
    report.setdefault("source_versions", {"data_version": "platform-v1"})
    return _finalize_snapshot(report, created_by=None, kind="historical", map_state=None)
