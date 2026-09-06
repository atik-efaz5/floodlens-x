"""AOI-clipped event dataset from GFM processed maps + Open-Meteo features."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from floodlens.ml.leakage import parse_ts
from floodlens.ml.real_dataset import Q_LOOKBACK_DAYS, load_raw
from floodlens.ml.schema import LOOKBACK_HOURS
from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR
from floodlens.ml.spatial.leakage import assert_no_spatial_leakage
from floodlens.ml.spatial.schema import (
    GRID_SIZE,
    HORIZON_HOURS,
    LABEL_OBSERVED,
    LABEL_SIMULATED,
    SPATIAL_DATASET_VERSION,
    UNKNOWN,
    SpatialForecastSample,
)
from floodlens.ml.spatial.dem_plan import try_load_city_dem
from floodlens.ml.spatial.events import assign_event_ids, inventory as event_inventory
from floodlens.ml.spatial.splits import assign_event_level_splits, assign_temporal
from floodlens.ml.spatial.tiles import city_bounds, grid_spec


def _iso(stamp) -> str:
    from datetime import timezone as tz

    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=tz.utc)
    return stamp.astimezone(tz.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _index_hourly(times: Sequence[str], values: Sequence) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for t, v in zip(times, values):
        stamp = str(t).replace("Z", "")
        if len(stamp) == 16:
            stamp = stamp + ":00"
        out[stamp] = None if v is None else float(v)
    return out


def _index_series(times: Sequence[str], values: Sequence) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for t, v in zip(times, values):
        key = str(t)[:10]
        out[key] = None if v is None else float(v)
    return out


def _floor_hour(issue):
    """Open-Meteo precip is hourly; GFM scene clocks are not. Align lookback to the last completed hour."""
    return issue.replace(minute=0, second=0, microsecond=0)


def _features_at_issue(city_id: str, issue, precip: dict, discharge: dict) -> Optional[dict]:
    p_payload = (precip.get("cities") or {}).get(city_id)
    q_payload = (discharge.get("cities") or {}).get(city_id)
    if not p_payload or not q_payload:
        return None
    issue_h = _floor_hour(issue)
    p_hourly = _index_hourly(p_payload["time"], p_payload["precipitation_mm"])
    q_daily = _index_series(q_payload["time"], q_payload["river_discharge_m3s"])
    look_vals = []
    look_kinds = []
    complete = 0
    for h in range(LOOKBACK_HOURS, 0, -1):
        stamp = (issue_h - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
        val = p_hourly.get(stamp)
        if val is None:
            look_vals.append(0.0)
            look_kinds.append("UNAVAILABLE")
        else:
            look_vals.append(float(val))
            look_kinds.append("OBSERVED")
            complete += 1
    frac = complete / float(LOOKBACK_HOURS)
    if frac < 0.80:
        return None
    windows = {}
    for width in (1, 3, 6, 12, 24, 48, 72):
        acc = []
        miss = 0
        for h in range(1, width + 1):
            stamp = (issue_h - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
            val = p_hourly.get(stamp)
            if val is None:
                miss += 1
            else:
                acc.append(float(val))
        windows[width] = float(sum(acc)) if (width - miss) / width >= 0.80 else None
    if windows[24] is None:
        return None
    q_hist: List[Optional[float]] = []
    for d in range(Q_LOOKBACK_DAYS, 0, -1):
        key = (issue_h - timedelta(days=d)).strftime("%Y-%m-%d")
        qv = q_daily.get(key)
        q_hist.append(None if qv is None else float(qv))
    if q_hist[-1] is None:
        return None
    return {
        "x_precip_hourly": look_vals,
        "x_precip_hourly_kind": look_kinds,
        "lookback_complete_frac": frac,
        "x_antecedent_24h": float(windows[24]),
        "x_antecedent_72h": windows.get(72),
        "x_glofas_q_lookback": q_hist,
        "precip_windows": {int(k): v for k, v in windows.items() if v is not None},
    }


def load_index(processed_dir: Optional[Path] = None) -> dict:
    processed_dir = Path(processed_dir or PROCESSED_DIR)
    path = processed_dir / "index.json"
    if not path.exists():
        return {"scenes": [], "n_kept": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def build_spatial_samples(
    processed_dir: Optional[Path] = None,
    real_dir: Optional[Path] = None,
) -> Tuple[List[SpatialForecastSample], dict]:
    processed_dir = Path(processed_dir or PROCESSED_DIR)
    index = load_index(processed_dir)
    scenes = list(index.get("scenes") or [])
    if not scenes:
        meta = {
            "dataset_version": SPATIAL_DATASET_VERSION,
            "n": 0,
            "label_kind": LABEL_OBSERVED,
            "available": False,
            "reason": "No GFM AOI-clipped scenes. Run scripts/phase5_acquire_gfm.py after probe.",
        }
        return [], meta
    discharge, precip, _manifest = load_raw(real_dir)
    # chronological per city for lagged persistence
    by_city: Dict[str, List[dict]] = {}
    for scene in scenes:
        dt = scene.get("datetime")
        for city_id in (scene.get("cities") or {}):
            by_city.setdefault(city_id, []).append(scene)
    for city_id in by_city:
        by_city[city_id].sort(key=lambda s: s.get("datetime") or "")

    samples: List[SpatialForecastSample] = []
    dropped = 0
    for city_id, city_scenes in by_city.items():
        prev_map = None
        prev_valid = None
        spec = grid_spec(city_id)
        bounds = list(city_bounds(city_id))
        for scene in city_scenes:
            npz_path = processed_dir / city_id / f"{scene['id']}.npz"
            if not npz_path.exists():
                dropped += 1
                continue
            blob = np.load(npz_path)
            y = np.asarray(blob["y_flood"])
            yf = np.asarray(blob["y_flood_frac"])
            valid_at = parse_ts(scene["datetime"])
            issue = valid_at - timedelta(hours=HORIZON_HOURS)
            feats = _features_at_issue(city_id, issue, precip, discharge)
            if feats is None:
                dropped += 1
                continue
            persistence = None
            persistence_valid = None
            if prev_map is not None and prev_valid is not None and prev_valid < issue:
                persistence = prev_map
                persistence_valid = prev_valid
            dem, dem_ok = try_load_city_dem(city_id)
            sample = SpatialForecastSample(
                city_id=city_id,
                issue_time=_iso(issue),
                valid_at=_iso(valid_at),
                horizon_hours=HORIZON_HOURS,
                y_flood=y,
                y_flood_frac=yf,
                x_precip_hourly=feats["x_precip_hourly"],
                x_precip_hourly_kind=feats["x_precip_hourly_kind"],
                x_antecedent_24h=feats["x_antecedent_24h"],
                x_antecedent_72h=feats["x_antecedent_72h"],
                x_glofas_q_lookback=feats["x_glofas_q_lookback"],
                x_persistence=None if persistence is None else np.asarray(persistence, dtype=np.float64),
                x_dem=None if not dem_ok else dem,
                precip_is_aoi_point=True,
                q_is_glofas_cell=True,
                dem_present=bool(dem_ok),
                label_kind=LABEL_OBSERVED,
                label_source="copernicus-gfm-ensemble-flood-extent",
                lookback_complete_frac=feats["lookback_complete_frac"],
                bounds=bounds,
                resolution_m=float(spec["dx_m"]),
                scene_id=scene["id"],
                extra={
                    "precip_windows": feats["precip_windows"],
                    "precip_is_aoi_point": True,
                    "q_is_glofas_cell": True,
                    "dem_present": bool(dem_ok),
                    "persistence_valid_at": None if persistence_valid is None else _iso(persistence_valid),
                    "grid": spec,
                    "gfm_valid_frac": (scene.get("cities") or {}).get(city_id, {}).get("valid_frac"),
                },
            )
            samples.append(sample)
            # previous completed observation = this label map (available after valid_at)
            prev_map = np.where(y == UNKNOWN, np.nan, y.astype(np.float64))
            prev_valid = valid_at
    assign_temporal(samples)
    assign_event_ids(samples)
    if samples:
        assert_no_spatial_leakage(samples)
    inv = event_inventory(samples) if samples else {}
    meta = {
        "dataset_version": SPATIAL_DATASET_VERSION,
        "n": len(samples),
        "dropped": dropped,
        "label_kind": LABEL_OBSERVED,
        "horizon_hours": HORIZON_HOURS,
        "grid": GRID_SIZE,
        "available": bool(samples),
        "splits": {name: sum(1 for s in samples if s.split == name) for name in ("train", "val", "test")},
        "cities": sorted({s.city_id for s in samples}),
        "not_horizons": [6, 12, 24, 48, 72],
        "not_horizons_reason": "GFM scenes are not daily 6–72 h maps. Do not invent those labels.",
        "index": {k: index.get(k) for k in ("n_kept", "raw_bytes", "source", "tile", "license_stac")},
        "events": inv,
        "validation_verdict": inv.get("verdict") or "INSUFFICIENT FOR VALIDATION",
    }
    return samples, meta


def make_synthetic_sample(
    city_id: str = "sunamganj",
    issue_time: str = "2018-06-01T00:00:00Z",
    split: str = "train",
    seed: int = 0,
) -> SpatialForecastSample:
    """SIMULATED maps for pipeline tests only. Not real skill."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, size=(GRID_SIZE, GRID_SIZE), dtype=np.uint8)
    y[0, 0] = UNKNOWN
    issue = parse_ts(issue_time)
    valid = issue + timedelta(hours=HORIZON_HOURS)
    pers = np.where(y == UNKNOWN, np.nan, y.astype(np.float64))
    pers = np.roll(pers, 1, axis=0)
    return SpatialForecastSample(
        city_id=city_id,
        issue_time=issue_time,
        valid_at=_iso(valid),
        horizon_hours=HORIZON_HOURS,
        y_flood=y,
        y_flood_frac=y.astype(np.float32),
        x_precip_hourly=[0.2] * LOOKBACK_HOURS,
        x_precip_hourly_kind=["SIMULATED"] * LOOKBACK_HOURS,
        x_antecedent_24h=4.8,
        x_antecedent_72h=10.0,
        x_glofas_q_lookback=[1.0] * 7,
        x_persistence=pers,
        x_dem=None,
        precip_is_aoi_point=True,
        q_is_glofas_cell=True,
        dem_present=False,
        label_kind="SIMULATED",
        label_source="synthetic-pipeline",
        lookback_complete_frac=1.0,
        bounds=list(city_bounds(city_id)),
        split=split,
        scene_id=f"synth-{seed}",
        extra={
            "precip_windows": {24: 4.8, 72: 10.0},
            "persistence_valid_at": _iso(issue - timedelta(days=8)),
            "synthetic": True,
        },
    )


