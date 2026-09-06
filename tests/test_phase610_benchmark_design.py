"""Phase 6.10 partial-causal Target-B design. No training. No filled forcing."""

from __future__ import annotations

from pathlib import Path

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_BENCHMARK_ELIGIBLE,
    TARGET_B_PRIMARY_LABEL,
    causal_timestamp_violations,
    issue_at_or_before_t0,
    state_timestamp_at_or_before_t0,
    valid_time_in_target_interval,
)
from floodlens.ml.spatial.phase610 import (
    evaluate_phase610,
    is_forecast_eligible,
)
from floodlens.ml.spatial.provenance_spatial import provenance_complete
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.vintage_steps import pm_from_windows


def _row(**kwargs):
    rec = {
        "pair_id": "p1",
        "event_id": "evt:2018-06-06",
        "city_id": "dhaka_ne",
        "region": "dhaka_ne",
        "split": "train",
        "year": 2018,
        "t0": "2018-06-06T12:00:00Z",
        "t1": "2018-06-18T12:00:00Z",
        "delta_t_hours": 288.0,
        "delta_t_days": 12.0,
        "delta_t_bucket": "10-14 days",
        "eligibility": "PARTIAL_CAUSAL",
        "forecast_status": "FORECAST_VINTAGE",
        "forecast_source": "wb2",
        "forecast_coverage_fraction": 0.79,
        "forecast_lead_min": 6.0,
        "forecast_lead_max": 240.0,
        "hydrology_status": "MODELLED_STATE",
        "glofas_state_time": "2018-06-06T00:00:00Z",
        "in_horizon_as_forecast_input": False,
    }
    rec.update(kwargs)
    return rec


def test_pm_mask_rejects_hindsight_and_does_not_fill():
    t0, t1 = "2018-06-06T12:00:00Z", "2018-06-07T12:00:00Z"
    windows = [
        ("2018-06-06T18:00:00Z", 6.0, 1.0),
        ("2018-06-07T00:00:00Z", 6.0, 2.0),
        ("2018-06-07T06:00:00Z", 6.0, 3.0),
        ("2018-06-07T12:00:00Z", 6.0, 4.0),
    ]
    ok = pm_from_windows(issue_time="2018-06-06T00:00:00Z", t0=t0, t1=t1, windows=windows)
    assert ok["filled"] is False
    assert ok["interpolated"] is False
    assert ok["forecast_issue_ok"] is True
    assert sum(ok["hourly_mask"]) == ok["n_hours_required"]
    assert all((p is None) == (m == 0) or m == 1 for p, m in zip(ok["hourly_precipitation_mm"], ok["hourly_mask"]))
    for precip, mask in zip(ok["hourly_precipitation_mm"], ok["hourly_mask"]):
        if mask == 0:
            assert precip is None
    assert ok["precip_sum_mm"] == 10.0
    bad = pm_from_windows(issue_time="2018-06-07T00:00:00Z", t0=t0, t1=t1, windows=windows)
    assert bad["forecast_issue_ok"] is False
    assert sum(bad["hourly_mask"]) == 0
    assert all(v is None for v in bad["hourly_precipitation_mm"])


def test_pm_missing_tail_is_none_not_zero():
    t0, t1 = "2018-06-06T12:00:00Z", "2018-06-08T12:00:00Z"
    windows = [("2018-06-06T18:00:00Z", 6.0, 1.5)]
    pm = pm_from_windows(issue_time="2018-06-06T00:00:00Z", t0=t0, t1=t1, windows=windows)
    assert 0 < sum(pm["hourly_mask"]) < pm["n_hours_required"]
    for precip, mask in zip(pm["hourly_precipitation_mm"], pm["hourly_mask"]):
        if mask == 0:
            assert precip is None
            assert precip != 0.0


def test_leakage_helpers():
    t0, t1 = "2018-06-06T12:00:00Z", "2018-06-18T12:00:00Z"
    assert issue_at_or_before_t0("2018-06-06T00:00:00Z", t0)
    assert valid_time_in_target_interval("2018-06-06T18:00:00Z", t0, t1)
    assert state_timestamp_at_or_before_t0("2018-06-06T00:00:00Z", t0)
    bad = causal_timestamp_violations(
        t0=t0,
        t1=t1,
        issue_time="2018-06-06T18:00:00Z",
        valid_times=["2018-06-19T00:00:00Z"],
        state_time="2018-06-07T00:00:00Z",
        era5_in_horizon_as_forecast=True,
        filled=True,
    )
    assert "forecast issue_time > t0" in bad
    assert any("valid_time" in r for r in bad)
    assert "glofas_state_time > t0" in bad
    assert "post-t0 ERA5 used as forecast forcing" in bad
    assert "forecast record was temporally filled" in bad
    assert causal_timestamp_violations(t0=t0, t1=t1, issue_time="2018-06-06T00:00:00Z", state_time="2018-06-06T00:00:00Z") == []


