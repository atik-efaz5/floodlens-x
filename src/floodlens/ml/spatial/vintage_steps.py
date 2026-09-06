"""Native-step forecast coverage and accumulation.

Does not interpolate 6-hourly fields onto fake hourly intensities.
An hour is covered only if it falls in a genuine accumulation window
whose valid_time is in (t0, t1].
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from floodlens.ml.leakage import hours_between, parse_ts
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_VINTAGE,
    UNAVAILABLE,
    issue_at_or_before_t0,
    valid_time_in_target_interval,
)
from floodlens.ml.spatial.phase68a import hour_key, hours_in_open_closed


def _iso(stamp: datetime) -> str:
    from datetime import timezone

    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def accumulate_forecast_precip(
    records: Sequence[Tuple[str, Optional[float]]],
    t0: str,
    t1: str,
) -> Optional[float]:
    """Sum genuine in-horizon accumulations. Missing values are skipped, not filled."""
    total = 0.0
    n = 0
    for valid, val in records:
        if val is None:
            continue
        if not valid_time_in_target_interval(valid, t0, t1):
            continue
        total += float(val)
        n += 1
    if n == 0:
        return None
    return total


def coverage_from_accumulation_windows(
    *,
    issue_time: str,
    t0: str,
    t1: str,
    windows: Sequence[Tuple[str, float, Optional[float]]],
    filled: bool = False,
) -> dict:
    """windows: (valid_time, window_hours, value_mm)."""
    if filled:
        raise ValueError("filled forecast windows are forbidden")
    if not issue_at_or_before_t0(issue_time, t0):
        return {
            "forecast_status": UNAVAILABLE,
            "forecast_coverage_fraction": 0.0,
            "forecast_n_hours_required": len(hours_in_open_closed(t0, t1)),
            "forecast_n_hours_present": 0,
            "forecast_issue_ok": False,
            "forecast_valid_ok": False,
            "forecast_filled": False,
            "forecast_lead_min": None,
            "forecast_lead_max": None,
            "precip_sum_mm": None,
            "reason": "issue_time > t0",
        }
    required = hours_in_open_closed(t0, t1)
    n_req = len(required)
    covered = set()
    leads = []
    valid_ok = True
    used: List[Tuple[str, Optional[float]]] = []
    for valid, width_h, val in windows:
        if not valid_time_in_target_interval(valid, t0, t1):
            if parse_ts(valid) > parse_ts(t0) and parse_ts(valid) > parse_ts(t1):
                continue
            if parse_ts(valid) <= parse_ts(t0):
                continue
            valid_ok = False
            continue
        if val is None:
            continue
        end = parse_ts(valid)
        start = end - timedelta(hours=float(width_h))
        for stamp in required:
            if start < stamp <= end:
                covered.add(hour_key(_iso(stamp)))
        leads.append(hours_between(valid, issue_time))
        used.append((valid, val))
    present = len(covered)
    frac = (present / n_req) if n_req else 0.0
    return {
        "forecast_status": FORECAST_VINTAGE if present else UNAVAILABLE,
        "forecast_coverage_fraction": frac,
        "forecast_n_hours_required": n_req,
        "forecast_n_hours_present": present,
        "forecast_issue_ok": True,
        "forecast_valid_ok": valid_ok,
        "forecast_filled": False,
        "forecast_lead_min": min(leads) if leads else None,
        "forecast_lead_max": max(leads) if leads else None,
        "precip_sum_mm": accumulate_forecast_precip(used, t0, t1),
        "n_native_steps_used": len(used),
        "reason": None if present else "no in-horizon native forecast steps",
    }


def pm_from_windows(
    *,
    issue_time: str,
    t0: str,
    t1: str,
    windows: Sequence[Tuple[str, float, Optional[float]]],
    filled: bool = False,
) -> dict:
    """Explicit P + M at native steps and hourly mask.

    M=1 only for hours inside a genuine vintage window with valid_time in (t0,t1]
    and issue_time <= t0. M=0 hours have precipitation None, never 0.0 fill.
    Native 6 h accumulations are not interpolated into hourly intensities.
    Precipitation mass is stored on the native valid_time hour only.
    """
    if filled:
        raise ValueError("filled forecast windows are forbidden")
    required = hours_in_open_closed(t0, t1)
    n_req = len(required)
    empty = {
        "forecast_issue_ok": issue_at_or_before_t0(issue_time, t0),
        "hourly_stamps": [_iso(h) for h in required],
        "hourly_mask": [0] * n_req,
        "hourly_precipitation_mm": [None] * n_req,
        "native_steps": [],
        "n_hours_required": n_req,
        "n_hours_masked_on": 0,
        "precip_sum_mm": None,
        "interpolated": False,
        "filled": False,
    }
    if not issue_at_or_before_t0(issue_time, t0):
        return {**empty, "reason": "issue_time > t0"}
    cov = coverage_from_accumulation_windows(
        issue_time=issue_time, t0=t0, t1=t1, windows=windows, filled=False
    )
    mask = [0] * n_req
    precip: List[Optional[float]] = [None] * n_req
    native: List[dict] = []
    hour_index = {hour_key(_iso(h)): i for i, h in enumerate(required)}
    for valid, width_h, val in windows:
        if val is None:
            continue
        if not valid_time_in_target_interval(valid, t0, t1):
            continue
        end = parse_ts(valid)
        start = end - timedelta(hours=float(width_h))
        native.append(
            {
                "valid_time": valid,
                "window_hours": float(width_h),
                "precipitation_mm": float(val),
                "mask": 1,
            }
        )
        for stamp in required:
            if start < stamp <= end:
                mask[hour_index[hour_key(_iso(stamp))]] = 1
        key = hour_key(valid)
        if key in hour_index:
            precip[hour_index[key]] = float(val)
        else:
            # Align mass to the last required hour that falls in the window.
            for stamp in reversed(required):
                if start < stamp <= end:
                    precip[hour_index[hour_key(_iso(stamp))]] = float(val)
                    break
    for i, m in enumerate(mask):
        if m == 0:
            precip[i] = None
    return {
        "forecast_issue_ok": True,
        "hourly_stamps": [_iso(h) for h in required],
        "hourly_mask": mask,
        "hourly_precipitation_mm": precip,
        "native_steps": native,
        "n_hours_required": n_req,
        "n_hours_masked_on": int(sum(mask)),
        "precip_sum_mm": cov.get("precip_sum_mm"),
        "forecast_coverage_fraction": cov.get("forecast_coverage_fraction"),
        "interpolated": False,
        "filled": False,
        "reason": None,
    }
