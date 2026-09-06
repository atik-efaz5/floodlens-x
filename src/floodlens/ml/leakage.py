"""Leakage guards for Phase 4 samples."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from floodlens.ml.schema import LOOKBACK_HOURS, ForecastSample


class LeakageError(ValueError):
    pass


def parse_ts(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def hours_between(later: str, earlier: str) -> float:
    return (parse_ts(later) - parse_ts(earlier)).total_seconds() / 3600.0


def check_sample(sample: ForecastSample) -> List[str]:
    errors: List[str] = []
    if len(sample.x_precip_hourly) != LOOKBACK_HOURS:
        errors.append("lookback length must be 24 hourly values")
    if sample.lookback_complete_frac < 0.80 and sample.split in {"train", "val", "test"}:
        errors.append("lookback completeness < 80% must be dropped before split assignment")
    kinds = sample.x_precip_hourly_kind or []
    if any(k == "FORECAST" for k in kinds):
        errors.append("future/forecast rain stored as lookback observed feature")
    if any(k not in {"OBSERVED", "SIMULATED", "UNAVAILABLE"} for k in kinds):
        errors.append(f"unexpected lookback kind: {sorted(set(kinds))}")
    if sample.x_precip_forecast_to_h is not None:
        issued = sample.x_precip_forecast_issued_at
        if not issued:
            errors.append("forecast precip present without issued_at")
        elif parse_ts(issued) > parse_ts(sample.issue_time):
            errors.append("forecast precip issued after issue_time")
        extra = sample.extra or {}
        if extra.get("forecast_is_era5_at_valid_at"):
            errors.append("ERA5 at t+h used as forecast feature")
    extra = sample.extra or {}
    if extra.get("q_lookback_includes_valid_at") or extra.get("q_at_valid_at_as_feature"):
        errors.append("future discharge used as a feature")
    if extra.get("physics_depth_at_valid_at_as_feature"):
        errors.append("physics SWE at t+h used as AI feature")
    if extra.get("emsr_acquired_after_issue"):
        errors.append("EMSR map acquired after issue_time used as input")
    if abs(hours_between(sample.valid_at, sample.issue_time) - sample.horizon_hours) > 0.01:
        errors.append("valid_at is not issue_time + horizon")
    return errors


def assert_no_leakage(samples: Iterable[ForecastSample]) -> None:
    problems = []
    for i, sample in enumerate(samples):
        errs = check_sample(sample)
        if errs:
            problems.append(f"sample[{i}] {sample.city_id} {sample.issue_time} h={sample.horizon_hours}: {errs}")
    if problems:
        raise LeakageError("\n".join(problems[:20]))


def assert_scaler_train_only(train_mean: list, applied_mean: list, atol: float = 1e-9) -> None:
    if any(abs(a - b) > atol for a, b in zip(train_mean, applied_mean)):
        raise LeakageError("feature scaler was not frozen from the train split")
