"""Phase 6.5C multi-source event matching. No training. No label merge."""

from __future__ import annotations

from pathlib import Path

from floodlens.ml.spatial.events import EVENT_GAP_DAYS
from floodlens.ml.spatial.multisource import (
    COMPATIBILITY_PAIRS,
    FAMILY_GFD,
    FAMILY_GFM,
    REGISTRY_VERSION,
    SOURCES,
    centroid_in_bangladesh,
    cluster_source_rows,
    evaluate_phase65c,
    match_windows,
    quality_reject_secondary,
    summarize_registry,
)


def test_45_day_rule_unchanged():
    assert EVENT_GAP_DAYS == 45
    assert match_windows("2017-04-12", "2017-05-20", "2017-07-31", "2017-08-25") is False
    assert match_windows("2017-07-31", "2017-08-24", "2017-08-10", "2017-08-26") is True


def test_cross_source_same_monsoon_is_one_event():
    assert match_windows("2017-07-31", "2017-08-24", "2017-08-10", "2017-08-26") is True


def test_duplicate_dfo_gfd_same_dfo_id_clusters():
    rows = [
        {"event_start": "2014-08-20", "event_end": "2014-09-08", "source_event_id": "gfd:dfo:4178"},
        {"event_start": "2014-08-20", "event_end": "2014-09-08", "source_event_id": "dfo:4178"},
    ]
    groups = cluster_source_rows(rows)
    assert len(groups) == 1


def test_observation_families_stay_separate():
    assert SOURCES["copernicus-gfm-ensemble-flood-extent"]["family"] == FAMILY_GFM
    assert SOURCES["global-flood-database"]["family"] == FAMILY_GFD
    assert SOURCES["giezendanner-bangladesh-inundation-history"]["label_kind"] == "DERIVED"
    assert COMPATIBILITY_PAIRS["gfm__giezendanner"]["decision"] == "D"
    assert COMPATIBILITY_PAIRS["gfm__gfd"]["decision"] == "C"
    assert "A" != COMPATIBILITY_PAIRS["gfm__gfd"]["decision"]


def test_no_pair_is_unified_training_label():
    for key, row in COMPATIBILITY_PAIRS.items():
        assert row["decision"] in {"A", "B", "C", "D"}
        if key != "unused":
            assert row["decision"] != "A", key


def test_resolution_metadata_not_upsampled():
    assert SOURCES["copernicus-gfm-ensemble-flood-extent"]["spatial_resolution_m"] == 20
    assert SOURCES["giezendanner-bangladesh-inundation-history"]["spatial_resolution_m"] == 500
    assert SOURCES["global-flood-database"]["spatial_resolution_m"] == 250


def test_unknown_mask_policy_preserved_on_gfm_source():
    assert "255" in SOURCES["copernicus-gfm-ensemble-flood-extent"]["unknown"]
    assert "never recoded" in SOURCES["copernicus-gfm-ensemble-flood-extent"]["unknown"]


def test_licensing_nc_not_product_safe():
    assert "NC" in SOURCES["global-flood-database"]["license"]
    assert SOURCES["global-flood-database"]["commercial_ok"] is False


def test_gfd_population_not_a_label():
    assert "population exposure" in SOURCES["global-flood-database"]["do_not_use"]


