"""Phase 6 data-quality gates. Fail closed: do not train, do not VALIDATE."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from floodlens.ml.spatial.channel_audit import MIN_SPATIAL_CHANNELS, SPATIAL, audit_channels, refuse_cnn
from floodlens.ml.spatial.events import EVENT_GAP_DAYS, coverage_summary, inventory, same_event_across_splits, same_event_in_train_and_test
from floodlens.ml.spatial.schema import LABEL_OBSERVED, UNKNOWN, SpatialForecastSample

GATE0_MIN_EVENTS = 20
GATE_B_PROVISIONAL_EVENTS = 20
GATE_B_RESEARCH_PASS_EVENTS = 30
GATE0_MIN_REGIONS = 3
GATE0_MIN_VALID_FRAC = 0.05
GATE1_MIN_TRAIN_EVENTS = 10


def unknown_never_scored_as_dry(samples: Sequence[SpatialForecastSample]) -> bool:
    """Nodata (255) must stay unknown in y_binary; never recoded as dry."""
    if not samples:
        return True
    for sample in samples:
        y = np.asarray(sample.y_flood)
        yb = sample.y_binary()
        if np.any((y == UNKNOWN) & np.isfinite(yb)):
            return False
        if np.any((y == UNKNOWN) & (y == 0)):
            return False
    return True


def evaluate_gate0(samples: Sequence[SpatialForecastSample], audit: Optional[dict] = None) -> dict:
    audit = audit or audit_channels(samples)
    inv = inventory(samples) if samples else {"n_independent_events": 0, "cities": [], "pixels": {}}
    cities = list(inv.get("cities") or [])
    n_spatial = int(audit.get("n_spatial") or 0)
    dem_ok = bool(samples) and all(bool(s.dem_present) and s.x_dem is not None for s in samples)
    lattice_ok = bool(samples) and (
        sum(1 for s in samples if not s.precip_is_aoi_point) >= 0.5 * len(samples)
    )
    leak = same_event_in_train_and_test(samples) if samples else []
    labels = {s.label_kind for s in samples} if samples else set()
    label_ok = labels == {LABEL_OBSERVED} or (not samples)
    checks = {
        "independent_events": int(inv.get("n_independent_events") or 0) >= GATE0_MIN_EVENTS,
        "regions": len(cities) >= GATE0_MIN_REGIONS,
        "spatial_channels": n_spatial >= MIN_SPATIAL_CHANNELS,
        "dem_present": dem_ok,
        "precip_lattice": lattice_ok,
        "no_event_leak_train_test": not leak,
        "label_observed": bool(samples) and label_ok,
        "unknown_never_dry": unknown_never_scored_as_dry(samples),
    }
    failed = [k for k, ok in checks.items() if not ok]
    return {
        "gate": 0,
        "pass": not failed and bool(samples),
        "failed": failed,
        "checks": checks,
        "n_independent_events": inv.get("n_independent_events"),
        "cities": cities,
        "n_spatial_channels": n_spatial,
        "event_gap_days": EVENT_GAP_DAYS,
        "spatial_channel_names": [
            name for name, row in (audit.get("channels") or {}).items() if row.get("class") == SPATIAL
        ],
        "leak_event_ids": leak,
        "unknown_fraction": (inv.get("pixels") or {}).get("unknown_fraction"),
        "note": "If this gate fails: expand data. Do not train a U-Net.",
    }


def evaluate_gate1(gate0: dict, gbdt_iou: Optional[float], persistence_iou: Optional[float], n_train_events: int) -> dict:
    beats = (
        gbdt_iou is not None
        and persistence_iou is not None
        and np_finite_gt(gbdt_iou, persistence_iou)
    )
    checks = {
        "gate0": bool(gate0.get("pass")),
        "gbdt_beats_persistence": beats,
        "train_events": n_train_events >= GATE1_MIN_TRAIN_EVENTS,
    }
    failed = [k for k, ok in checks.items() if not ok]
    return {
        "gate": 1,
        "pass": not failed,
        "failed": failed,
        "checks": checks,
        "gbdt_iou": gbdt_iou,
        "persistence_iou": persistence_iou,
        "n_train_events": n_train_events,
        "note": "DL / U-Net is allowed only if Gate 1 passes.",
    }


def np_finite_gt(a, b) -> bool:
    try:
        return float(a) > float(b)
    except (TypeError, ValueError):
        return False


def evaluate_gate2(
    gate1: dict,
    *,
    event_metrics_ok: bool,
    geographic_holdout_not_zero: bool,
    conformal_claim_80: bool,
    uncertainty_informative: bool,
    uncertainty_omitted: bool,
) -> dict:
    checks = {
        "gate1": bool(gate1.get("pass")),
        "event_metrics_reported": event_metrics_ok,
        "geographic_holdout_not_collapsed": geographic_holdout_not_zero,
        "no_a_priori_80pct_claim": not conformal_claim_80,
        "uncertainty_ok": uncertainty_informative or uncertainty_omitted,
    }
    failed = [k for k, ok in checks.items() if not ok]
    return {
        "gate": 2,
        "pass": not failed,
        "failed": failed,
        "checks": checks,
        "note": "Catalog VALIDATED only if Gate 2 passes. Public API stays UNAVAILABLE otherwise.",
    }


def event_independence_report(samples: Sequence[SpatialForecastSample]) -> dict:
    """Extra Gate B diagnostics. Does not change the official <20 FAIL rule."""
    inv = inventory(samples) if samples else {"n_independent_events": 0, "event_ids": [], "cities": []}
    from floodlens.ml.spatial.events import assign_event_ids
    from floodlens.ml.spatial.event_expansion import flood_mechanism_for_date

    assign_event_ids(samples)
    by_split = {"train": set(), "val": set(), "test": set()}
    by_year: dict = {}
    by_region: dict = {}
    by_mechanism: dict = {}
    years_per_region: dict = {}
    for sample in samples or []:
        eid = (sample.extra or {}).get("event_id")
        if not eid:
            continue
        if sample.split in by_split:
            by_split[sample.split].add(eid)
        year = (sample.valid_at or "")[:4]
        by_year.setdefault(year, set()).add(eid)
        by_region.setdefault(sample.city_id, set()).add(eid)
        years_per_region.setdefault(sample.city_id, set()).add(year)
        mech = flood_mechanism_for_date(sample.valid_at, sample.city_id)
        by_mechanism.setdefault(mech, set()).add(eid)
        sample.extra["flood_mechanism"] = mech
    n = int(inv.get("n_independent_events") or 0)
    leak = same_event_in_train_and_test(samples) if samples else []
    leak_tv = same_event_across_splits(samples, "train", "val") if samples else []
    leak_vt = same_event_across_splits(samples, "val", "test") if samples else []
    split_counts = {k: len(v) for k, v in by_split.items()}
    min_split = min(split_counts.values()) if samples else 0
    if n < GATE0_MIN_EVENTS:
        research = "FAIL"
    elif n < GATE_B_RESEARCH_PASS_EVENTS:
        research = "PROVISIONAL"
    else:
        research = "PASS"
    return {
        "n_independent_events": n,
        "train_events": split_counts.get("train", 0),
        "validation_events": split_counts.get("val", 0),
        "test_events": split_counts.get("test", 0),
        "train_event_ids": sorted(by_split["train"]),
        "validation_event_ids": sorted(by_split["val"]),
        "test_event_ids": sorted(by_split["test"]),
        "events_per_year": {k: len(v) for k, v in sorted(by_year.items())},
        "events_per_region": {k: len(v) for k, v in sorted(by_region.items())},
        "years_per_region": {k: sorted(v) for k, v in sorted(years_per_region.items())},
        "events_per_mechanism": {k: len(v) for k, v in sorted(by_mechanism.items())},
        "minimum_event_count_in_any_split": min_split,
        "duplicate_event_detection": {
            "train_test": leak,
            "train_val": leak_tv,
            "val_test": leak_vt,
            "clean": not (leak or leak_tv or leak_vt),
        },
        "official_status": "PASS" if n >= GATE0_MIN_EVENTS and not (leak or leak_tv or leak_vt) else "FAIL",
        "research_recommendation": research,
        "research_rule": (
            f"Official Gate B FAIL if <{GATE0_MIN_EVENTS}. "
            f"Research: PROVISIONAL {GATE_B_PROVISIONAL_EVENTS}–{GATE_B_RESEARCH_PASS_EVENTS - 1}; "
            f"PASS ≥{GATE_B_RESEARCH_PASS_EVENTS} with no split leaks. Not a silent definition change."
        ),
    }


def evaluate_gates_af(
    samples: Sequence[SpatialForecastSample],
    audit: Optional[dict] = None,
    *,
    manifests_written: bool = False,
) -> dict:
    """Phase 6.5 Gates A–F. PASS / FAIL / PENDING with machine-readable reasons. No training."""
    if audit is None:
        audit = audit_channels(samples) if samples else {"channels": {}, "n_spatial": 0}
    inv = inventory(samples) if samples else {"n_independent_events": 0, "cities": [], "pixels": {}}
    leak = same_event_in_train_and_test(samples) if samples else []
    leak_tv = same_event_across_splits(samples, "train", "val") if samples else []
    leak_vt = same_event_across_splits(samples, "val", "test") if samples else []
    labels = {s.label_kind for s in samples} if samples else set()
    synthetic = [s.scene_id for s in samples if (s.extra or {}).get("synthetic")] if samples else []
    n_spatial = int(audit.get("n_spatial") or 0)
    dem_ok = bool(samples) and all(bool(s.dem_present) and s.x_dem is not None for s in samples)
    lattice_ok = bool(samples) and (
        sum(1 for s in samples if not s.precip_is_aoi_point) >= 0.5 * len(samples)
    )
    future = []
    for s in samples or []:
        if (s.extra or {}).get("future_rain_as_feature") or any(
            k == "FORECAST" for k in (s.x_precip_hourly_kind or [])
        ):
            future.append(s.scene_id)
    cities = list(inv.get("cities") or [])
    valid_regions = 0
    if samples:
        cov = coverage_summary(samples)
        valid_regions = sum(
            1
            for r in cov.get("regions") or []
            if (r.get("valid_flood_pixels") or 0) + (r.get("valid_dry_pixels") or 0) > 0
        )

    def _status(ok: bool, pending: bool = False) -> str:
        if pending:
            return "PENDING"
        return "PASS" if ok else "FAIL"

    gate_a_ok = bool(samples) and labels == {LABEL_OBSERVED} and not synthetic and unknown_never_scored_as_dry(samples)
    gate_b_ok = int(inv.get("n_independent_events") or 0) >= GATE0_MIN_EVENTS and not leak and not leak_tv and not leak_vt
    b_report = event_independence_report(samples) if samples else event_independence_report([])
    gate_c_ok = n_spatial >= MIN_SPATIAL_CHANNELS and dem_ok and lattice_ok
    gate_d_ok = bool(samples) and not future
    unk = (inv.get("pixels") or {}).get("unknown_fraction")
    gate_e_ok = bool(samples) and unknown_never_scored_as_dry(samples) and labels == {LABEL_OBSERVED}
    gate_f_ok = valid_regions >= GATE0_MIN_REGIONS

    gates = {
        "A": {
            "name": "dataset_validity",
            "status": _status(gate_a_ok),
            "reasons": []
            if gate_a_ok
            else [
                r
                for r in [
                    "no_samples" if not samples else None,
                    "label_not_observed" if labels != {LABEL_OBSERVED} else None,
                    "synthetic_in_real" if synthetic else None,
                    "unknown_scored_as_dry" if samples and not unknown_never_scored_as_dry(samples) else None,
                ]
                if r
            ],
        },
        "B": {
            "name": "event_independence",
            "status": _status(gate_b_ok),
            "reasons": []
            if gate_b_ok
            else [
                r
                for r in [
                    f"events={inv.get('n_independent_events')} < {GATE0_MIN_EVENTS}",
                    f"train_test_leak={leak}" if leak else None,
                    f"train_val_leak={leak_tv}" if leak_tv else None,
                    f"val_test_leak={leak_vt}" if leak_vt else None,
                ]
                if r
            ],
            "n_independent_events": inv.get("n_independent_events"),
            "train_events": b_report.get("train_events"),
            "validation_events": b_report.get("validation_events"),
            "test_events": b_report.get("test_events"),
            "events_per_year": b_report.get("events_per_year"),
            "events_per_region": b_report.get("events_per_region"),
            "minimum_event_count_in_any_split": b_report.get("minimum_event_count_in_any_split"),
            "duplicate_event_detection": b_report.get("duplicate_event_detection"),
            "research_recommendation": b_report.get("research_recommendation"),
            "research_rule": b_report.get("research_rule"),
        },
        "C": {
            "name": "spatial_feature_sufficiency",
            "status": _status(gate_c_ok),
            "reasons": []
            if gate_c_ok
            else [
                r
                for r in [
                    f"spatial_channels={n_spatial} < {MIN_SPATIAL_CHANNELS}" if n_spatial < MIN_SPATIAL_CHANNELS else None,
                    "dem_missing" if not dem_ok else None,
                    "precip_lattice_point_broadcast" if not lattice_ok else None,
                ]
                if r
            ],
            "n_spatial_channels": n_spatial,
        },
        "D": {
            "name": "temporal_causality",
            "status": _status(gate_d_ok),
            "reasons": [] if gate_d_ok else (["no_samples"] if not samples else ["future_rain_in_lookback"]),
        },
        "E": {
            "name": "label_quality",
            "status": _status(gate_e_ok),
            "reasons": []
            if gate_e_ok
            else [
                r
                for r in [
                    "no_samples" if not samples else None,
                    "unknown_scored_as_dry" if samples and not unknown_never_scored_as_dry(samples) else None,
                    "label_not_observed" if labels != {LABEL_OBSERVED} else None,
                ]
                if r
            ],
            "unknown_fraction": unk,
        },
        "F": {
            "name": "geographic_diversity",
            "status": _status(gate_f_ok),
            "reasons": [] if gate_f_ok else [f"regions={len(cities)} valid_regions={valid_regions} < {GATE0_MIN_REGIONS}"],
            "cities": cities,
            "valid_regions": valid_regions,
            "events_per_region": b_report.get("events_per_region"),
            "events_per_mechanism": b_report.get("events_per_mechanism"),
            "events_per_year": b_report.get("events_per_year"),
            "years_per_region": b_report.get("years_per_region"),
            "split_event_counts": {
                "train": b_report.get("train_events"),
                "validation": b_report.get("validation_events"),
                "test": b_report.get("test_events"),
            },
            "geographic_holdout_iou": "PENDING",
            "note": (
                "Official Gate F: ≥3 AOIs with valid GFM. Extra fields report events/years/mechanisms. "
                "Holdout IoU is not evaluated (no model training)."
            ),
        },
        "G": {"name": "baseline_competitiveness", "status": "PENDING", "reasons": ["no_model_training_in_phase_6_5"]},
        "H": {"name": "uncertainty_calibration", "status": "PENDING", "reasons": ["no_model_training_in_phase_6_5"]},
        "I": {
            "name": "reproducibility",
            "status": "PASS" if manifests_written else "PENDING",
            "reasons": [] if manifests_written else ["split_manifests_not_written"],
        },
        "J": {"name": "physics_comparability", "status": "FAIL", "reasons": ["COMPARISON NOT YET COMPARABLE"]},
    }
    return {
        "gates": gates,
        "note": "Gates G–H pending until a separate training-approval phase. Do not train here.",
    }


def cnn_refusal(audit: dict, gate1: Optional[dict] = None) -> Optional[str]:
    reason = refuse_cnn(audit)
    if reason:
        return reason
    if gate1 is not None and not gate1.get("pass"):
        return f"CNN refused: Gate 1 failed ({gate1.get('failed')})."
    return None
