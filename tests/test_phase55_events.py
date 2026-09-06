"""Phase 5.5 event grouping, nodata, holdout leakage, eval helpers."""

from __future__ import annotations

import numpy as np

from floodlens.ml.spatial.builder import make_synthetic_sample
from floodlens.ml.spatial.events import (
    assign_event_ids,
    cluster_dates,
    inventory,
    same_event_in_train_and_test,
)
from floodlens.ml.spatial.eval_spatial import dice_at_threshold, map_metrics
from floodlens.ml.spatial.labels import encode_binary
from floodlens.ml.spatial.schema import UNKNOWN


def test_cluster_dates_merges_orbit_pairs():
    groups = cluster_dates(["2022-05-16", "2022-05-18", "2022-05-28", "2020-06-19"], gap_days=14)
    assert ["2022-05-16", "2022-05-18", "2022-05-28"] in groups or any(
        "2022-05-16" in g and "2022-05-28" in g for g in groups
    )
    assert any("2020-06-19" in g for g in groups)


def test_inventory_does_not_treat_adjacent_tiles_as_two_events():
    a = make_synthetic_sample(city_id="sunamganj", issue_time="2018-06-01T00:00:00Z", seed=1)
    b = make_synthetic_sample(city_id="dhaka", issue_time="2018-06-01T00:00:00Z", seed=2)
    a.valid_at = "2018-06-09T00:00:00Z"
    b.valid_at = "2018-06-09T00:00:00Z"
    assign_event_ids([a, b])
    inv = inventory([a, b])
    assert inv["n_tiles"] == 2
    assert inv["n_independent_events"] == 1
    assert inv["verdict"] == "INSUFFICIENT FOR VALIDATION"


def test_nodata_never_scored_as_dry():
    frac = np.ones((4, 4)) * 0.0
    valid = np.zeros((4, 4), dtype=bool)
    y = encode_binary(frac, valid, tau=0.25)
    assert np.all(y == UNKNOWN)
    m = map_metrics(np.array([]), np.array([]))
    assert m["n"] == 0
    assert dice_at_threshold(np.array([1.0, 0.0]), np.array([0.9, 0.1]), 0.5) > 0.9


def test_same_event_cannot_sit_in_train_and_test():
    a = make_synthetic_sample(issue_time="2022-05-15T00:00:00Z", split="train", seed=3)
    b = make_synthetic_sample(issue_time="2022-05-16T00:00:00Z", split="test", seed=4)
    a.valid_at = "2022-05-16T00:00:00Z"
    b.valid_at = "2022-05-18T00:00:00Z"
    a.split = "train"
    b.split = "test"
    assign_event_ids([a, b])
    # same city, 2 days apart → one event_id → leakage if splits differ
    leaked = same_event_in_train_and_test([a, b])
    assert leaked


def test_gfm_candidates_reject_neighbor_equi7_tiles():
    from floodlens.ml.spatial.acquire_gfm import _dedupe_one_per_day
    from floodlens.ml.spatial.equi7 import TILE_ID

    feats = [
        {
            "id": "ENSEMBLE_FLOOD_20160628T120505_VV_AS020M_E039N024T3",
            "properties": {"datetime": "2016-06-28T12:05:05Z"},
            "assets": {
                "ensemble_flood_extent": {
                    "href": "https://data.eodc.eu/x/ENSEMBLE_FLOOD_20160628T120505_VV_AS020M_E039N024T3.tif"
                }
            },
        },
        {
            "id": "ENSEMBLE_FLOOD_20180113T120433_VV_AS020M_E039N021T3",
            "properties": {"datetime": "2018-01-13T12:04:33Z"},
            "assets": {
                "ensemble_flood_extent": {
                    "href": "https://data.eodc.eu/x/ENSEMBLE_FLOOD_20180113T120433_VV_AS020M_E039N021T3.tif"
                }
            },
        },
    ]
    kept = _dedupe_one_per_day(feats)
    assert len(kept) == 1
    assert TILE_ID in kept[0]["id"]


