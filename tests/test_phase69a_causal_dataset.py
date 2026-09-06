"""Phase 6.9A causal dataset construction. No training. No fabricated NWP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_VINTAGE,
    MODELLED_STATE,
    OBSERVED_LOOKBACK,
    POST_T0_OBSERVATION_STATUS,
    UNAVAILABLE,
    issue_at_or_before_t0,
    last_available_nwp_run,
    state_timestamp_at_or_before_t0,
    valid_time_in_target_interval,
)
from floodlens.ml.spatial.hydro_t0 import classify_staleness, reindex_glofas_q_at_t0
from floodlens.ml.spatial.phase68a import delta_t_hours
from floodlens.ml.spatial.phase69a import (
    ELIG_FULL,
    ELIG_PARTIAL,
    ELIG_STATE,
    classify_eligibility,
    evaluate_phase69a,
    pair_causal_row,
)
from floodlens.ml.spatial.provenance_spatial import provenance_complete
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status


def _pair(**kwargs):
    row = {
        "pair_id": "evt:2018-06-06|dhaka_ne|a|b",
        "event_id": "evt:2018-06-06",
        "city_id": "dhaka_ne",
        "region": "dhaka_ne",
        "split": "train",
        "flood_mechanism": "monsoon_riverine",
        "t0": "2018-06-06T12:00:00Z",
        "t1": "2018-06-18T12:00:00Z",
        "delta_t_hours": 288.0,
        "joint_valid_fraction": 0.6,
        "unknown_fraction": 0.4,
        "fraction_newly_flooded": 0.03,
        "rainfall_pre_t0": {"n_hours_required": 72, "n_hours_present": 72, "rainfall_complete": True},
        "rainfall_in_horizon": {
            "n_hours_required": 288,
            "n_hours_present": 288,
            "rainfall_complete": True,
            "forcing_class": "FORCING_COMPLETE",
        },
    }
    row.update(kwargs)
    return row


def _discharge():
    times = []
    values = []
    start = datetime(2018, 5, 1, tzinfo=timezone.utc)
    for i in range(80):
        day = start + timedelta(days=i)
        times.append(day.strftime("%Y-%m-%d"))
        values.append(10.0 + i)
    times_2022 = []
    values_2022 = []
    start2 = datetime(2022, 5, 1, tzinfo=timezone.utc)
    for i in range(60):
        day = start2 + timedelta(days=i)
        times_2022.append(day.strftime("%Y-%m-%d"))
        values_2022.append(20.0)
    times_2024 = []
    values_2024 = []
    start4 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    for i in range(80):
        day = start4 + timedelta(days=i)
        times_2024.append(day.strftime("%Y-%m-%d"))
        values_2024.append(30.0)
    return {
        "cities": {
            "dhaka": {"time": times + times_2022 + times_2024, "river_discharge_m3s": values + values_2022 + values_2024},
            "sunamganj": {"time": times + times_2022 + times_2024, "river_discharge_m3s": values + values_2022 + values_2024},
            "sylhet": {"time": times + times_2022 + times_2024, "river_discharge_m3s": values + values_2022 + values_2024},
        }
    }


def test_glofas_reindex_state_time_at_or_before_t0():
    t0 = "2018-06-06T12:00:00Z"
    row = reindex_glofas_q_at_t0(t0, "dhaka_ne", discharge=_discharge())
    assert row["status"] == MODELLED_STATE
    assert row["glofas_q_date"] == "2018-06-05"
    assert row["glofas_state_time"] == "2018-06-06T00:00:00Z"
    assert state_timestamp_at_or_before_t0(row["glofas_state_time"], t0)
    assert row["lag_hours"] == 12.0
    assert row["kind"] == "modelled"
    assert row["status"] != FORECAST_VINTAGE


def test_staleness_classification():
    assert classify_staleness(12.0) == "FRESH"
    assert classify_staleness(24.0) == "FRESH"
    assert classify_staleness(36.0) == "STALE"
    assert classify_staleness(72.0) == "STALE"
    assert classify_staleness(96.0) == "VERY_STALE"
    assert classify_staleness(None) == "MISSING"


def test_issue_time_and_valid_time_rules():
    t0 = "2018-06-06T12:00:00Z"
    t1 = "2018-06-18T12:00:00Z"
    assert issue_at_or_before_t0("2018-06-06T06:00:00Z", t0)
    assert issue_at_or_before_t0("2018-06-06T12:00:01Z", t0) is False
    assert valid_time_in_target_interval("2018-06-06T13:00:00Z", t0, t1)
    assert valid_time_in_target_interval("2018-06-06T12:00:00Z", t0, t1) is False
    assert valid_time_in_target_interval("2018-06-18T12:00:00Z", t0, t1)
    assert valid_time_in_target_interval("2018-06-18T12:00:01Z", t0, t1) is False
    run = last_available_nwp_run(t0)
    assert run is not None
    assert run.hour == 6
    assert (run.year, run.month, run.day) == (2018, 6, 6)


def test_forecast_observed_distinction_and_post_t0_exclusion():
    row = pair_causal_row(
        _pair(),
        discharge=_discharge(),
        cache_dir=None,
        acquire_forecast=False,
        retrieval_time="2026-09-03T00:00:00Z",
    )
    assert row["in_horizon_obs_status"] == POST_T0_OBSERVATION_STATUS
    assert row["in_horizon_as_forecast_input"] is False
    assert row["antecedent_rain_status"] == OBSERVED_LOOKBACK
    assert row["forecast_coverage_fraction"] == 0.0
    assert row["forecast"]["forecast_status"] == UNAVAILABLE
    assert row["eligibility"] == ELIG_STATE
    assert abs(delta_t_hours(row["t0"], row["t1"]) - 288.0) < 1e-6


def test_pair_eligibility_full_partial_state():
    assert classify_eligibility(state_ok=True, forecast_frac=1.0, obs_in_horizon=True) == ELIG_FULL
    assert classify_eligibility(state_ok=True, forecast_frac=0.5, obs_in_horizon=True) == ELIG_PARTIAL
    assert classify_eligibility(state_ok=True, forecast_frac=0.0, obs_in_horizon=True) == ELIG_STATE
    assert (
        classify_eligibility(state_ok=False, forecast_frac=0.0, obs_in_horizon=True)
        == "OBSERVATIONAL_ONLY"
    )
    assert classify_eligibility(state_ok=False, forecast_frac=0.0, obs_in_horizon=False) == UNAVAILABLE


def test_train_val_test_coverage_and_provenance(tmp_path: Path):
    pairs = [
        _pair(),
        _pair(
            pair_id="evt:2018-06-06|dhaka_nw|a|b",
            city_id="dhaka_nw",
            region="dhaka_nw",
            split="val",
            event_id="evt:2019-01-10",
            t0="2018-06-07T12:00:00Z",
            t1="2018-06-19T12:00:00Z",
        ),
        _pair(
            pair_id="evt:2022-05-16|dhaka_sw|a|b",
            city_id="dhaka_sw",
            region="dhaka_sw",
            split="test",
            event_id="evt:2022-05-16",
            t0="2022-05-16T12:00:00Z",
            t1="2022-05-28T12:00:00Z",
        ),
    ]
    report = evaluate_phase69a(
        pairs=pairs,
        discharge=_discharge(),
        out_dir=tmp_path / "r1",
        cache_dir=tmp_path / "cache",
        acquire_forecast=False,
        write_docs=False,
    )
    assert report["counts"]["n_pairs"] == 3
    assert report["counts"]["n_full_causal"] == 0
    assert report["counts"]["n_state_only"] == 3
    assert report["counts"]["n_train_events_full"] == 0
    assert report["counts"]["n_val_events_full"] == 0
    assert report["counts"]["n_test_events_full"] == 0
    assert report["decision_letter"] == "C"
    assert report["provenance"]["complete"] is True
    assert provenance_complete(report["provenance"]["envelope"]) is True
    assert (tmp_path / "r1" / "causal_pair_inventory.csv").exists()
    assert (tmp_path / "r1" / "causal_forcing_summary.json").exists()
    assert (tmp_path / "r1" / "hydrology_t0_alignment.csv").exists()
    assert (tmp_path / "r1" / "forecast_vintage_manifest.json").exists()
    assert report["cnn_trained"] is False
    assert report["model_training"] == "NOT AUTHORIZED"


def test_phase69a_deterministic_and_no_training(tmp_path: Path):
    pairs = [_pair(), _pair(pair_id="dup2", city_id="dhaka_nw", region="dhaka_nw")]
    a = evaluate_phase69a(
        pairs=pairs,
        discharge=_discharge(),
        out_dir=tmp_path / "a",
        cache_dir=tmp_path / "ca",
        acquire_forecast=False,
        write_docs=False,
    )
    b = evaluate_phase69a(
        pairs=pairs,
        discharge=_discharge(),
        out_dir=tmp_path / "b",
        cache_dir=tmp_path / "cb",
        acquire_forecast=False,
        write_docs=False,
    )
    assert a["counts"]["n_state_only"] == b["counts"]["n_state_only"]
    assert a["decision_letter"] == b["decision_letter"]
    assert a["hydrology_summary"]["n_modelled_state"] == 2
    md = (tmp_path / "a" / "PHASE_6_9A_CAUSAL_DATASET_REPORT.md").read_text(encoding="utf-8")
    assert "NOT_VALIDATED" in md
    assert "MODELLED_STATE" in md
    assert "NOT AUTHORIZED" in md


def test_phase69a_does_not_train_or_touch_solver():
    spatial = load_spatial_registry()
    aoi = load_registry()
    blobs = [
        Path("src/floodlens/ml/spatial/phase69a.py").read_text(encoding="utf-8"),
        Path("src/floodlens/ml/spatial/hydro_t0.py").read_text(encoding="utf-8"),
        Path("src/floodlens/ml/spatial/forecast_acquire.py").read_text(encoding="utf-8"),
        Path("scripts/phase69a_causal_dataset.py").read_text(encoding="utf-8"),
    ]
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "BoostingModel" not in blob
        assert "LogisticModel" not in blob
        assert "mark_spatial_validated" not in blob
        assert "TinyUNet" not in blob
    assert public_spatial_status(spatial) != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
