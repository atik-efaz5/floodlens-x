"""Phase 6.9 causal forcing audit. No training. No fabricated NWP."""

from __future__ import annotations

from pathlib import Path

import pytest

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_AVAILABLE,
    KIND_FORECAST,
    KIND_REANALYSIS,
    OBSERVED_AVAILABLE,
    POST_T0_OBSERVATION,
    UNAVAILABLE,
    ForecastForcing,
    classify_precip,
    cube_issue_192h,
    issue_at_or_before_t0,
    reject_hindsight_forecast,
)
from floodlens.ml.spatial.phase68a import delta_t_hours
from floodlens.ml.spatial.phase69 import (
    evaluate_phase69,
    hydro_alignment,
    pair_forcing_row,
)
from floodlens.ml.spatial.provenance_spatial import provenance_complete
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status


def _pair(**kwargs):
    row = {
        "pair_id": "evt:2018-06-06|sunamganj|a|b",
        "event_id": "evt:2018-06-06",
        "city_id": "sunamganj",
        "split": "train",
        "t0": "2018-06-06T12:00:00Z",
        "t1": "2018-06-18T12:00:00Z",
        "delta_t_hours": 288.0,
        "joint_valid_fraction": 0.6,
        "unknown_fraction": 0.4,
        "fraction_newly_flooded": 0.03,
        "fraction_receding": 0.02,
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


def test_issue_time_must_be_at_or_before_t0():
    t0 = "2018-06-06T12:00:00Z"
    assert issue_at_or_before_t0("2018-06-06T12:00:00Z", t0)
    assert issue_at_or_before_t0("2018-06-06T00:00:00Z", t0)
    assert issue_at_or_before_t0("2018-06-06T12:00:01Z", t0) is False


def test_forecast_observed_status_distinction():
    t0 = "2018-06-06T12:00:00Z"
    assert classify_precip(window="pre_t0", kind=KIND_REANALYSIS, issue_time=None, t0=t0) == OBSERVED_AVAILABLE
    assert classify_precip(window="in_horizon", kind=KIND_REANALYSIS, issue_time=None, t0=t0) == POST_T0_OBSERVATION
    assert (
        classify_precip(window="in_horizon", kind=KIND_FORECAST, issue_time="2018-06-06T00:00:00Z", t0=t0)
        == FORECAST_AVAILABLE
    )
    assert (
        classify_precip(window="in_horizon", kind=KIND_FORECAST, issue_time="2018-06-07T00:00:00Z", t0=t0)
        == POST_T0_OBSERVATION
    )


def test_no_post_t0_forecast_inputs():
    t0 = "2018-06-06T12:00:00Z"
    bad = ForecastForcing(
        source="fake",
        provider="test",
        issue_time="2018-06-07T00:00:00Z",
        valid_start=t0,
        valid_end="2018-06-18T12:00:00Z",
        lead_time_hours=24,
        variable="precipitation",
        units="mm",
        spatial_resolution="1deg",
        temporal_resolution="hourly",
        coverage="test",
        status="ok",
        kind=KIND_FORECAST,
        availability=FORECAST_AVAILABLE,
        acquired=True,
        filled=False,
    )
    err = reject_hindsight_forecast(bad, t0)
    assert err is not None
    assert "issue_time > t0" in err
    era5 = ForecastForcing(
        source="era5",
        provider="test",
        issue_time=None,
        valid_start=t0,
        valid_end="2018-06-18T12:00:00Z",
        lead_time_hours=288,
        variable="precipitation",
        units="mm",
        spatial_resolution="11km",
        temporal_resolution="hourly",
        coverage="aoi",
        status="FORCING_COMPLETE",
        kind=KIND_REANALYSIS,
        availability=POST_T0_OBSERVATION,
        acquired=True,
        filled=False,
    )
    assert reject_hindsight_forecast(era5, t0) is None
    row = pair_forcing_row(_pair())
    assert row["obs_in_horizon_as_forecast_input"] is False
    assert row["forecast_forcing_available"] is False
    assert row["obs_in_horizon_availability"] == POST_T0_OBSERVATION


def test_target_b_alignment_and_delta_t():
    row = pair_forcing_row(_pair())
    assert row["t0"] == "2018-06-06T12:00:00Z"
    assert abs(row["delta_t_hours"] - 288.0) < 1e-6
    assert abs(delta_t_hours(row["t0"], row["t1"]) - 288.0) < 1e-6
    assert row["delta_t_bucket"] == "10-14 days"
    cube = cube_issue_192h(row["t1"])
    assert cube == "2018-06-10T12:00:00Z"  # t1 − 192 h = t0 + 96 h → after t0
    hydro = hydro_alignment(row["t0"], row["t1"])
    assert hydro["status"] == "POST_T0"


def test_hydrology_timestamp_stale_when_delta_shorter_than_192h():
    hydro = hydro_alignment("2018-06-06T12:00:00Z", "2018-06-10T12:00:00Z")
    # Δt=96 h; cube issue = t1-192 = t0-96 h → before t0, stale
    assert hydro["status"] == "CAUSAL_BUT_STALE"


def test_forcing_coverage_zero_without_nwp():
    row = pair_forcing_row(_pair())
    assert row["forecast_coverage_fraction"] == 0.0
    assert row["forecast_status"] == UNAVAILABLE
    assert (row["hypothetical_coverage"] or {}).get("tigge_15d") == pytest.approx(1.0)


def test_provenance_complete():
    report = evaluate_phase69(
        pairs=[_pair(), _pair(event_id="evt:2020-06-07", pair_id="e2|sunamganj|a|b", t0="2020-06-07T12:00:00Z", t1="2020-06-19T12:00:00Z")],
        out_dir=None,
        write_artifacts=False,
        write_docs=False,
    )
    assert report["provenance"]["complete"] is True
    assert provenance_complete(report["provenance"]["envelope"]) is True


def test_phase69_deterministic_and_no_training(tmp_path: Path):
    pairs = [
        _pair(),
        _pair(
            event_id="evt:2022-05-16",
            pair_id="evt:2022-05-16|sylhet|a|b",
            city_id="sylhet",
            split="test",
            t0="2022-05-16T12:00:00Z",
            t1="2022-05-28T12:00:00Z",
        ),
    ]
    a = evaluate_phase69(pairs=pairs, out_dir=tmp_path / "r1", write_docs=False)
    b = evaluate_phase69(pairs=pairs, out_dir=tmp_path / "r2", write_docs=False)
    assert a["counts"]["n_pairs"] == b["counts"]["n_pairs"] == 2
    assert a["decision_letter"] == b["decision_letter"] == "F"
    assert a["promoted_to_validated"] is False
    assert a["cnn_trained"] is False
    assert a["model_training"] == "NOT AUTHORIZED"
    assert a["spatial_api"] == "UNAVAILABLE"
    assert (tmp_path / "r1" / "forecast_sources.json").exists()
    assert (tmp_path / "r1" / "targetb_forcing_audit.json").exists()
    assert (tmp_path / "r1" / "pair_forcing_coverage.csv").exists()
    md = (tmp_path / "r1" / "PHASE_6_9_CAUSAL_FORCING_AUDIT.md").read_text(encoding="utf-8")
    assert "NOT_VALIDATED" in md
    assert "6.9A" in md
    gates = (a.get("gates") or {}).get("gates") or {}
    assert gates["6.9B"]["status"] == "FAIL"
    assert gates["6.9E"]["status"] == "PASS"
    assert gates["6.9A"]["status"] == "PASS"


def test_phase69_does_not_train_or_touch_solver():
    spatial = load_spatial_registry()
    aoi = load_registry()
    src = Path("src/floodlens/ml/spatial/phase69.py").read_text(encoding="utf-8")
    schema = Path("src/floodlens/ml/spatial/forecast_forcing.py").read_text(encoding="utf-8")
    script = Path("scripts/phase69_causal_forcing.py").read_text(encoding="utf-8")
    for blob in (src, schema, script):
        assert "fit_unet" not in blob
        assert "BoostingModel" not in blob
        assert "LogisticModel" not in blob
        assert "mark_spatial_validated" not in blob
        assert "TinyUNet" not in blob
    assert public_spatial_status(spatial) != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