def test_quality_rejects_nigeria_and_tiny_and_outside_centroid():
    ok, _, why = quality_reject_secondary(
        {"event_start": "2000-09-20", "event_end": "2000-09-21", "country": "Nigeria • Bangladesh", "area_km2": 7725, "dead": 0, "displaced": 0}
    )
    assert ok is False
    assert why == "country_not_bangladesh_useful"
    ok2, _, why2 = quality_reject_secondary(
        {"event_start": "2014-07-13", "event_end": "2014-07-14", "country": "Bangladesh", "area_km2": 218, "dead": 0, "displaced": 30000}
    )
    assert ok2 is True  # displaced 30k keeps it
    ok3, _, why3 = quality_reject_secondary(
        {"event_start": "2014-07-13", "event_end": "2014-07-14", "country": "Bangladesh", "area_km2": 218, "dead": 0, "displaced": 0}
    )
    assert ok3 is False
    assert why3 == "tiny_or_unconfirmed_extent"
    assert centroid_in_bangladesh(27.46, 95.60) is False
    ok4, _, why4 = quality_reject_secondary(
        {
            "event_start": "2016-04-20",
            "event_end": "2016-05-01",
            "country": "India • Bangladesh",
            "area_km2": 70518,
            "dead": 18,
            "displaced": 3000,
            "lat": 27.46,
            "lon": 95.60,
        }
    )
    assert ok4 is False
    assert why4 == "centroid_outside_bangladesh"


def test_event_count_does_not_add_datasets():
    rows = [
        {
            "event_id": "evt:2017-07-31",
            "source": "copernicus-gfm-ensemble-flood-extent",
            "cube_eligible": True,
            "accepted": True,
            "year": 2017,
            "flood_mechanism": "monsoon_riverine",
        },
        {
            "event_id": "evt:2017-07-31",
            "source": "global-flood-database",
            "accepted": True,
            "independent_from_gfm": False,
            "year": 2017,
            "flood_mechanism": "monsoon_riverine",
        },
        {
            "event_id": "evt:2014-08-20",
            "source": "dartmouth-flood-observatory",
            "accepted": True,
            "independent_from_gfm": True,
            "year": 2014,
            "flood_mechanism": "monsoon_riverine",
        },
    ]
    s = summarize_registry(rows)
    assert s["gfm_only"] == 1
    assert s["additional_unique_events"] == 1
    assert s["combined_independent_events"] == 2
    assert s["official_gate_b"] == "FAIL"


def test_phase65c_never_trains_and_never_merges():
    root = Path(__file__).resolve().parents[1]
    src = (root / "src/floodlens/ml/spatial/multisource.py").read_text()
    assert "fit_unet(" not in src
    assert "mark_spatial_validated(" not in src
    script = (root / "scripts/phase65c_multisource.py").read_text()
    assert "fit_unet(" not in script
    assert REGISTRY_VERSION == "phase6.5-multisource-event-v1"


def test_evaluate_writes_registry(tmp_path, monkeypatch):
    import json

    import floodlens.ml.spatial.multisource as ms

    monkeypatch.setattr(ms, "REGISTRY_CSV", tmp_path / "multisource_event_registry.csv")
    monkeypatch.setattr(ms, "REGISTRY_JSON", tmp_path / "multisource_event_registry.json")
    monkeypatch.setattr(ms, "COMPAT_JSON", tmp_path / "source_compatibility_matrix.json")
    monkeypatch.setattr(ms, "COMPAT_CSV", tmp_path / "source_compatibility_matrix.csv")
    monkeypatch.setattr(ms, "PHASE65C_EVAL", tmp_path / "phase65c_eval.json")
    report = evaluate_phase65c()
    assert (tmp_path / "multisource_event_registry.csv").exists()
    assert report["catalog_status"] == "NOT_VALIDATED"
    assert report["spatial_ai"] == "NOT_VALIDATED"
    assert report["summary"]["gfm_only"] == 15
    assert report["summary"]["official_gate_b"] == "FAIL"
    assert report["does_not_overwrite"] == "phase6.5-gfm-spatial-v2.1"
    rows = json.loads((tmp_path / "multisource_event_registry.json").read_text())
    fam = {r["observation_family"] for r in rows if r.get("accepted")}
    assert FAMILY_GFM in fam
    gfd_pixels = [r for r in rows if r["source"] == "global-flood-database" and r.get("accepted")]
    assert all(r.get("cube_eligible") is False for r in gfd_pixels)
    assert all(r.get("label_kind") != "SIMULATED" for r in rows if r.get("accepted"))
