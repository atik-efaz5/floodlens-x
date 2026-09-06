"""Phase 6.5A dataset expansion: events, splits, gates, provenance. No training."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from floodlens.ml.spatial.builder import make_synthetic_sample, make_synthetic_sample_v2
from floodlens.ml.spatial.channel_audit import CONSTANT, SPATIAL, TEMPORAL_ONLY, audit_channels
from floodlens.ml.spatial.events import assign_event_ids, cluster_dates, coverage_summary, event_records, inventory
from floodlens.ml.spatial.gates import evaluate_gates_af, unknown_never_scored_as_dry
from floodlens.ml.spatial.labels import encode_binary
from floodlens.ml.spatial.leakage import check_spatial_sample
from floodlens.ml.spatial.provenance_spatial import provenance_complete, spatial_artifact_provenance
from floodlens.ml.spatial.schema import LABEL_OBSERVED, LABEL_SIMULATED, UNKNOWN
from floodlens.ml.spatial.splits import assign_event_level_splits, forbid_pixel_iid, write_split_manifests


def _observed_v2(city_id: str, issue_time: str, seed: int, split: str = "train"):
    sample = make_synthetic_sample_v2(city_id=city_id, issue_time=issue_time, seed=seed, split=split)
    sample.label_kind = LABEL_OBSERVED
    sample.extra["synthetic"] = False
    sample.extra["rainfall_status"] = "REANALYSIS"
    sample.x_precip_hourly_kind = ["REANALYSIS"] * len(sample.x_precip_hourly_kind)
    return sample


def test_synthetic_v2_is_simulated_not_observed():
    sample = make_synthetic_sample_v2(seed=1)
    assert sample.label_kind == LABEL_SIMULATED
    assert sample.extra.get("synthetic") is True
    assert sample.extra.get("rainfall_status") == "SIMULATED"


def test_event_deduplication_same_monsoon_is_one_event():
    a = _observed_v2("dhaka_ne", "2018-07-01T00:00:00Z", 1)
    b = _observed_v2("sunamganj", "2018-07-12T00:00:00Z", 2)
    c = _observed_v2("kishoreganj", "2018-07-20T00:00:00Z", 3)
    assign_event_ids([a, b, c])
    ids = {(s.extra or {}).get("event_id") for s in (a, b, c)}
    assert len(ids) == 1
    records = event_records([a, b, c])
    assert len(records) == 1
    row = records[0]
    for key in (
        "event_id",
        "event_start",
        "event_peak",
        "event_end",
        "geographic_region",
        "source",
        "source_version",
        "label_source",
        "provenance",
        "quality_status",
    ):
        assert key in row
    assert set(row["geographic_region"]) == {"dhaka_ne", "sunamganj", "kishoreganj"}


def test_event_gap_creates_independent_events():
    a = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 1)
    b = _observed_v2("sunamganj", "2018-08-20T00:00:00Z", 2)
    assign_event_ids([a, b])
    assert (a.extra or {}).get("event_id") != (b.extra or {}).get("event_id")


def test_split_isolation_no_event_in_two_splits(tmp_path):
    train = _observed_v2("dhaka_ne", "2017-06-01T00:00:00Z", 1)
    val = _observed_v2("kishoreganj", "2020-06-01T00:00:00Z", 2)
    test = _observed_v2("sunamganj", "2022-06-01T00:00:00Z", 3)
    samples = [train, val, test]
    payload = write_split_manifests(samples, tmp_path)
    train_ids = set(payload["train_events"])
    val_ids = set(payload["validation_events"])
    test_ids = set(payload["test_events"])
    assert not (train_ids & val_ids)
    assert not (train_ids & test_ids)
    assert not (val_ids & test_ids)
    for name in (
        "train_events.json",
        "validation_events.json",
        "test_events.json",
        "geographic_holdout.json",
        "temporal_holdout.json",
    ):
        assert (tmp_path / name).exists()


def test_event_level_split_prevents_year_boundary_leak():
    a = _observed_v2("dhaka_ne", "2018-12-15T00:00:00Z", 1)
    b = _observed_v2("sunamganj", "2019-01-10T00:00:00Z", 2)
    assign_event_level_splits([a, b])
    assert a.split == b.split == "train"


def test_forbid_pixel_iid():
    with pytest.raises(ValueError):
        forbid_pixel_iid("random_pixel")


def test_no_future_leakage():
    sample = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 4)
    assert not check_spatial_sample(sample)
    sample.x_precip_hourly_kind = ["FORECAST"] + list(sample.x_precip_hourly_kind[1:])
    assert any("forecast" in e.lower() or "future" in e.lower() for e in check_spatial_sample(sample))


def test_unknown_mask_preserved():
    sample = make_synthetic_sample_v2(seed=8)
    assert sample.y_flood[0, 0] == UNKNOWN
    yb = sample.y_binary()
    assert not np.isfinite(yb[0, 0])
    assert unknown_never_scored_as_dry([sample])
    frac = np.zeros((4, 4), dtype=np.float64)
    valid = np.zeros((4, 4), dtype=bool)
    valid[1, 1] = True
    frac[1, 1] = 0.9
    encoded = encode_binary(frac, valid, tau=0.25)
    assert encoded[0, 0] == UNKNOWN
    assert encoded[1, 1] == 1


def test_provenance_completeness():
    rec = spatial_artifact_provenance(
        data_status="REAL",
        source="copernicus-gfm-ensemble-flood-extent",
        dataset="ensemble_flood_extent",
        source_url="https://stac.eodc.eu/api/v1",
        source_version="GFM ensemble_flood_extent AS020M",
        checksum={"sha256_ends": "abc"},
        processing_version="phase6.5-gfm-spatial-v2",
        license_name="proprietary",
        attribution="Copernicus Emergency Management Service — Global Flood Monitoring (GFM).",
        label_kind=LABEL_OBSERVED,
    )
    assert provenance_complete(rec)
    sample = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 5)
    sample.extra["provenance"] = {
        "source": "copernicus-gfm-ensemble-flood-extent",
        "source_version": "GFM ensemble_flood_extent AS020M",
        "processing_version": "phase6.5-gfm-spatial-v2",
        "status": "REAL",
        "license": "proprietary",
        "attribution": "Copernicus GFM",
        "checksum": {"sha256_ends": "abc"},
    }
    assert provenance_complete(sample.extra["provenance"])
    assert not provenance_complete({})


def test_feature_channel_classification_spatial_vs_constant():
    spatial = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 6)
    audit = audit_channels([spatial])
    ch = audit["channels"]
    assert ch["dem"]["class"] == SPATIAL
    assert ch["slope"]["class"] == SPATIAL
    assert ch["river_distance"]["class"] == SPATIAL
    assert ch["precip_24h"]["class"] == SPATIAL
    assert ch["log1p_q"]["class"] in {TEMPORAL_ONLY, CONSTANT}
    v1 = make_synthetic_sample(seed=1)
    v1_audit = audit_channels([v1])
    assert v1_audit["channels"]["precip_24h"]["class"] in {TEMPORAL_ONLY, CONSTANT}


def test_no_synthetic_in_real_gate_a():
    fake = make_synthetic_sample_v2(seed=9)
    gates = evaluate_gates_af([fake])
    assert gates["gates"]["A"]["status"] == "FAIL"
    assert "synthetic_in_real" in gates["gates"]["A"]["reasons"] or "label_not_observed" in gates["gates"]["A"]["reasons"]
    realish = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 9)
    gates_ok = evaluate_gates_af([realish])
    assert "synthetic_in_real" not in gates_ok["gates"]["A"]["reasons"]


def test_gates_af_machine_readable_pass_fail_pending():
    aois = ("sunamganj", "kishoreganj", "dhaka_ne")
    stamps = [datetime(2016, 6, 1, tzinfo=timezone.utc) + timedelta(days=50 * i) for i in range(22)]
    samples = [
        _observed_v2(aois[i % 3], stamp.strftime("%Y-%m-%dT00:00:00Z"), 20 + i)
        for i, stamp in enumerate(stamps)
    ]
    assign_event_level_splits(samples)
    gates = evaluate_gates_af(samples, manifests_written=True)
    for letter in "ABCDEF":
        assert gates["gates"][letter]["status"] in {"PASS", "FAIL", "PENDING"}
        assert isinstance(gates["gates"][letter]["reasons"], list)
    assert gates["gates"]["A"]["status"] == "PASS"
    assert gates["gates"]["B"]["status"] == "PASS"
    assert gates["gates"]["C"]["status"] == "PASS"
    assert gates["gates"]["D"]["status"] == "PASS"
    assert gates["gates"]["E"]["status"] == "PASS"
    assert gates["gates"]["F"]["status"] == "PASS"
    assert gates["gates"]["G"]["status"] == "PENDING"
    assert gates["gates"]["H"]["status"] == "PENDING"
    assert gates["gates"]["I"]["status"] == "PASS"
    assert gates["gates"]["J"]["status"] == "FAIL"


def test_gate_d_fails_on_forecast_lookback():
    sample = _observed_v2("dhaka_ne", "2018-06-01T00:00:00Z", 11)
    sample.x_precip_hourly_kind = ["FORECAST"] * len(sample.x_precip_hourly_kind)
    gates = evaluate_gates_af([sample])
    assert gates["gates"]["D"]["status"] == "FAIL"


def test_deterministic_preprocessing_and_event_ids():
    dates = ["2018-07-01", "2018-07-10", "2019-01-01"]
    assert cluster_dates(dates) == cluster_dates(dates)
    frac = np.array([[0.0, 0.4], [0.1, 0.9]])
    valid = np.array([[True, True], [False, True]])
    a = encode_binary(frac, valid, tau=0.25)
    b = encode_binary(frac, valid, tau=0.25)
    assert np.array_equal(a, b)
    samples = [_observed_v2("sunamganj", "2018-06-01T00:00:00Z", 1) for _ in range(2)]
    assign_event_ids(samples)
    first = [s.extra["event_id"] for s in samples]
    assign_event_ids(samples)
    assert [s.extra["event_id"] for s in samples] == first


def test_coverage_summary_and_manifest_integrity(tmp_path):
    samples = [
        _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 1),
        _observed_v2("kishoreganj", "2018-06-01T00:00:00Z", 2),
        _observed_v2("dhaka_ne", "2020-06-01T00:00:00Z", 3),
    ]
    cov = coverage_summary(samples)
    assert cov["n_regions"] == 3
    for row in cov["regions"]:
        assert "valid_flood_pixels" in row
        assert "valid_dry_pixels" in row
        assert "unknown_pixels" in row
        assert "dates_covered" in row
    payload = write_split_manifests(samples, tmp_path)
    splits = json.loads((tmp_path / "splits.json").read_text())
    assert splits["pixel_iid"] is False
    assert set(payload["train_events"]).isdisjoint(payload["test_events"])


def test_phase65a_never_trains():
    root = Path(__file__).resolve().parents[1]
    src = (root / "src/floodlens/ml/spatial/phase65a.py").read_text()
    assert "fit_unet(" not in src
    assert "fit_spatial_baselines(" not in src
    assert "mark_spatial_validated(" not in src
    assert "evaluate_phase6(" not in src
    script = (root / "scripts/phase65a_expand.py").read_text()
    assert "fit_unet(" not in script


def test_v1_dedupe_still_rejects_neighbor_tile():
    from floodlens.ml.spatial.acquire_gfm import _dedupe_one_per_day
    from floodlens.ml.spatial.equi7 import TILE_CATALOG, TILE_ID

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
    kept_v2 = _dedupe_one_per_day(feats, tiles=tuple(TILE_CATALOG.keys()))
    assert len(kept_v2) == 2


def test_inventory_counts_unknown_separately():
    sample = _observed_v2("sunamganj", "2018-06-01T00:00:00Z", 12)
    inv = inventory([sample])
    assert inv["pixels"]["unknown"] >= 1
    assert inv["pixels"]["unknown_fraction"] is not None