def test_state_only_excluded_and_frozen_split_counts(tmp_path: Path):
    rows = [
        _row(),
        _row(pair_id="p2", event_id="evt:2017-04-12", year=2017, eligibility="PARTIAL_CAUSAL"),
        _row(
            pair_id="p3",
            event_id="evt:2015-07-11",
            year=2015,
            eligibility="STATE_ONLY",
            forecast_coverage_fraction=0.0,
            forecast_status="UNAVAILABLE",
            forecast_source="",
        ),
        _row(
            pair_id="v1",
            event_id="evt:2019-06-15",
            split="val",
            year=2019,
            eligibility="PARTIAL_CAUSAL",
            t0="2019-06-15T12:00:00Z",
            t1="2019-06-27T12:00:00Z",
            glofas_state_time="2019-06-15T00:00:00Z",
        ),
        _row(
            pair_id="v2",
            event_id="evt:2020-06-07",
            split="val",
            year=2020,
            eligibility="FULL_CAUSAL",
            forecast_coverage_fraction=1.0,
            t0="2020-06-07T12:00:00Z",
            t1="2020-06-11T12:00:00Z",
            glofas_state_time="2020-06-07T00:00:00Z",
        ),
        _row(
            pair_id="t1",
            event_id="evt:2022-05-16",
            split="test",
            year=2022,
            eligibility="PARTIAL_CAUSAL",
            t0="2022-05-16T12:00:00Z",
            t1="2022-05-28T12:00:00Z",
            glofas_state_time="2022-05-16T00:00:00Z",
        ),
        _row(
            pair_id="t2",
            event_id="evt:2023-06-16",
            split="test",
            year=2023,
            eligibility="STATE_ONLY",
            forecast_coverage_fraction=0.0,
            t0="2023-06-16T12:00:00Z",
            t1="2023-06-28T12:00:00Z",
            glofas_state_time="2023-06-16T00:00:00Z",
        ),
    ]
    report = evaluate_phase610(
        pairs=rows,
        hydro={},
        out_dir=tmp_path / "out",
        write_docs=False,
    )
    p2 = report["policies"]["policy2_forecast"]
    assert p2["train"]["n_events"] == 2
    assert p2["val"]["n_events"] == 2
    assert p2["test"]["n_events"] == 1
    assert p2["train"]["n_pairs"] == 2
    assert report["complete_case"]["train"]["n_events"] == 0
    assert report["complete_case"]["val"]["n_events"] == 1
    assert "evt:2015-07-11" not in p2["train"]["event_ids"]
    assert "evt:2023-06-16" not in p2["test"]["event_ids"]
    assert all(is_forecast_eligible(r) == (r["eligibility"] in FORECAST_BENCHMARK_ELIGIBLE) for r in rows)
    csv_path = tmp_path / "out" / "benchmark_eligibility.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert "STATE_ONLY_DIAGNOSTIC" in text
    assert "FORECAST" in text
    assert report["training_gates"]["training_authorized"] is False
    assert report["training_gates"]["state_only_excluded_from_forecast_set"] is True
    assert report["decision_letter"] == "B"
    assert TARGET_B_PRIMARY_LABEL == "NEWLY_FLOODED"
    assert report["leakage"]["ok"] is True
    assert report["provenance"]["complete"] is True
    assert provenance_complete(report["provenance"]["envelope"]) is True
    md = (tmp_path / "out" / "PHASE_6_10_PARTIAL_CAUSAL_BENCHMARK_DESIGN.md").read_text(encoding="utf-8")
    assert "NOT_VALIDATED" in md
    assert "MODELLED_STATE" in md
    assert "PARTIAL-CAUSAL BENCHMARK WITH EXPLICIT MASKING" in md


def test_live_artifacts_policy2_if_present():
    cov = Path("src/floodlens/application/data/ml/spatial/phase610/missingness_audit.json")
    if not cov.exists():
        return
    data = __import__("json").loads(cov.read_text(encoding="utf-8"))
    c = data["counts"]
    assert c["n_pairs"] == 183
    assert c["n_independent_events"] == 15
    assert c["n_full_causal"] == 12
    assert c["n_partial_causal"] == 138
    assert c["n_state_only"] == 33
    p2 = data["policies"]["policy2_forecast"]
    assert p2["train"]["n_events"] == 5
    assert p2["train"]["n_pairs"] == 42
    assert p2["val"]["n_events"] == 5
    assert p2["val"]["n_pairs"] == 76
    assert p2["test"]["n_events"] == 2
    assert p2["test"]["n_pairs"] == 32
    assert data["complete_case"]["train"]["n_events"] == 0
    assert data["model_training"] == "NOT AUTHORIZED"
    assert data["hydro_status"] == "MODELLED_STATE_AT_T0"
    assert data["training_gates"]["training_authorized"] is False
    assert data["cnn_trained"] is False
    assert data["solver_modified"] is False


def test_phase610_does_not_train_or_touch_solver():
    spatial = load_spatial_registry()
    aoi = load_registry()
    blobs = [
        Path("src/floodlens/ml/spatial/phase610.py").read_text(encoding="utf-8"),
        Path("src/floodlens/ml/spatial/vintage_steps.py").read_text(encoding="utf-8"),
        Path("scripts/phase610_benchmark_design.py").read_text(encoding="utf-8"),
    ]
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "BoostingModel" not in blob
        assert "LogisticModel" not in blob
        assert "mark_spatial_validated" not in blob
        assert "TinyUNet" not in blob
        assert "sklearn" not in blob
    assert public_spatial_status(spatial) != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
