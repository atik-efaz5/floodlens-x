"""Leakage guards: no future rain, no ERA5-as-forecast, no random split."""

from __future__ import annotations

import pytest

from floodlens.ml.dataset_builder import build_synthetic_samples
from floodlens.ml.features import fit_scaler, matrix
from floodlens.ml.leakage import LeakageError, assert_no_leakage, assert_scaler_train_only
from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample
from floodlens.ml.splits import by_split, temporal_split


def _base_sample(**overrides) -> ForecastSample:
    payload = dict(
        city_id="dhaka",
        issue_time="2021-06-01T00:00:00Z",
        horizon_hours=24,
        valid_at="2021-06-02T00:00:00Z",
        x_precip_hourly=[0.1] * LOOKBACK_HOURS,
        x_precip_hourly_kind=["OBSERVED"] * LOOKBACK_HOURS,
        x_precip_forecast_to_h=None,
        x_precip_forecast_issued_at=None,
        x_antecedent_24h=2.4,
        x_antecedent_72h=5.0,
        x_dem_stats=None,
        x_glofas_q_lookback=None,
        y_track_a=0,
        y_track_b=None,
        y_track_b_available=False,
        lookback_complete_frac=1.0,
        label_source="test",
        label_kind="MODELLED",
        issue_precip_forecast_id=None,
        split="train",
        extra={},
    )
    payload.update(overrides)
    return ForecastSample(**payload)


def test_future_forecast_kind_in_lookback_is_leakage():
    sample = _base_sample(x_precip_hourly_kind=["FORECAST"] * LOOKBACK_HOURS)
    with pytest.raises(LeakageError):
        assert_no_leakage([sample])


def test_era5_at_valid_at_as_forecast_is_leakage():
    sample = _base_sample(
        x_precip_forecast_to_h=12.0,
        x_precip_forecast_issued_at="2021-06-01T00:00:00Z",
        extra={"forecast_is_era5_at_valid_at": True},
    )
    with pytest.raises(LeakageError):
        assert_no_leakage([sample])


def test_physics_and_late_emsr_as_features_are_leakage():
    with pytest.raises(LeakageError):
        assert_no_leakage([_base_sample(extra={"physics_depth_at_valid_at_as_feature": True})])
    with pytest.raises(LeakageError):
        assert_no_leakage([_base_sample(extra={"emsr_acquired_after_issue": True})])


def test_synthetic_builder_samples_pass_leakage_guards():
    samples = build_synthetic_samples(
        start="2021-05-01T00:00:00Z",
        end="2021-08-01T00:00:00Z",
        cities=("dhaka",),
        stride_hours=24,
    )
    assert_no_leakage(samples)
    assert all(s.lookback_complete_frac >= 0.80 for s in samples)
    assert all(len(s.x_precip_hourly) == LOOKBACK_HOURS for s in samples)


def test_scaler_statistics_come_from_train_only():
    samples = build_synthetic_samples(
        start="2020-01-01T00:00:00Z",
        end="2023-03-01T00:00:00Z",
        cities=("dhaka",),
        stride_hours=48,
    )
    X_train, _, _ = matrix(by_split(samples, "train"), track="A")
    scaler = fit_scaler(X_train)
    assert_scaler_train_only(scaler.mean.tolist(), scaler.mean.tolist())
    X_val, _, _ = matrix(by_split(samples, "val"), track="A")
    val_mean = X_val.mean(axis=0).tolist()
    with pytest.raises(LeakageError):
        assert_scaler_train_only(scaler.mean.tolist(), val_mean)


def test_temporal_split_is_not_random():
    assert temporal_split("2021-12-31T00:00:00Z") == "train"
    assert temporal_split("2022-03-01T00:00:00Z") == "val"
    assert temporal_split("2023-03-01T00:00:00Z") == "test"
    assert temporal_split("2022-06-01T00:00:00Z") == "test"
