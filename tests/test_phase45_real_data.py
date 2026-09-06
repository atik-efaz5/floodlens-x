"""Phase 4.5 real Open-Meteo GloFAS dataset: ingestion, labels, leakage, splits."""

from __future__ import annotations

import pytest

from floodlens.ml.leakage import LeakageError, assert_no_leakage, parse_ts
from floodlens.ml.real_dataset import (
    REAL_DATASET_VERSION,
    REAL_HORIZONS,
    build_real_samples,
    empirical_q2_thresholds,
    load_raw,
    snapshot_available,
)
from floodlens.ml.splits import by_split, in_named_holdout


pytestmark = pytest.mark.skipif(not snapshot_available(), reason="real Open-Meteo snapshot not acquired")


def test_snapshot_has_three_cities_and_no_null_q():
    discharge, precip, manifest = load_raw()
    assert set(discharge["cities"]) == {"sunamganj", "dhaka", "sylhet"}
    assert set(precip["cities"]) == {"sunamganj", "dhaka", "sylhet"}
    for city, payload in discharge["cities"].items():
        assert payload["n"] >= 3650
        assert payload["n_null"] == 0
        assert payload["n"] == len(payload["river_discharge_m3s"])
    for city, payload in precip["cities"].items():
        assert payload["n"] >= 80000
        assert payload["n_null"] == 0
    assert manifest["credentials"] == "none"
    assert manifest["dataset_version"] == REAL_DATASET_VERSION


def test_q2_threshold_uses_train_years_only():
    discharge, _, _ = load_raw()
    thresholds, ams = empirical_q2_thresholds(discharge, train_end_year=2021)
    for city, series in ams.items():
        years = [int(y) for y in series]
        assert max(years) == 2021
        assert min(years) <= 2015
        assert thresholds[city] > 0


def test_real_samples_leakage_and_daily_horizons():
    samples, meta = build_real_samples()
    assert_no_leakage(samples)
    assert samples
    assert set(meta["horizons"]) == {24, 48, 72}
    assert 6 not in {s.horizon_hours for s in samples}
    assert 12 not in {s.horizon_hours for s in samples}
    assert all(s.label_kind == "MODELLED" for s in samples)
    assert all(s.y_track_b_available is False for s in samples)
    assert all(s.x_precip_forecast_to_h is None for s in samples)
    for sample in samples[:50]:
        issue = parse_ts(sample.issue_time)
        assert all(k == "OBSERVED" for k in sample.x_precip_hourly_kind) or sample.lookback_complete_frac >= 0.8
        assert sample.x_glofas_q_lookback
        assert sample.x_glofas_q_lookback[-1] is not None
        assert "forecast_is_era5_at_valid_at" not in (sample.extra or {})
        assert (issue.hour, issue.minute) == (0, 0)


def test_real_temporal_and_named_holdout():
    samples, meta = build_real_samples()
    train = by_split(samples, "train")
    val = by_split(samples, "val")
    test = by_split(samples, "test")
    assert train and val and test
    assert all(parse_ts(s.issue_time).year <= 2021 for s in train)
    holdout = [s for s in samples if in_named_holdout(parse_ts(s.issue_time))]
    assert holdout
    assert all(s.split == "test" for s in holdout)
    assert meta["splits"]["train"] == len(train)


def test_geographic_holdout_does_not_mix_test_city_into_train():
    from floodlens.ml.splits import geographic_split

    assert geographic_split("sunamganj", train_cities={"dhaka", "sylhet"}) == "test"
    assert geographic_split("dhaka", train_cities={"dhaka", "sylhet"}) == "train"


def test_q_lookback_is_strictly_before_issue_day():
    from floodlens.ml.real_dataset import q_lookback_before_issue

    samples, _ = build_real_samples()
    sample = samples[0]
    issue = parse_ts(sample.issue_time)
    assert len(sample.x_glofas_q_lookback) == 7
    assert sample.x_precip_forecast_to_h is None
    assert sample.x_dem_stats is None
    assert (sample.extra or {}).get("q_at_valid_at_as_feature") is None
    packed = q_lookback_before_issue(sample.city_id, issue, allow_live=False)
    assert packed is not None
    assert packed["end_day"] < issue.strftime("%Y-%m-%d")
    assert packed["values"] == sample.x_glofas_q_lookback


def test_future_q_as_feature_still_rejected():
    from floodlens.ml.schema import ForecastSample

    samples, _ = build_real_samples()
    row = ForecastSample.from_dict(samples[0].to_dict())
    row.extra = {**(row.extra or {}), "physics_depth_at_valid_at_as_feature": True}
    with pytest.raises(LeakageError):
        assert_no_leakage([row])
    row2 = ForecastSample.from_dict(samples[0].to_dict())
    row2.extra = {**(row2.extra or {}), "q_at_valid_at_as_feature": True}
    with pytest.raises(LeakageError):
        assert_no_leakage([row2])
