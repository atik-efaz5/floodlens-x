"""Spatial leakage guards. Extends AOI leakage.py; does not replace it."""

from __future__ import annotations

from typing import Iterable, List

from floodlens.ml.leakage import LeakageError, hours_between, parse_ts
from floodlens.ml.spatial.schema import HORIZON_HOURS, SpatialForecastSample
from floodlens.ml.spatial.splits import event_straddle_violations


def check_spatial_sample(sample: SpatialForecastSample) -> List[str]:
    errors: List[str] = []
    extra = sample.extra or {}
    if extra.get("sar_at_issue_as_feature") or extra.get("optical_at_valid_as_feature"):
        errors.append("same-time or future satellite used as input (label only)")
    if extra.get("era5_at_valid_as_feature") or extra.get("future_rain_as_feature"):
        errors.append("future rain / ERA5 at t+h used as a feature")
    if extra.get("q_lookback_includes_valid_at") or extra.get("q_at_valid_at_as_feature"):
        errors.append("future discharge used as a feature")
    if extra.get("physics_depth_at_valid_at_as_feature"):
        errors.append("physics SWE at t+h used as AI feature")
    if extra.get("persistence_is_target"):
        errors.append("persistence used the target map")
    if extra.get("pixel_iid_split"):
        errors.append("pixel-level random split")
    if extra.get("scaler_fit_on_test"):
        errors.append("normalization from test rasters")
    kinds = sample.x_precip_hourly_kind or []
    if any(k == "FORECAST" for k in kinds):
        errors.append("future/forecast rain stored as lookback observed feature")
    if parse_ts(sample.issue_time) >= parse_ts(sample.valid_at):
        errors.append("issue t must be before label valid_at")
    if abs(hours_between(sample.valid_at, sample.issue_time) - sample.horizon_hours) > 1.0:
        errors.append("valid_at is not issue_time + horizon")
    if sample.horizon_hours not in {HORIZON_HOURS, sample.horizon_hours} and extra.get("invented_subdaily_label"):
        errors.append("invented 6h/12h/24h spatial labels")
    if extra.get("invented_subdaily_label"):
        errors.append("invented 6h/12h/24h spatial labels")
    cube_ok = float((sample.extra or {}).get("cube_completeness") or 0.0) >= 0.5
    lattice_rain = (sample.extra or {}).get("rainfall_status") in {"REANALYSIS", "OBSERVED"}
    if (
        sample.lookback_complete_frac < 0.80
        and not (cube_ok and lattice_rain)
        and sample.split in {"train", "val", "test"}
    ):
        errors.append("lookback completeness < 80% must be dropped before split assignment")
    return errors


def assert_no_spatial_leakage(samples: Iterable[SpatialForecastSample]) -> None:
    problems = []
    samples = list(samples)
    for i, sample in enumerate(samples):
        errs = check_spatial_sample(sample)
        if errs:
            problems.append(
                f"spatial[{i}] {sample.city_id} {sample.issue_time}: {errs}"
            )
    problems.extend(event_straddle_violations(samples))
    if problems:
        raise LeakageError("\n".join(problems[:20]))


def assert_persistence_is_lagged(sample: SpatialForecastSample) -> None:
    extra = sample.extra or {}
    prev = extra.get("persistence_valid_at")
    if sample.x_persistence is None:
        return
    if extra.get("persistence_is_target"):
        raise LeakageError("persistence used the target map")
    if prev is None:
        raise LeakageError("persistence map missing previous valid_at")
    if parse_ts(prev) >= parse_ts(sample.issue_time):
        raise LeakageError("persistence must be a completed observation before issue_time")
