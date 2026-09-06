"""Phase 5 spatial schema, leakage, splits, baselines, U-Net (synthetic maps)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodlens.ml.leakage import LeakageError
from floodlens.ml.spatial.baselines import (
    evaluate_spatial_baselines,
    fit_spatial_baselines,
    persistence_map,
)
from floodlens.ml.spatial.builder import make_synthetic_sample
from floodlens.ml.spatial.equi7 import in_tile, lonlat_to_pixel
from floodlens.ml.spatial.labels import encode_binary, mix_kinds_error, valid_prevalence
from floodlens.ml.spatial.leakage import assert_no_spatial_leakage, assert_persistence_is_lagged
from floodlens.ml.spatial.schema import (
    GRID_SIZE,
    HORIZON_HOURS,
    LABEL_OBSERVED,
    raster_metadata,
)
from floodlens.ml.spatial.splits import (
    event_straddle_violations,
    forbid_pixel_iid,
    geographic_split,
    temporal_split,
)
from floodlens.ml.spatial.unet import TinyUNet, fit_unet, sample_channels
from floodlens.ml.spatial.registry_spatial import (
    load_spatial_registry,
    public_spatial_status,
    save_spatial_registry,
)
from floodlens.ml.registry import public_status, load_registry


def test_aoi_gbdt_registry_unchanged():
    record = load_registry()
    assert record["id"] == "ai-forecast"
    assert record["model_id"] == "FLOOD-OCCURRENCE-GBDT-v0.1"
    assert public_status(record) == "VALIDATED"
    assert record["label_kind"] == "MODELLED"


def test_spatial_registry_does_not_inherit_validated():
    spatial = load_spatial_registry()
    assert spatial["id"] == "ai-spatial-forecast"
    assert public_spatial_status(spatial) == "NOT_TRAINED"
    assert spatial["status"] != "VALIDATED"
    assert spatial.get("comparable_to_physics") is False


def test_raster_metadata_has_no_array():
    meta = raster_metadata(
        dataset_id="phase5-gfm-aoi-v0.1",
        variable="flood_occurrence",
        timestamp="2018-06-01T00:00:00Z",
        valid_at="2018-06-09T00:00:00Z",
        crs="EPSG:4326",
        resolution=500.0,
        bounds=[91.2, 24.8, 91.5, 25.1],
        width=32,
        height=32,
        nodata=255,
        units="class",
        source="copernicus-gfm",
        data_status="REAL",
        label_kind=LABEL_OBSERVED,
    )
    assert "y_flood" not in meta
    assert set(meta) >= {
        "dataset_id",
        "variable",
        "timestamp",
        "valid_at",
        "crs",
        "resolution",
        "bounds",
        "width",
        "height",
        "nodata",
        "units",
        "source",
        "data_status",
        "label_kind",
        "artifact_uri",
    }


def test_unknown_never_dry_and_kinds_not_mixed():
    frac = np.array([[0.9, 0.0], [0.1, 0.4]])
    valid = np.array([[True, False], [True, True]])
    y = encode_binary(frac, valid, tau=0.25)
    assert y[0, 1] == 255
    assert y[0, 0] == 1
    assert y[1, 0] == 0
    n, prev = valid_prevalence(y)
    assert n == 3
    assert mix_kinds_error(["OBSERVED", "MODELLED"]) is not None
    assert mix_kinds_error(["OBSERVED", "OBSERVED"]) is None


def test_equi7_cities_in_shared_tile():
    assert in_tile(24.95, 91.35)
    assert in_tile(23.81, 90.41)
    r, c = lonlat_to_pixel(24.95, 91.35)
    assert 0 <= r < 15000 and 0 <= c < 15000


def test_temporal_and_geo_splits_not_pixel_iid():
    assert temporal_split("2018-06-01T00:00:00Z") == "train"
    assert temporal_split("2020-06-01T00:00:00Z") == "val"
    assert temporal_split("2022-05-15T00:00:00Z") == "test"
    assert geographic_split("dhaka") == "train"
    assert geographic_split("sunamganj") == "test"
    with pytest.raises(ValueError):
        forbid_pixel_iid("pixel")


def test_leakage_guards_sar_future_and_persistence():
    sample = make_synthetic_sample(issue_time="2018-06-01T00:00:00Z", seed=1)
    assert_no_spatial_leakage([sample])
    assert_persistence_is_lagged(sample)
    sample.extra["sar_at_issue_as_feature"] = True
    with pytest.raises(LeakageError):
        assert_no_spatial_leakage([sample])
    hold = make_synthetic_sample(issue_time="2022-05-15T00:00:00Z", split="train", seed=2)
    hold.split = "train"
    assert event_straddle_violations([hold])


def test_synthetic_baselines_and_unet_pipeline():
    samples = [
        make_synthetic_sample(issue_time="2018-06-01T00:00:00Z", split="train", seed=i)
        for i in range(4)
    ]
    samples += [
        make_synthetic_sample(issue_time="2020-06-01T00:00:00Z", split="val", seed=10 + i)
        for i in range(2)
    ]
    fitted = fit_spatial_baselines(samples)
    table = evaluate_spatial_baselines(samples, fitted, "val")
    assert table["accuracy_claim"] is None
    assert "persistence" in table["models"]
    pers = persistence_map(samples[0])
    assert pers.shape == (GRID_SIZE, GRID_SIZE)
    model = fit_unet(samples[:3], epochs=1)
    prob = model.predict_proba(samples[0])
    assert prob.shape == (GRID_SIZE, GRID_SIZE)
    assert 0.0 <= float(np.min(prob)) <= float(np.max(prob)) <= 1.0
    chans = sample_channels(samples[0])
    assert chans.shape[0] >= 8
    blob = model.to_dict()
    restored = TinyUNet.from_dict(blob)
    p2 = restored.predict_proba(samples[0])
    assert np.allclose(prob, p2)
    assert HORIZON_HOURS == 192


def test_spatial_registry_trained_stays_not_public(tmp_path: Path):
    path = tmp_path / "spatial_registry.json"
    save_spatial_registry(
        {
            "id": "ai-spatial-forecast",
            "status": "TRAINED",
            "accuracy_claim": None,
            "checkpoint": str(tmp_path / "ckpt.json"),
        },
        path=path,
    )
    assert public_spatial_status(load_spatial_registry(path)) == "NOT_TRAINED"


def test_real_gfm_builder_if_snapshot_present():
    from floodlens.ml.spatial.acquire_gfm import snapshot_available
    from floodlens.ml.spatial.builder import build_spatial_samples

    if not snapshot_available():
        pytest.skip("GFM AOI snapshot not acquired")
    samples, meta = build_spatial_samples()
    assert meta["label_kind"] == LABEL_OBSERVED
    assert samples
    assert all(s.label_kind == LABEL_OBSERVED for s in samples)
    assert all(s.horizon_hours == HORIZON_HOURS for s in samples)
    assert_no_spatial_leakage(samples)
    assert not event_straddle_violations(samples)
    splits = {s.split for s in samples}
    years = {s.valid_at[:4] for s in samples}
    if any(y <= "2018" for y in years):
        assert "train" in splits
    kinds = {s.label_kind for s in samples}
    assert kinds == {LABEL_OBSERVED}
