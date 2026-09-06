"""Phase 6.8A Target B observational diagnostic. No training. No invented horizons."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.builder import make_synthetic_sample_v2
from floodlens.ml.spatial.events import assign_event_ids
from floodlens.ml.spatial.phase68a import (
    CLASS_NEWLY_FLOODED,
    CLASS_PERSISTENT_DRY,
    CLASS_PERSISTENT_FLOOD,
    CLASS_RECEDING,
    CLASS_UNKNOWN,
    IN_HORIZON_KIND,
    PRE_T0_KIND,
    adjacent_pairs,
    audit_rainfall_interval,
    build_lattice_index,
    delta_t_hours,
    evaluate_phase68a,
    event_level_summaries,
    hours_in_open_closed,
    pair_statistics,
    transition_map,
)
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import LABEL_OBSERVED, UNKNOWN
from floodlens.ml.spatial.splits import assign_event_level_splits


def _stamp(day: str, hour: int = 12) -> str:
    return f"{day}T{hour:02d}:00:00Z"


def _sample(city_id: str, valid_at: str, seed: int, split: str = "train", event_id: str | None = None):
    issue = (datetime.fromisoformat(valid_at.replace("Z", "+00:00")) - timedelta(hours=192)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sample = make_synthetic_sample_v2(city_id=city_id, issue_time=issue, seed=seed, split=split)
    sample.label_kind = LABEL_OBSERVED
    sample.valid_at = valid_at
    sample.dataset_version = "phase6.5-gfm-spatial-v2.1"
    sample.extra["synthetic"] = False
    sample.extra["rainfall_status"] = "REANALYSIS"
    if event_id:
        sample.extra["event_id"] = event_id
        sample.extra["flood_mechanism"] = "haor_monsoon_inundation"
    return sample


def _hourly(start: str, n: int, value: float = 1.0, skip: set[int] | None = None):
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    times = []
    vals = []
    skip = skip or set()
    for i in range(n):
        stamp = (t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00")
        times.append(stamp)
        vals.append(None if i in skip else value)
    return times, vals


def _lattice(aoi: str, start: str, n: int, value: float = 1.0, skip: set[int] | None = None):
    times, vals = _hourly(start, n, value=value, skip=skip)
    return {
        "source": "test-lattice",
        "kind": "REANALYSIS",
        "start": start[:10],
        "end": (datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(hours=n - 1)).strftime("%Y-%m-%d"),
        "aois": {aoi: {"points": [{"lat": 24.8, "lon": 91.2, "time": times, "precipitation_mm": vals}]}},
    }


def test_adjacent_scene_pairing_not_skip_or_cross_aoi():
    a = _sample("sunamganj", _stamp("2018-06-01"), 1, event_id="evt:2018-06-01")
    b = _sample("sunamganj", _stamp("2018-06-03"), 2, event_id="evt:2018-06-01")
    c = _sample("sunamganj", _stamp("2018-06-13"), 3, event_id="evt:2018-06-01")
    other = _sample("sylhet", _stamp("2018-06-03"), 4, event_id="evt:2018-06-01")
    pairs = adjacent_pairs([a, c, b, other])
    keys = {(p[0].scene_id, p[1].scene_id) for p in pairs}
    assert (a.scene_id, b.scene_id) in keys
    assert (b.scene_id, c.scene_id) in keys
    assert (a.scene_id, c.scene_id) not in keys
    assert all(p[0].city_id == p[1].city_id for p in pairs)
    assert len(pairs) == 2


def test_same_event_enforced_despite_close_dates():
    a = _sample("kishoreganj", _stamp("2018-06-01"), 1, event_id="evt:2018-06-01")
    b = _sample("kishoreganj", _stamp("2018-06-03"), 2, event_id="evt:2018-08-20")
    pairs = adjacent_pairs([a, b])
    assert pairs == []


def test_transition_classification_and_unknown_preserved():
    y0 = np.array([[0, 1, 255], [0, 1, 0]], dtype=np.uint8)
    y1 = np.array([[1, 1, 0], [0, 0, 255]], dtype=np.uint8)
    trans = transition_map(y0, y1)
    assert trans[0, 0] == CLASS_NEWLY_FLOODED
    assert trans[0, 1] == CLASS_PERSISTENT_FLOOD
    assert trans[1, 0] == CLASS_PERSISTENT_DRY
    assert trans[1, 1] == CLASS_RECEDING
    assert trans[0, 2] == CLASS_UNKNOWN
    assert trans[1, 2] == CLASS_UNKNOWN
    assert y0[0, 2] == UNKNOWN
    assert y1[1, 2] == UNKNOWN


def test_unknown_never_inferred_as_dry():
    y0 = np.full((4, 4), UNKNOWN, dtype=np.uint8)
    y1 = np.zeros((4, 4), dtype=np.uint8)
    trans = transition_map(y0, y1)
    assert np.all(trans == CLASS_UNKNOWN)
    assert not np.any(trans == CLASS_PERSISTENT_DRY)


def test_delta_t_is_measured_interval_not_product_hour():
    a = _sample("sunamganj", "2018-06-01T12:00:00Z", 1, event_id="e")
    b = _sample("sunamganj", "2018-06-09T12:00:00Z", 2, event_id="e")
    dt = delta_t_hours(a.valid_at, b.valid_at)
    assert abs(dt - 192.0) < 1e-6
    hours = hours_in_open_closed(a.valid_at, b.valid_at)
    assert len(hours) == 192
    row = pair_statistics(a, b, lattice=build_lattice_index(_lattice("sunamganj", "2018-05-01T00:00:00Z", 24)))
    assert row["horizon_relabeled"] is False
    assert row["delta_t_bucket"] == "8-12 days"
    assert row["t0"] == a.valid_at
    assert row["t1"] == b.valid_at


def test_rainfall_gap_detection_no_fill():
    t0 = "2018-06-01T12:00:00Z"
    t1 = "2018-06-01T18:00:00Z"
    complete = build_lattice_index(_lattice("sunamganj", "2018-06-01T00:00:00Z", 48))
    missing = build_lattice_index(_lattice("sunamganj", "2018-06-01T00:00:00Z", 48, skip={14, 15, 16}))
    ok = audit_rainfall_interval("sunamganj", t0, t1, complete, window="in_horizon")
    gap = audit_rainfall_interval("sunamganj", t0, t1, missing, window="in_horizon")
    none = audit_rainfall_interval("sunamganj", t0, t1, None, window="in_horizon")
    assert ok["forcing_class"] == "FORCING_COMPLETE"
    assert ok["filled"] is False
    assert ok["causal_feature"] is False
    assert gap["forcing_class"] == "FORCING_PARTIAL"
    assert gap["n_hours_missing"] == 3
    assert gap["longest_missing_gap_hours"] == 3
    assert gap["filled"] is False
    assert none["forcing_class"] == "FORCING_MISSING"
    assert none["precip_sum_kind"] == IN_HORIZON_KIND


def test_causal_feature_separation_and_no_future_leakage():
    a = _sample("sunamganj", "2018-06-01T12:00:00Z", 1, event_id="e")
    b = _sample("sunamganj", "2018-06-02T12:00:00Z", 2, event_id="e")
    idx = build_lattice_index(_lattice("sunamganj", "2018-05-29T00:00:00Z", 120, value=4.0))
    row = pair_statistics(a, b, idx)
    feats = row["features"]
    assert feats["rainfall_during_horizon"]["kind"] == IN_HORIZON_KIND
    assert feats["rainfall_during_horizon"]["causal_feature"] is False
    assert feats["rainfall_during_horizon"]["forecast_available"] is False
    assert feats["rainfall_history_before_t0"]["kind"] == PRE_T0_KIND
    assert feats["rainfall_history_before_t0"]["causal_feature"] is True
    assert feats["prior_flood_map"]["causal_feature"] is True
    assert feats["later_flood_map"]["causal_feature"] is False
    assert row["in_horizon_as_causal_feature"] is False
    assert row["later_map_as_feature"] is False
    assert row["gates"]["B4_no_target_leakage"] is True
    assert (row["rainfall_in_horizon"] or {}).get("causal_feature") is False


def test_event_level_aggregation_does_not_count_pairs_as_events():
    a1 = _sample("sunamganj", _stamp("2018-06-01"), 1, event_id="evt:2018-06-01")
    a2 = _sample("sunamganj", _stamp("2018-06-03"), 2, event_id="evt:2018-06-01")
    a3 = _sample("sunamganj", _stamp("2018-06-13"), 3, event_id="evt:2018-06-01")
    b1 = _sample("netrokona", _stamp("2020-07-01"), 4, split="val", event_id="evt:2020-07-01")
    b2 = _sample("netrokona", _stamp("2020-07-12"), 5, split="val", event_id="evt:2020-07-01")
    samples = [a1, a2, a3, b1, b2]
    pairs = adjacent_pairs(samples)
    rows = [pair_statistics(x, y) for x, y in pairs]
    summary = event_level_summaries(rows, samples)
    assert len(pairs) == 3
    assert len(summary) == 2
    by_id = {r["event_id"]: r for r in summary}
    assert by_id["evt:2018-06-01"]["n_pairs"] == 2
    assert by_id["evt:2018-06-01"]["independent_event"] is True
    assert by_id["evt:2020-07-01"]["n_pairs"] == 1


def _corpus():
    specs = [
        ("kishoreganj", "2017-06-01", 1, "train"),
        ("kishoreganj", "2017-06-09", 2, "train"),
        ("dhaka_sw", "2017-08-20", 3, "train"),
        ("dhaka_sw", "2017-08-28", 4, "train"),
        ("kishoreganj", "2018-06-15", 5, "train"),
        ("kishoreganj", "2018-06-18", 6, "train"),
        ("dhaka_ne", "2018-08-20", 7, "train"),
        ("dhaka_ne", "2018-08-28", 8, "train"),
        ("sunamganj", "2020-06-01", 9, "val"),
        ("sunamganj", "2020-06-12", 10, "val"),
        ("netrokona", "2021-06-02", 11, "val"),
        ("netrokona", "2021-06-14", 12, "val"),
        ("sylhet", "2022-05-16", 13, "test"),
        ("sylhet", "2022-05-18", 14, "test"),
        ("dhaka_se", "2023-06-16", 15, "test"),
        ("dhaka_se", "2023-06-28", 16, "test"),
    ]
    samples = []
    for city, day, seed, split in specs:
        samples.append(_sample(city, _stamp(day), seed, split=split))
    assign_event_ids(samples)
    assign_event_level_splits(samples)
    return samples


def test_phase68a_deterministic_and_writes_artifacts(tmp_path: Path):
    samples = _corpus()
    expected = {
        "train_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "train"}),
        "validation_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "val"}),
        "test_events": sorted({(s.extra or {}).get("event_id") for s in samples if s.split == "test"}),
    }
    lattice = {
        "kind": "REANALYSIS",
        "start": "2017-01-01",
        "end": "2023-12-31",
        "aois": {},
    }
    # coverage-only empty aois → completeness from window; still no fill
    a = evaluate_phase68a(
        samples=samples,
        expected_splits=expected,
        lattice=lattice,
        out_dir=tmp_path / "run1",
        write_docs=False,
        lock_splits=False,
    )
    b = evaluate_phase68a(
        samples=_corpus(),
        expected_splits=expected,
        lattice=lattice,
        out_dir=tmp_path / "run2",
        write_docs=False,
        lock_splits=False,
    )
    assert a["counts"]["n_observed_transition_pairs"] == b["counts"]["n_observed_transition_pairs"]
    assert a["counts"]["n_observed_transition_pairs"] == 8
    assert a["counts"]["n_independent_events"] == b["counts"]["n_independent_events"]
    assert a["promoted_to_validated"] is False
    assert a["cnn_trained"] is False
    assert a["catalog_status"] == "NOT_VALIDATED"
    assert a["spatial_api"] == "UNAVAILABLE"
    assert a["model_training"] == "NOT AUTHORIZED"
    assert a["forcing"]["forecast_available_in_horizon"] is False
    assert a["forcing"]["filled"] is False
    assert (tmp_path / "run1" / "transition_pairs.json").exists()
    assert (tmp_path / "run1" / "transition_statistics.json").exists()
    assert (tmp_path / "run1" / "rainfall_completeness.json").exists()
    assert (tmp_path / "run1" / "delta_t_distribution.json").exists()
    assert (tmp_path / "run1" / "event_summaries.json").exists()
    assert (tmp_path / "run1" / "gate_results.json").exists()
    md = (tmp_path / "run1" / "PHASE_6_8A_TARGET_B_DIAGNOSTIC_REPORT.md").read_text(encoding="utf-8")
    assert "TARGET B" in md
    assert "NOT_VALIDATED" in md
    assert "measured" in md.lower() or "delta_t" in md.lower() or "Δt" in md
    for letter in ("B1", "B2", "B3", "B4", "B5", "B6", "B7"):
        assert letter in ((a.get("gates") or {}).get("gates") or {})


def test_phase68a_does_not_train_or_promote():
    spatial = load_spatial_registry()
    aoi = load_registry()
    src = Path("src/floodlens/ml/spatial/phase68a.py").read_text(encoding="utf-8")
    script = Path("scripts/phase68a_target_b.py").read_text(encoding="utf-8")
    for blob in (src, script):
        assert "fit_unet" not in blob
        assert "TinyUNet" not in blob
        assert "BoostingModel" not in blob
        assert "LogisticModel" not in blob
        assert "mark_spatial_validated" not in blob
        assert "ConvLSTM" not in blob
    assert public_spatial_status(spatial) != "VALIDATED"
    assert spatial.get("status") != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
    assert aoi["model_id"] == "FLOOD-OCCURRENCE-GBDT-v0.1"


def test_transition_shape_mismatch_fails():
    y0 = np.zeros((2, 2), dtype=np.uint8)
    y1 = np.zeros((3, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        transition_map(y0, y1)