def build_spatial_samples_v2(
    processed_dir: Optional[Path] = None,
    real_dir: Optional[Path] = None,
) -> Tuple[List[SpatialForecastSample], dict]:
    """Phase 6 tensors: 64×64, precip lattice, DEM, river distance. GFM OBSERVED 192 h."""
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR_V2
    from floodlens.ml.spatial.aois_v2 import aoi_bounds, q_proxy_city
    from floodlens.ml.spatial.dem_plan import height_above_nearest_river, try_load_aoi_dem
    from floodlens.ml.spatial.elevation_lattice import dem_and_slope
    from floodlens.ml.spatial.precip_lattice import precip_maps_at_issue
    from floodlens.ml.spatial.river_features import river_distance_map, river_mask_map
    from floodlens.ml.spatial.schema import GRID_SIZE_V2, SPATIAL_DATASET_VERSION_V2
    from floodlens.ml.spatial.tiles import cell_size_m

    processed_dir = Path(processed_dir or PROCESSED_DIR_V2)
    index = load_index(processed_dir)
    dataset_version = index.get("dataset_version") or SPATIAL_DATASET_VERSION_V2
    scenes = list(index.get("scenes") or [])
    if not scenes:
        return [], {
            "dataset_version": dataset_version,
            "n": 0,
            "available": False,
            "reason": "No GFM v2 processed maps. Run scripts/phase6_acquire.py.",
            "label_kind": LABEL_OBSERVED,
        }
    discharge, precip, _manifest = load_raw(real_dir)
    by_aoi: Dict[str, List[dict]] = {}
    for scene in scenes:
        for aoi_id in (scene.get("cities") or {}):
            by_aoi.setdefault(aoi_id, []).append(scene)
    for aoi_id in by_aoi:
        by_aoi[aoi_id].sort(key=lambda s: s.get("datetime") or "")

    samples: List[SpatialForecastSample] = []
    dropped = 0
    for aoi_id, aoi_scenes in by_aoi.items():
        prev_map = None
        prev_valid = None
        bounds = list(aoi_bounds(aoi_id))
        dx_m, _dy = cell_size_m(tuple(bounds), GRID_SIZE_V2, GRID_SIZE_V2)
        proxy = q_proxy_city(aoi_id)
        for scene in aoi_scenes:
            if scene.get("synthetic") or scene.get("label_kind") in {"SIMULATED", "DEMO"}:
                dropped += 1
                continue
            npz_path = processed_dir / aoi_id / f"{scene['id']}.npz"
            if not npz_path.exists():
                dropped += 1
                continue
            blob = np.load(npz_path)
            y = np.asarray(blob["y_flood"])
            yf = np.asarray(blob["y_flood_frac"])
            valid_at = parse_ts(scene["datetime"])
            issue = valid_at - timedelta(hours=HORIZON_HOURS)
            ny, nx = y.shape
            rain = precip_maps_at_issue(aoi_id, _iso(issue), ny, nx)
            feats = _features_at_issue(proxy, issue, precip, discharge)
            if rain is not None and float(rain.get("cube_completeness") or 0.0) < 0.5:
                rain = None
            if rain is None and feats is None:
                dropped += 1
                continue
            if rain is None:
                rain = {
                    "precip_24h_map": None,
                    "precip_72h_map": None,
                    "precip_intensity_24h_map": None,
                    "n_lattice_points": 1,
                    "precip_is_aoi_point": True,
                    "x_antecedent_24h": feats["x_antecedent_24h"],
                    "x_antecedent_72h": feats["x_antecedent_72h"],
                    "t0": _iso(issue),
                    "input_start": _iso(issue - timedelta(hours=LOOKBACK_HOURS)),
                    "input_end": _iso(issue),
                    "rainfall_source": "open-meteo-archive-aoi-point",
                    "rainfall_status": "UNAVAILABLE"
                    if all(k == "UNAVAILABLE" for k in (feats.get("x_precip_hourly_kind") or []))
                    else "REANALYSIS",
                    "cube_completeness": float(feats.get("lookback_complete_frac") or 0.0),
                }
            if feats is None:
                feats = {
                    "x_precip_hourly": [0.0] * LOOKBACK_HOURS,
                    "x_precip_hourly_kind": ["UNAVAILABLE"] * LOOKBACK_HOURS,
                    "lookback_complete_frac": float(rain.get("cube_completeness") or 1.0),
                    "x_glofas_q_lookback": [None] * 7,
                    "precip_windows": {24: rain["x_antecedent_24h"]},
                }
            persistence = None
            persistence_valid = None
            if prev_map is not None and prev_valid is not None and prev_valid < issue:
                persistence = prev_map
                persistence_valid = prev_valid
            glo, glo_ok, glo_meta = try_load_aoi_dem(aoi_id, ny, nx)
            if glo_ok:
                dem, slope = glo, np.sqrt(sum(g * g for g in np.gradient(glo)))
                dem_source = glo_meta
            else:
                dem, slope = dem_and_slope(aoi_id, ny, nx)
                dem_source = {
                    "status": "OBSERVED" if dem is not None else "UNAVAILABLE",
                    "source": "open-meteo-elevation" if dem is not None else None,
                    "synthetic": False,
                    "fallback_reason": glo_meta.get("reason") if isinstance(glo_meta, dict) else None,
                }
            river = river_distance_map(aoi_id, ny, nx)
            river_mask = river_mask_map(river)
            har = height_above_nearest_river(dem, river_mask)
            dem_ok = dem is not None and np.any(np.isfinite(dem))
            cube_frac = float(rain.get("cube_completeness") or feats.get("lookback_complete_frac") or 1.0)
            tile_id = scene.get("tile") or (scene.get("cities") or {}).get(aoi_id, {}).get("tile_id")
            sample = SpatialForecastSample(
                city_id=aoi_id,
                issue_time=_iso(issue),
                valid_at=_iso(valid_at),
                horizon_hours=HORIZON_HOURS,
                y_flood=y,
                y_flood_frac=yf,
                x_precip_hourly=feats["x_precip_hourly"],
                x_precip_hourly_kind=feats["x_precip_hourly_kind"],
                x_antecedent_24h=float(rain["x_antecedent_24h"]),
                x_antecedent_72h=rain.get("x_antecedent_72h"),
                x_glofas_q_lookback=feats["x_glofas_q_lookback"],
                x_persistence=None if persistence is None else np.asarray(persistence, dtype=np.float64),
                x_dem=None if not dem_ok else dem,
                precip_is_aoi_point=bool(rain.get("precip_is_aoi_point", True)),
                q_is_glofas_cell=True,
                dem_present=bool(dem_ok),
                label_kind=LABEL_OBSERVED,
                label_source="copernicus-gfm-ensemble-flood-extent",
                lookback_complete_frac=cube_frac,
                bounds=bounds,
                resolution_m=float(dx_m),
                dataset_version=dataset_version,
                scene_id=scene["id"],
                extra={
                    "precip_windows": feats.get("precip_windows") or {24: rain["x_antecedent_24h"]},
                    "precip_24h_map": rain.get("precip_24h_map"),
                    "precip_72h_map": rain.get("precip_72h_map"),
                    "precip_intensity_24h_map": rain.get("precip_intensity_24h_map"),
                    "precip_cube_lattice": rain.get("precip_cube_lattice"),
                    "slope": slope,
                    "river_distance": river,
                    "river_mask": river_mask,
                    "height_above_river": har,
                    "n_lattice_points": rain.get("n_lattice_points"),
                    "q_proxy_city": proxy,
                    "dem_present": bool(dem_ok),
                    "dem_provenance": dem_source,
                    "persistence_valid_at": None if persistence_valid is None else _iso(persistence_valid),
                    "gfm_valid_frac": (scene.get("cities") or {}).get(aoi_id, {}).get("valid_frac"),
                    "grid_size": ny,
                    "tile_id": tile_id,
                    "region_id": aoi_id,
                    "scene_id": scene["id"],
                    "dataset_version": dataset_version,
                    "t0": rain.get("t0") or _iso(issue),
                    "input_start": rain.get("input_start"),
                    "input_end": rain.get("input_end"),
                    "target_time": _iso(valid_at),
                    "input_window": {"start": rain.get("input_start"), "end": rain.get("input_end")},
                    "label_window": {"valid_at": _iso(valid_at), "horizon_hours": HORIZON_HOURS},
                    "rainfall_source": rain.get("rainfall_source"),
                    "rainfall_status": rain.get("rainfall_status") or "UNAVAILABLE",
                    "cube_completeness": rain.get("cube_completeness"),
                    "alignment": (scene.get("cities") or {}).get(aoi_id, {}).get("grid")
                    or {
                        "crs": "EPSG:4326",
                        "resolution": f"{GRID_SIZE_V2}×{GRID_SIZE_V2}",
                        "resampling": "GFM Equi7 window block-reduce; rain/DEM/rivers on EPSG:4326 AOI grid",
                        "timestamp_alignment": "issue_time = valid_at - 192 h; rain hours strictly < t0",
                    },
                    "provenance": {
                        "source": "copernicus-gfm-ensemble-flood-extent",
                        "source_url": scene.get("href"),
                        "retrieval_time": scene.get("datetime"),
                        "source_version": "GFM ensemble_flood_extent AS020M",
                        "checksum": scene.get("checksum") or scene.get("sha256"),
                        "processing_version": dataset_version,
                        "status": "REAL",
                        "license": scene.get("license") or "proprietary",
                        "attribution": scene.get("attribution")
                        or "Copernicus Emergency Management Service — Global Flood Monitoring (GFM).",
                        "label_kind": LABEL_OBSERVED,
                    },
                },
            )
            samples.append(sample)
            prev_map = np.where(y == UNKNOWN, np.nan, y.astype(np.float64))
            prev_valid = valid_at
    assign_event_level_splits(samples)
    assign_event_ids(samples)
    if samples:
        assert_no_spatial_leakage(samples)
    inv = event_inventory(samples) if samples else {}
    meta = {
        "dataset_version": dataset_version,
        "n": len(samples),
        "dropped": dropped,
        "label_kind": LABEL_OBSERVED,
        "horizon_hours": HORIZON_HOURS,
        "grid": GRID_SIZE_V2,
        "available": bool(samples),
        "splits": {name: sum(1 for s in samples if s.split == name) for name in ("train", "val", "test")},
        "cities": sorted({s.city_id for s in samples}),
        "not_horizons": [6, 12, 24, 48, 72],
        "not_horizons_reason": "GFM scenes are not daily 6–72 h maps. Do not invent those labels.",
        "events": inv,
        "validation_verdict": inv.get("verdict") or "INSUFFICIENT FOR VALIDATION",
    }
    return samples, meta


