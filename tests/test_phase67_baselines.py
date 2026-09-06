"""Phase 6.7 Track A diagnostic baselines. No VALIDATED promotion. No CNN."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.baselines import PIXEL_FEATURE_NAMES, feature_indices, pixel_matrix, pixel_vector
from floodlens.ml.spatial.builder import make_synthetic_sample_v2
from floodlens.ml.spatial.events import assign_event_ids
from floodlens.ml.spatial.phase67 import (
    assert_frozen_splits,
    event_bootstrap_ci,
    evaluate_phase67,
    freeze_identifier,
    leakage_report,
    reliability_diagram,
    score_vectors,
    valid_yp,
)
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import GRID_SIZE_V2, LABEL_OBSERVED, UNKNOWN
from floodlens.ml.spatial.splits import assign_event_level_splits


def _observed_v2(city_id: str, issue_time: str, seed: int, split: str = "train"):
    sample = make_synthetic_sample_v2(city_id=city_id, issue_time=issue_time, seed=seed, split=split)
    sample.label_kind = LABEL_OBSERVED
    sample.dataset_version = "phase6.5-gfm-spatial-v2.1"
    sample.extra["synthetic"] = False
    sample.extra["rainfall_status"] = "REANALYSIS"
    sample.x_precip_hourly_kind = ["REANALYSIS"] * len(sample.x_precip_hourly_kind)
    return sample


def _corpus():
    specs = [
        ("kishoreganj", "2017-06-01T00:00:00Z", 1),
        ("dhaka_sw", "2017-08-01T00:00:00Z", 2),
        ("kishoreganj", "2018-06-15T00:00:00Z", 3),
        ("dhaka_ne", "2018-08-01T00:00:00Z", 4),
        ("kishoreganj", "2019-06-20T00:00:00Z", 5),
        ("dhaka_se", "2020-07-01T00:00:00Z", 6),
        ("sunamganj", "2022-05-20T00:00:00Z", 7),
        ("netrokona", "2023-06-15T00:00:00Z", 8),
    ]
    samples = [_observed_v2(city, stamp, seed) for city, stamp, seed in specs]
    assign_event_ids(samples)
    assign_event_level_splits(samples)
    return samples


def test_pixel_matrix_matches_pixel_vector():
    sample = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 9)
    cube_x, cube_y = pixel_matrix(sample)
    y = np.asarray(sample.y_flood)
    rows = []
    labels = []
    h, w = y.shape
    for i in range(h):
        for j in range(w):
            if y[i, j] == UNKNOWN:
                continue
            rows.append(pixel_vector(sample, i, j))
            labels.append(float(y[i, j]))
    assert cube_x.shape[1] == len(PIXEL_FEATURE_NAMES)
    np.testing.assert_allclose(cube_x, np.stack(rows))
    np.testing.assert_allclose(cube_y, np.asarray(labels))


def test_unknown_pixels_never_enter_metrics():
    sample = _observed_v2("kishoreganj", "2018-06-01T00:00:00Z", 11)
    sample.y_flood[0, :] = UNKNOWN
    pred = np.zeros_like(sample.y_flood, dtype=np.float64)
    y, p = valid_yp(sample, pred)
    assert int(np.sum(np.asarray(sample.y_flood) == UNKNOWN)) >= GRID_SIZE_V2
    assert y.size == int(np.sum(np.asarray(sample.y_flood) != UNKNOWN))
    scored = score_vectors(y, p)
    assert scored["n_valid_pixels"] == y.size
    yb = sample.y_binary()
    assert not np.any(np.isfinite(yb[np.asarray(sample.y_flood) == UNKNOWN]))


def test_frozen_split_enforced():
    samples = _corpus()
    expected = {
        "train_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "train"}),
        "validation_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "val"}),
        "test_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "test"}),
    }
    assert_frozen_splits(samples, expected)
    bad = dict(expected)
    bad["test_events"] = list(expected["train_events"])
    with pytest.raises(ValueError, match="frozen Track A split mismatch"):
        assert_frozen_splits(samples, bad)


def test_causal_forecast_rain_fails_leakage():
    sample = _observed_v2("kishoreganj", "2018-06-01T00:00:00Z", 12)
    assign_event_ids([sample])
    sample.split = "train"
    sample.x_precip_hourly_kind = ["FORECAST"] * len(sample.x_precip_hourly_kind)
    report = leakage_report([sample])
    assert report["pass"] is False
    assert report["future_horizons_used"] is False


def test_micro_versus_event_macro():
    y_big = np.ones(100)
    p_big = np.ones(100)
    y_small = np.ones(10)
    p_small = np.zeros(10)
    micro = score_vectors(np.concatenate([y_big, y_small]), np.concatenate([p_big, p_small]))
    e1 = score_vectors(y_big, p_big)
    e2 = score_vectors(y_small, p_small)
    macro = 0.5 * (e1["iou"] + e2["iou"])
    assert micro["iou"] > macro
    assert micro["n_valid_pixels"] == 110


def test_bootstrap_is_event_level():
    rows_a = [{"event_id": "e1", "iou": 0.8}, {"event_id": "e2", "iou": 0.2}, {"event_id": "e3", "iou": 0.5}]
    rows_b = [{"event_id": "e1", "iou": 0.4}, {"event_id": "e2", "iou": 0.4}, {"event_id": "e3", "iou": 0.4}]
    ci = event_bootstrap_ci(rows_a, rows_b, metric="iou", n_draws=200, seed=0)
    assert ci["n_events"] == 3
    assert ci["unit"] == "event"
    assert ci["ci95"][0] <= ci["mean"] <= ci["ci95"][1]


def test_reliability_perfect_is_acceptable():
    y = np.array([0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0] * 20)
    p = y.copy()
    diagram = reliability_diagram(y, p, n_bins=10)
    assert diagram["ece"] is not None
    assert diagram["ece"] < 0.05
    assert diagram["status"] == "ACCEPTABLE"


def test_ablation_feature_groups():
    rain = feature_indices(("rainfall",))
    terrain = feature_indices(("terrain",))
    river = feature_indices(("river_static",))
    all_idx = feature_indices(None)
    assert set(rain).isdisjoint(terrain)
    assert set(river).isdisjoint(rain)
    assert "persistence" not in [PIXEL_FEATURE_NAMES[i] for i in rain]
    assert len(all_idx) == len(PIXEL_FEATURE_NAMES)


def test_phase67_deterministic_synthetic(tmp_path: Path):
    samples = _corpus()
    expected = {
        "train_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "train"}),
        "validation_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "val"}),
        "test_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "test"}),
    }
    a = evaluate_phase67(
        samples=samples,
        expected_splits=expected,
        out_dir=tmp_path / "run1",
        write_docs=False,
        run_geographic=False,
        run_importance=False,
    )
    b = evaluate_phase67(
        samples=_corpus(),
        expected_splits=expected,
        out_dir=tmp_path / "run2",
        write_docs=False,
        run_geographic=False,
        run_importance=False,
    )
    iou_a = (((a.get("splits") or {}).get("test") or {}).get("persistence") or {}).get("micro") or {}
    iou_b = (((b.get("splits") or {}).get("test") or {}).get("persistence") or {}).get("micro") or {}
    assert iou_a.get("iou") == iou_b.get("iou")
    assert a["promoted_to_validated"] is False
    assert a["cnn_trained"] is False
    assert a["catalog_status"] == "NOT_VALIDATED"
    assert a["spatial_api"] == "UNAVAILABLE"
    assert (tmp_path / "run1" / "phase67_eval.json").exists()
    assert (tmp_path / "run1" / "PHASE_6_7_TRACK_A_BASELINES_REPORT.md").exists()
    assert freeze_identifier({"x": 1}) == freeze_identifier({"x": 1})


def test_phase67_does_not_promote_or_touch_solver():
    spatial = load_spatial_registry()
    aoi = load_registry()
    src = Path("src/floodlens/ml/spatial/phase67.py").read_text(encoding="utf-8")
    assert "mark_spatial_validated" not in src
    assert "fit_unet" not in src
    assert "TinyUNet" not in src
    assert public_spatial_status(spatial) != "VALIDATED"
    assert spatial.get("status") != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
    assert aoi["model_id"] == "FLOOD-OCCURRENCE-GBDT-v0.1"


def test_phase67_report_mentions_both_resolutions(tmp_path: Path):
    samples = _corpus()
    expected = {
        "train_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "train"}),
        "validation_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "val"}),
        "test_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "test"}),
    }
    report = evaluate_phase67(
        samples=samples,
        expected_splits=expected,
        out_dir=tmp_path,
        write_docs=False,
        run_geographic=True,
        run_ablations_flag=True,
        run_importance=True,
    )
    freeze = report["freeze"]
    assert freeze["label_resolution_m"] == 20.0
    assert freeze["working_grid"].startswith("64")
    assert "20 m" in freeze["note"]
    md = (tmp_path / "PHASE_6_7_TRACK_A_BASELINES_REPORT.md").read_text(encoding="utf-8")
    assert "20 m" in md
    assert "64" in md
    assert "NOT_VALIDATED" in md
    ablations = report.get("ablations") or {}
    assert "A_rainfall" in ablations
    assert "F_all" in ablations
    assert "persistence" not in ablations["A_rainfall"]["features"]
    geo = report.get("geographic") or {}
    assert "INSUFFICIENT DATA" in (geo.get("headline") or geo.get("status") or "") or geo.get("status") in {
        "INSUFFICIENT DATA",
        "RUNNABLE",
    }
    gates = (report.get("gates_67") or {}).get("gates") or {}
    for letter in "ABCDEFG":
        assert letter in gates
    assert report["gates_67"]["validated"] is False
    assert (report.get("splits") or {}).get("test", {}).get("persistence", {}).get("event_rows")
    calib = ((report.get("splits") or {}).get("val_test") or {}).get("calibration_pixel_gbdt") or {}
    assert calib.get("status") in {"NOT CALIBRATED", "PARTIALLY CALIBRATED", "ACCEPTABLE"}
