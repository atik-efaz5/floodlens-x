"""Phase 6.5B independent-event expansion. No training."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from floodlens.ml.spatial.acquire_gfm import _dedupe_one_per_day, _dedupe_orbits
from floodlens.ml.spatial.acquire_gfm import covering_orbit_score as gfm_orbit_score
from floodlens.ml.spatial.builder import make_synthetic_sample_v2
from floodlens.ml.spatial.equi7 import TILE_ID
from floodlens.ml.spatial.event_expansion import (
    SOURCE_COMPATIBILITY,
    TARGET_CLUSTERS,
    build_candidate_inventory,
    covering_orbit_score,
    detect_duplicate_scenes,
    independent_from_existing,
    intervals_overlap,
    lattice_covers,
)
from floodlens.ml.spatial.events import EVENT_GAP_DAYS, assign_event_ids, cluster_dates, event_records
from floodlens.ml.spatial.gates import (
    GATE0_MIN_EVENTS,
    event_independence_report,
    evaluate_gates_af,
    unknown_never_scored_as_dry,
)
from floodlens.ml.spatial.schema import LABEL_OBSERVED, LABEL_SIMULATED, UNKNOWN
from floodlens.ml.spatial.splits import assign_event_level_splits, write_split_manifests


def _observed_v2(city_id: str, issue_time: str, seed: int, split: str = "train"):
    sample = make_synthetic_sample_v2(city_id=city_id, issue_time=issue_time, seed=seed, split=split)
    sample.label_kind = LABEL_OBSERVED
    sample.extra["synthetic"] = False
    sample.extra["rainfall_status"] = "REANALYSIS"
    sample.x_precip_hourly_kind = ["REANALYSIS"] * len(sample.x_precip_hourly_kind)
    return sample


def test_event_independence_45_day_gap():
    assert intervals_overlap("2017-04-12", "2017-05-20", "2017-07-31", "2017-08-25") is False
    assert intervals_overlap("2018-06-01", "2018-07-15", "2018-07-20", "2018-08-10") is True
    ok, why = independent_from_existing("2017-07-31", "2017-08-25")
    assert ok is True
    assert why == ""
    ok2, why2 = independent_from_existing("2018-06-01", "2018-07-10")
    assert ok2 is False
    assert "evt:2018-06-06" in why2


def test_candidate_deduplication_same_pulse():
    dates = ["2017-07-31", "2017-08-12", "2017-08-24"]
    groups = cluster_dates(dates, gap_days=EVENT_GAP_DAYS)
    assert len(groups) == 1


def test_cross_region_same_event():
    a = _observed_v2("sunamganj", "2024-07-10T00:00:00Z", 1)
    b = _observed_v2("dhaka_sw", "2024-07-22T00:00:00Z", 2)
    c = _observed_v2("kishoreganj", "2024-08-01T00:00:00Z", 3)
    assign_event_ids([a, b, c])
    ids = {(s.extra or {}).get("event_id") for s in (a, b, c)}
    assert len(ids) == 1
    rec = event_records([a, b, c])[0]
    for key in (
        "event_id",
        "event_start",
        "event_peak",
        "event_end",
        "region_ids",
        "source_ids",
        "meteorological_signature",
        "hydrological_signature",
        "deduplication_key",
        "quality_status",
    ):
        assert key in rec
    assert set(rec["region_ids"]) == {"sunamganj", "dhaka_sw", "kishoreganj"}


def test_downstream_spread_is_one_event():
    a = _observed_v2("netrokona", "2020-06-10T00:00:00Z", 1)
    b = _observed_v2("kishoreganj", "2020-07-01T00:00:00Z", 2)
    c = _observed_v2("dhaka_sw", "2020-07-20T00:00:00Z", 3)
    assign_event_ids([a, b, c])
    assert len({(s.extra or {}).get("event_id") for s in (a, b, c)}) == 1


def test_duplicate_scene_detection():
    index = {"scenes": [{"id": "a"}, {"id": "b"}, {"id": "a"}]}
    assert detect_duplicate_scenes(index) == ["a"]
    assert detect_duplicate_scenes({"scenes": [{"id": "a"}, {"id": "b"}]}) == []


def test_covering_orbit_prefers_1204_over_1156():
    assert gfm_orbit_score("2017-08-01T12:04:36Z") < gfm_orbit_score("2017-08-01T11:56:12Z")
    assert covering_orbit_score("2017-08-01T23:55:01Z") < covering_orbit_score("2017-08-01T23:47:01Z")
    feats = [
        {
            "id": "ENSEMBLE_FLOOD_20170801T115612_VV_AS020M_E039N021T3",
            "properties": {"datetime": "2017-08-01T11:56:12Z"},
            "assets": {"ensemble_flood_extent": {"href": "https://example/E039N021T3.tif"}},
        },
        {
            "id": "ENSEMBLE_FLOOD_20170801T120436_VV_AS020M_E039N021T3",
            "properties": {"datetime": "2017-08-01T12:04:36Z"},
            "assets": {"ensemble_flood_extent": {"href": "https://example/E039N021T3.tif"}},
        },
    ]
    kept = _dedupe_orbits(feats, tiles=(TILE_ID,))
    cover = [k for k in kept if "120436" in k["id"] or k["datetime"].startswith("2017-08-01T12:04")]
    assert cover


def test_unknown_mask_never_becomes_dry():
    sample = make_synthetic_sample_v2(seed=3)
    assert sample.y_flood[0, 0] == UNKNOWN
    assert not np.isfinite(sample.y_binary()[0, 0])
    assert unknown_never_scored_as_dry([sample])


def test_provenance_and_reproducibility_fields():
    a = _observed_v2("sunamganj", "2017-08-01T00:00:00Z", 4)
    rec = event_records([a])[0]
    assert rec["source"] == "copernicus-gfm-ensemble-flood-extent"
    assert rec["deduplication_key"]
    assert rec["source_ids"]


def test_event_split_isolation(tmp_path):
    samples = [
        _observed_v2("dhaka_ne", "2017-05-01T00:00:00Z", 1),
        _observed_v2("kishoreganj", "2020-06-01T00:00:00Z", 2),
        _observed_v2("sunamganj", "2022-06-01T00:00:00Z", 3),
    ]
    payload = write_split_manifests(samples, tmp_path)
    assert set(payload["train_events"]).isdisjoint(payload["validation_events"])
    assert set(payload["train_events"]).isdisjoint(payload["test_events"])
    assert set(payload["validation_events"]).isdisjoint(payload["test_events"])
    splits = json.loads((tmp_path / "splits.json").read_text())
    assert splits["pixel_iid"] is False


def test_gate_b_extras_without_changing_official_floor():
    samples = [
        _observed_v2("sunamganj", "2016-06-30T00:00:00Z", 1),
        _observed_v2("kishoreganj", "2018-06-06T00:00:00Z", 2),
    ]
    assign_event_level_splits(samples)
    report = event_independence_report(samples)
    assert GATE0_MIN_EVENTS == 20
    assert report["n_independent_events"] == 2
    assert report["official_status"] == "FAIL"
    assert report["research_recommendation"] == "FAIL"
    assert "train_events" in report
    assert "events_per_year" in report
    assert "duplicate_event_detection" in report
    gates = evaluate_gates_af(samples)
    assert gates["gates"]["B"]["status"] == "FAIL"
    assert gates["gates"]["B"]["research_recommendation"] == "FAIL"
    assert gates["gates"]["B"]["n_independent_events"] == 2


def test_gate_f_reports_events_not_only_region_count():
    samples = [
        _observed_v2("sunamganj", "2016-06-30T00:00:00Z", 1),
        _observed_v2("kishoreganj", "2018-06-06T00:00:00Z", 2),
        _observed_v2("dhaka_sw", "2020-06-07T00:00:00Z", 3),
    ]
    assign_event_level_splits(samples)
    gates = evaluate_gates_af(samples)
    assert gates["gates"]["F"]["status"] == "PASS"
    assert "events_per_region" in gates["gates"]["F"]
    assert "years_per_region" in gates["gates"]["F"]
    assert "events_per_mechanism" in gates["gates"]["F"]
    assert gates["gates"]["F"]["valid_regions"] >= 3


def test_no_synthetic_enters_real_gate_a():
    fake = make_synthetic_sample_v2(seed=9)
    assert fake.label_kind == LABEL_SIMULATED
    gates = evaluate_gates_af([fake])
    assert gates["gates"]["A"]["status"] == "FAIL"


def test_candidate_inventory_rejected_has_reason():
    index = {
        "scenes": [
            {
                "id": "s1",
                "datetime": "2018-06-06T12:04:00Z",
                "tile": TILE_ID,
                "cities": {
                    "sunamganj": {"n_flood": 10, "n_dry": 100, "n_unknown": 5, "valid_frac": 0.9},
                },
            }
        ]
    }
    acquire_log = {
        "clusters": [
            {
                **TARGET_CLUSTERS[0],
                "n_stac_features": 0,
                "stac_empty": True,
                "candidates": [],
                "attempts": [],
            }
        ]
    }
    rows = build_candidate_inventory(index, acquire_log)
    rejected = [r for r in rows if not r.get("accepted")]
    assert rejected
    assert all(r.get("rejection_reason") for r in rejected)
    accepted = [r for r in rows if r.get("accepted")]
    assert any(r["event_id"].startswith("evt:") for r in accepted)


def test_lattice_window_excludes_2015_and_2025():
    assert lattice_covers("2017-08-01", "2017-08-20")
    assert not lattice_covers("2015-07-01", "2015-08-01")
    assert not lattice_covers("2025-06-20", "2025-08-01")
    assert not lattice_covers("2016-01-10", "2016-02-05")


def test_source_compatibility_decisions_are_exclusive():
    allowed = {"A", "B", "C", "D"}
    for name, row in SOURCE_COMPATIBILITY.items():
        assert row["decision"] in allowed, name
    assert SOURCE_COMPATIBILITY["copernicus-gfm-ensemble-flood-extent"]["decision"] == "A"
    assert SOURCE_COMPATIBILITY["opera-dswx-s1"]["decision"] == "D"
    assert SOURCE_COMPATIBILITY["global-flood-database"]["decision"] == "C"


def test_v1_dedupe_still_rejects_neighbor_by_default():
    feats = [
        {
            "id": "ENSEMBLE_FLOOD_20160628T120505_VV_AS020M_E039N024T3",
            "properties": {"datetime": "2016-06-28T12:05:05Z"},
            "assets": {"ensemble_flood_extent": {"href": "https://example/E039N024T3.tif"}},
        },
        {
            "id": "ENSEMBLE_FLOOD_20180113T120433_VV_AS020M_E039N021T3",
            "properties": {"datetime": "2018-01-13T12:04:33Z"},
            "assets": {"ensemble_flood_extent": {"href": "https://example/E039N021T3.tif"}},
        },
    ]
    kept = _dedupe_one_per_day(feats)
    assert len(kept) == 1
    assert TILE_ID in kept[0]["id"]


def test_phase65b_never_trains():
    root = Path(__file__).resolve().parents[1]
    src = (root / "src/floodlens/ml/spatial/phase65b.py").read_text()
    assert "fit_unet(" not in src
    assert "fit_spatial_baselines(" not in src
    assert "mark_spatial_validated(" not in src
    assert "evaluate_phase6(" not in src
    script = (root / "scripts/phase65b_expand.py").read_text()
    assert "fit_unet(" not in script


def test_official_gate_b_floor_unchanged():
    stamps = [datetime(2016, 6, 1, tzinfo=timezone.utc) + timedelta(days=50 * i) for i in range(19)]
    samples = [_observed_v2("sunamganj", s.strftime("%Y-%m-%dT00:00:00Z"), i) for i, s in enumerate(stamps)]
    assign_event_level_splits(samples)
    gates = evaluate_gates_af(samples)
    assert gates["gates"]["B"]["status"] == "FAIL"
    assert gates["gates"]["B"]["research_recommendation"] == "FAIL"
    stamps30 = [datetime(2016, 6, 1, tzinfo=timezone.utc) + timedelta(days=50 * i) for i in range(30)]
    many = [_observed_v2("sunamganj", s.strftime("%Y-%m-%dT00:00:00Z"), i) for i, s in enumerate(stamps30)]
    assign_event_level_splits(many)
    gates30 = evaluate_gates_af(many)
    assert gates30["gates"]["B"]["status"] == "PASS"
    assert gates30["gates"]["B"]["research_recommendation"] == "PASS"