def make_synthetic_sample_v2(
    city_id: str = "sunamganj",
    issue_time: str = "2018-06-01T00:00:00Z",
    split: str = "train",
    seed: int = 0,
) -> SpatialForecastSample:
    """SIMULATED v2 maps with spatial rain/DEM/river. Pipeline tests only."""
    from floodlens.ml.spatial.aois_v2 import aoi_bounds
    from floodlens.ml.spatial.schema import GRID_SIZE_V2, SPATIAL_DATASET_VERSION_V2

    rng = np.random.default_rng(seed)
    n = GRID_SIZE_V2
    y = rng.integers(0, 2, size=(n, n), dtype=np.uint8)
    y[0, 0] = UNKNOWN
    issue = parse_ts(issue_time)
    valid = issue + timedelta(hours=HORIZON_HOURS)
    pers = np.where(y == UNKNOWN, np.nan, y.astype(np.float64))
    pers = np.roll(pers, 1, axis=0)
    yy, xx = np.mgrid[0:n, 0:n]
    rain = 10.0 + 0.05 * xx.astype(np.float64)
    dem = 12.0 - 0.04 * yy.astype(np.float64) - 0.03 * xx.astype(np.float64) + 0.002 * yy * xx
    gy, gx = np.gradient(dem)
    slope = np.sqrt(gx * gx + gy * gy)
    river = (xx / max(n - 1, 1)).astype(np.float64)
    try:
        bounds = list(aoi_bounds(city_id))
    except Exception:
        bounds = list(aoi_bounds("sunamganj"))
    return SpatialForecastSample(
        city_id=city_id,
        issue_time=issue_time,
        valid_at=_iso(valid),
        horizon_hours=HORIZON_HOURS,
        y_flood=y,
        y_flood_frac=y.astype(np.float32),
        x_precip_hourly=[0.2] * LOOKBACK_HOURS,
        x_precip_hourly_kind=["SIMULATED"] * LOOKBACK_HOURS,
        x_antecedent_24h=float(np.mean(rain)),
        x_antecedent_72h=float(np.mean(rain) * 2.0),
        x_glofas_q_lookback=[1.0] * 7,
        x_persistence=pers,
        x_dem=dem,
        precip_is_aoi_point=False,
        q_is_glofas_cell=True,
        dem_present=True,
        label_kind=LABEL_SIMULATED,
        label_source="synthetic-pipeline",
        lookback_complete_frac=1.0,
        bounds=bounds,
        dataset_version=SPATIAL_DATASET_VERSION_V2,
        split=split,
        scene_id=f"synth-v2-{seed}",
        extra={
            "precip_windows": {24: float(np.mean(rain)), 72: float(np.mean(rain) * 2.0)},
            "precip_24h_map": rain,
            "precip_72h_map": rain * 2.0,
            "precip_intensity_24h_map": rain * 0.05,
            "slope": slope,
            "river_distance": river,
            "river_mask": (river < 0.25).astype(np.float64),
            "height_above_river": dem - float(np.min(dem)),
            "n_lattice_points": 9,
            "persistence_valid_at": _iso(issue - timedelta(days=8)),
            "synthetic": True,
            "tile_id": "E039N021T3",
            "region_id": city_id,
            "t0": issue_time,
            "input_start": _iso(issue - timedelta(hours=LOOKBACK_HOURS)),
            "input_end": issue_time,
            "target_time": _iso(valid),
            "rainfall_source": "synthetic-pipeline",
            "rainfall_status": "SIMULATED",
            "cube_completeness": 1.0,
            "provenance": {
                "source": "synthetic-pipeline",
                "status": "SIMULATED",
                "processing_version": SPATIAL_DATASET_VERSION_V2,
                "license": "not-for-training",
            },
        },
    )