def test_scene_from_raw_path_parses_product_tile():
    from pathlib import Path

    from floodlens.ml.spatial.acquire_gfm import scene_from_raw_path

    row = scene_from_raw_path(Path("ENSEMBLE_FLOOD_20180113T120433_VV_AS020M_E039N021T3.tif"))
    assert row["datetime"].startswith("2018-01-13T12:04:33")
    neighbor = scene_from_raw_path(Path("ENSEMBLE_FLOOD_20160628T120505_VV_AS020M_E039N024T3.tif"))
    assert neighbor is not None
    assert neighbor["tile"] == "E039N024T3"

    from floodlens.ml.spatial.acquire_gfm import _keep_independent_days

    rows = [
        {"datetime": "2022-05-16T12:00:00Z", "id": "a"},
        {"datetime": "2022-05-18T12:00:00Z", "id": "b"},
        {"datetime": "2022-06-20T12:00:00Z", "id": "c"},
    ]
    kept = _keep_independent_days(rows, gap_days=10)
    assert [r["id"] for r in kept] == ["a", "c"]


def test_dem_plan_fails_closed_without_path():
    from floodlens.ml.spatial.dem_plan import DEM_INGESTION_PLAN, try_load_city_dem

    arr, ok = try_load_city_dem("sunamganj")
    assert ok is False
    assert arr is None
    assert DEM_INGESTION_PLAN["fail_closed"] is True
    assert "pipeline tests only" in DEM_INGESTION_PLAN["synthetic_allowed"]


def test_scene_quality_does_not_code_nodata_as_dry():
    from floodlens.ml.spatial.labels import scene_quality_table

    table = scene_quality_table(
        {
            "scenes": [
                {
                    "id": "s1",
                    "datetime": "2022-05-16T00:00:00Z",
                    "cities": {
                        "dhaka": {
                            "n_flood": 1,
                            "n_dry": 10,
                            "n_unknown": 100,
                            "valid_frac": 0.1,
                        }
                    },
                }
            ]
        }
    )
    assert table[0]["nodata_coded_as_dry"] is False
    assert table[0]["unknown_pixels"] == 100
    assert table[0]["negative_pixels"] == 10


def test_conformal_does_not_claim_80_percent():
    from floodlens.ml.spatial.eval_spatial import conformal_heldout
    from floodlens.ml.uncertainty import fit_conformal

    sample = make_synthetic_sample(issue_time="2022-05-15T00:00:00Z", split="test", seed=5)
    y = sample.y_binary().reshape(-1)
    p = np.full_like(y, 0.4)
    m = np.isfinite(y)
    cal = fit_conformal(y[m], p[m])

    def pred(s):
        return np.full(s.y_flood.shape, 0.4)

    row = conformal_heldout([sample], pred, cal)
    assert row["claim_80_percent"] is False
    assert "empirical_coverage" in row


def test_hard_case_flags_and_subset_empty_ok():
    from floodlens.ml.spatial.eval_spatial import hard_case_masks, subset_metrics

    sample = make_synthetic_sample(seed=6)
    flags = hard_case_masks(sample)
    assert set(flags) >= {"weak_flood", "small_flood", "nodata_heavy", "low_rainfall", "rare_event"}

    def pred(s):
        return np.zeros(s.y_flood.shape)

    empty = subset_metrics([sample], pred, "nodata_heavy")
    assert "n_maps" in empty


def test_phase55_never_promotes_validated():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src/floodlens/ml/spatial/phase55.py").read_text()
    train = (Path(__file__).resolve().parents[1] / "src/floodlens/ml/spatial/train.py").read_text()
    assert "mark_spatial_validated" not in src
    assert "mark_spatial_validated" not in train
    assert "promoted_to_validated" in src


def test_conv_smooth_and_rain_threshold_baselines_exist():
    from floodlens.ml.spatial.baselines import conv_smooth_map, rain_threshold_map

    sample = make_synthetic_sample(seed=7)
    rain = rain_threshold_map(sample, 1.0)
    conv = conv_smooth_map(sample)
    assert rain.shape == sample.y_flood.shape
    assert conv.shape == sample.y_flood.shape
    assert np.all((conv >= 0) & (conv <= 1))


def test_unet_records_train_loss():
    from floodlens.ml.spatial.unet import bce_on_samples, fit_unet

    samples = [make_synthetic_sample(seed=i, split="train") for i in range(3)]
    model = fit_unet(samples, epochs=1)
    assert model.history["train_loss"]
    loss = bce_on_samples(model, samples)
    assert loss is None or np.isfinite(loss)

