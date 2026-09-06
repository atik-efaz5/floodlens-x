"""Phase 6 formulation: channel audit, gates, v2 features. No VALIDATED promotion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from floodlens.ml.spatial.aois_v2 import AOI_IDS_V2, GEO_TEST_AOIS, aoi_bounds, q_proxy_city
from floodlens.ml.spatial.builder import make_synthetic_sample, make_synthetic_sample_v2
from floodlens.ml.spatial.channel_audit import (
    CONSTANT,
    MIN_SPATIAL_CHANNELS,
    SPATIAL,
    TEMPORAL_ONLY,
    audit_channels,
    refuse_cnn,
)
from floodlens.ml.spatial.events import assign_event_ids, inventory
from floodlens.ml.spatial.gates import evaluate_gate0, evaluate_gate1, evaluate_gate2, unknown_never_scored_as_dry
from floodlens.ml.spatial.precip_lattice import lattice_points
from floodlens.ml.spatial.schema import GRID_SIZE, GRID_SIZE_V2, LABEL_OBSERVED, UNKNOWN
from floodlens.ml.spatial.splits import assign_temporal, geographic_split, temporal_split


def test_broadcast_channels_are_not_spatial():
    samples = [
        make_synthetic_sample(issue_time="2018-06-01T00:00:00Z", seed=1),
        make_synthetic_sample(issue_time="2018-07-01T00:00:00Z", seed=2),
    ]
    audit = audit_channels(samples)
    ch = audit["channels"]
    assert ch["precip_24h"]["class"] in {TEMPORAL_ONLY, CONSTANT}
    assert ch["precip_72h"]["class"] in {TEMPORAL_ONLY, CONSTANT}
    assert ch["log1p_q"]["class"] in {TEMPORAL_ONLY, CONSTANT}
    assert ch["month_sin"]["class"] in {TEMPORAL_ONLY, CONSTANT}
    assert ch["precip_is_aoi_point"]["class"] in {CONSTANT, TEMPORAL_ONLY}
    assert ch["persistence"]["class"] == SPATIAL
    assert audit["n_spatial"] < MIN_SPATIAL_CHANNELS
    assert refuse_cnn(audit)


def test_cnn_refused_below_four_spatial_channels():
    samples = [make_synthetic_sample(seed=0)]
    reason = refuse_cnn(audit_channels(samples))
    assert reason is not None
    assert "CNN refused" in reason


def test_v2_synthetic_has_spatial_rain_dem_river():
    sample = make_synthetic_sample_v2(city_id="kishoreganj", seed=3)
    assert sample.y_flood.shape == (GRID_SIZE_V2, GRID_SIZE_V2)
    assert sample.dem_present is True
    assert sample.precip_is_aoi_point is False
    assert sample.x_dem is not None
    extra = sample.extra
    assert extra["precip_24h_map"].shape == (GRID_SIZE_V2, GRID_SIZE_V2)
    assert float(np.var(extra["precip_24h_map"])) > 1e-8
    assert float(np.var(sample.x_dem)) > 1e-8
    audit = audit_channels([sample])
    assert audit["n_spatial"] >= MIN_SPATIAL_CHANNELS
    assert refuse_cnn(audit) is None


def test_gate0_fails_on_phase55_like_broadcast_sample():
    samples = [make_synthetic_sample(seed=4, split="train")]
    gate = evaluate_gate0(samples)
    assert gate["pass"] is False
    assert "independent_events" in gate["failed"]
    assert "dem_present" in gate["failed"] or "spatial_channels" in gate["failed"]


def _corpus_v2(n: int = 20):
    aois = ("sunamganj", "kishoreganj", "dhaka_ne")
    train_dates = [datetime(2017, 1, 15, tzinfo=timezone.utc) + timedelta(days=50 * i) for i in range(12)]
    val_dates = [datetime(2019, 6, 1, tzinfo=timezone.utc) + timedelta(days=80 * i) for i in range(4)]
    test_dates = [datetime(2022, 5, 20, tzinfo=timezone.utc) + timedelta(days=80 * i) for i in range(4)]
    stamps = (train_dates + val_dates + test_dates)[:n]
    samples = []
    for i, stamp in enumerate(stamps):
        sample = make_synthetic_sample_v2(
            city_id=aois[i % 3],
            issue_time=stamp.strftime("%Y-%m-%dT00:00:00Z"),
            seed=10 + i,
        )
        sample.label_kind = LABEL_OBSERVED
        sample.extra["synthetic"] = False
        sample.extra["rainfall_status"] = "REANALYSIS"
        samples.append(sample)
    assign_temporal(samples)
    assign_event_ids(samples)
    return samples


def test_gate0_can_pass_on_twenty_v2_events():
    samples = _corpus_v2(20)
    inv = inventory(samples)
    assert inv["n_independent_events"] >= 20
    gate = evaluate_gate0(samples)
    assert gate["checks"]["independent_events"]
    assert gate["checks"]["regions"]
    assert gate["checks"]["spatial_channels"]
    assert gate["checks"]["dem_present"]
    assert gate["checks"]["precip_lattice"]
    assert gate["checks"]["no_event_leak_train_test"]
    assert gate["checks"]["label_observed"]
    assert gate["checks"]["unknown_never_dry"]
    assert gate["pass"] is True


def test_gate1_requires_gbdt_over_persistence_and_gate0():
    g0 = {"pass": True, "failed": []}
    fail = evaluate_gate1(g0, gbdt_iou=0.10, persistence_iou=0.12, n_train_events=12)
    assert fail["pass"] is False
    assert "gbdt_beats_persistence" in fail["failed"]
    ok = evaluate_gate1(g0, gbdt_iou=0.25, persistence_iou=0.12, n_train_events=12)
    assert ok["pass"] is True
    blocked = evaluate_gate1({"pass": False, "failed": ["independent_events"]}, 0.3, 0.1, 12)
    assert blocked["pass"] is False


def test_gate2_blocked_without_gate1():
    g2 = evaluate_gate2(
        {"pass": False, "failed": ["gate0"]},
        event_metrics_ok=True,
        geographic_holdout_not_zero=True,
        conformal_claim_80=False,
        uncertainty_informative=False,
        uncertainty_omitted=True,
    )
    assert g2["pass"] is False


def test_nodata_never_dry_on_v2():
    sample = make_synthetic_sample_v2(seed=8)
    assert sample.y_flood[0, 0] == UNKNOWN
    yb = sample.y_binary()
    assert not np.isfinite(yb[0, 0])
    assert unknown_never_scored_as_dry([sample])


def test_v1_grid_unchanged_and_v2_is_64():
    assert GRID_SIZE == 32
    assert GRID_SIZE_V2 == 64
    v1 = make_synthetic_sample(seed=1)
    assert v1.y_flood.shape == (32, 32)


def test_aois_v2_not_in_product_catalog_bounds():
    assert len(AOI_IDS_V2) >= 8
    west, south, east, north = aoi_bounds("kishoreganj")
    assert west < east and south < north
    assert q_proxy_city("kishoreganj") == "sunamganj"
    assert geographic_split("netrokona") == "test"
    assert geographic_split("kishoreganj") == "train"
    assert "sunamganj" in GEO_TEST_AOIS


def test_precip_lattice_has_at_least_four_points():
    pts = lattice_points("sunamganj", n=3)
    assert len(pts) == 9
    lats = {p[0] for p in pts}
    lons = {p[1] for p in pts}
    assert len(lats) == 3 and len(lons) == 3


def test_geographic_and_temporal_split_helpers():
    assert temporal_split("2018-06-01T00:00:00Z") == "train"
    assert temporal_split("2020-06-01T00:00:00Z") == "val"
    assert geographic_split("dhaka_ne") == "train"
    assert geographic_split("sylhet") == "test"


def test_phase6_and_train_never_mark_validated():
    root = Path(__file__).resolve().parents[1]
    phase6 = (root / "src/floodlens/ml/spatial/phase6.py").read_text()
    train = (root / "src/floodlens/ml/spatial/train.py").read_text()
    assert "mark_spatial_validated(" not in phase6
    assert "from floodlens.ml.spatial.registry_spatial import mark_spatial_validated" not in phase6
    assert "mark_spatial_validated" not in train
    assert "fit_unet" not in train
    assert "promoted_to_validated" in phase6


def test_v2_cards_exist_and_have_no_fake_metrics():
    root = Path(__file__).resolve().parents[1]
    data = (root / "docs/data_cards/SPATIAL_FLOOD_DATASET_V2.md").read_text()
    model = (root / "docs/model_cards/SPATIAL_AI_FLOOD_V2.md").read_text()
    status = (root / "docs/PHASE6_FORMULATION.md").read_text()
    assert "OBSERVED" in data
    assert "64" in data
    assert "Gate 0" in model
    assert "NOT_TRAINED" in model or "NOT_VALIDATED" in model
    assert "Empty on purpose" in model or "not reported" in model
    assert "do not train a u-net" in status.lower()


def test_frontend_status_mentions_gate2():
    root = Path(__file__).resolve().parents[1]
    status = (root / "frontend/src/platform/ModelStatusPanel.jsx").read_text()
    assert "Gate 2" in status
    assert "UNAVAILABLE" in status
    panel = (root / "frontend/src/platform/ForecastPanel.jsx").read_text()
    assert "AI Powered" not in panel


def test_index_local_v2_exports_and_processed_dir():
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR, PROCESSED_DIR_V2, index_local_v2

    assert PROCESSED_DIR.name == "processed"
    assert PROCESSED_DIR_V2.name == "processed_v2"
    assert callable(index_local_v2)


def test_hydrorivers_geojson_loader(tmp_path):
    from floodlens.ml.spatial.river_features import load_hydrorivers, river_distance_map, river_mask_map

    path = tmp_path / "hydrorivers.geojson"
    path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":'
        '{"type":"LineString","coordinates":[[91.30,24.90],[91.35,24.95]]}}]}'
    )
    payload = load_hydrorivers(aoi_ids=["sunamganj"], path=path)
    assert payload is not None
    assert payload["aois"]["sunamganj"]["n_vertices"] >= 1
    dist = river_distance_map("sunamganj", 8, 8, cache=payload)
    assert dist is not None and dist.shape == (8, 8)
    mask = river_mask_map(dist)
    assert mask is not None and set(np.unique(mask)).issubset({0.0, 1.0})
