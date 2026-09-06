"""Phase 6.9B forecast-vintage expansion. No training. No fabricated NWP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_VINTAGE,
    issue_at_or_before_t0,
    last_available_nwp_run,
    state_timestamp_at_or_before_t0,
    valid_time_in_target_interval,
)
from floodlens.ml.spatial.phase69b import evaluate_phase69b
from floodlens.ml.spatial.provenance_spatial import provenance_complete
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.vintage_steps import accumulate_forecast_precip, coverage_from_accumulation_windows
from floodlens.ml.spatial.wb2_hres import WB2_REGRID, WB2_SOURCE_RESOLUTION, wb2_eligible


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
        "rainfall_pre_t0": {"n_hours_required": 72, "n_hours_present": 72},
        "rainfall_in_horizon": {"n_hours_required": 288, "n_hours_present": 288},
    }
    row.update(kwargs)
    return row


def _discharge():
    times, values = [], []
    for year, start, n, q0 in (
        (2018, datetime(2018, 5, 1, tzinfo=timezone.utc), 80, 10.0),
        (2019, datetime(2019, 7, 1, tzinfo=timezone.utc), 40, 12.0),
        (2022, datetime(2022, 5, 1, tzinfo=timezone.utc), 40, 15.0),
    ):
        for i in range(n):
            day = start + timedelta(days=i)
            times.append(day.strftime("%Y-%m-%d"))
            values.append(q0)
    cities = {c: {"time": times, "river_discharge_m3s": values} for c in ("dhaka", "sunamganj", "sylhet")}
    return {"cities": cities}


def _wb2_cache(tmp: Path, issue: str = "2018-06-06T00:00:00Z") -> Path:
    cache = tmp / "wb2"
    cache.mkdir(parents=True)
    series = []
    t0 = datetime.fromisoformat(issue.replace("Z", "+00:00"))
    for lead in range(6, 241, 6):
        valid = t0 + timedelta(hours=lead)
        series.append(
            {
                "lead_hours": float(lead),
                "valid_time": valid.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "precipitation_mm": 1.0,
            }
        )
    payload = {
        "status": "OK",
        "provider": "test",
        "model": "IFS HRES operational (WB2)",
        "cycle": "00UTC",
        "issue_time": issue,
        "points": {
            "dhaka": {
                "grid_lat": 24.0,
                "grid_lon": 90.0,
                "series": series,
            }
        },
        "source_resolution": WB2_SOURCE_RESOLUTION,
        "regridding_method": WB2_REGRID,
        "processing_version": "test",
        "license": "test",
    }
    (cache / "wb2_hres_20180606T0000.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    return cache


def test_issue_and_valid_time_integrity():
    t0 = "2018-06-06T12:00:00Z"
    t1 = "2018-06-18T12:00:00Z"
    assert issue_at_or_before_t0("2018-06-06T00:00:00Z", t0)
    assert issue_at_or_before_t0("2018-06-06T12:00:01Z", t0) is False
    assert valid_time_in_target_interval("2018-06-06T13:00:00Z", t0, t1)
    assert valid_time_in_target_interval(t0, t0, t1) is False
    assert valid_time_in_target_interval("2018-06-18T12:00:01Z", t0, t1) is False
    run = last_available_nwp_run(t0, cycles=(0, 12), latency_hours=6)
    assert run.hour == 0
    assert wb2_eligible(t0)["eligible"] is True
    assert wb2_eligible("2015-07-11T12:00:00Z")["eligible"] is False


def test_no_hindsight_and_accumulation():
    t0, t1 = "2018-06-06T12:00:00Z", "2018-06-07T12:00:00Z"
    windows = [
        ("2018-06-06T18:00:00Z", 6.0, 1.0),
        ("2018-06-07T00:00:00Z", 6.0, 2.0),
        ("2018-06-07T06:00:00Z", 6.0, 3.0),
        ("2018-06-07T12:00:00Z", 6.0, 4.0),
    ]
    cov = coverage_from_accumulation_windows(
        issue_time="2018-06-06T00:00:00Z", t0=t0, t1=t1, windows=windows
    )
    assert cov["forecast_status"] == FORECAST_VINTAGE
    assert cov["forecast_issue_ok"] is True
    assert cov["forecast_filled"] is False
    assert cov["precip_sum_mm"] == 10.0
    assert accumulate_forecast_precip([(a, b) for a, _, b in windows], t0, t1) == 10.0
    bad = coverage_from_accumulation_windows(
        issue_time="2018-06-07T00:00:00Z", t0=t0, t1=t1, windows=windows
    )
    assert bad["forecast_issue_ok"] is False
    assert bad["forecast_coverage_fraction"] == 0.0


def test_native_grid_metadata_not_highres():
    assert "1.5" in WB2_SOURCE_RESOLUTION
    assert "20 m" in WB2_REGRID or "20 m" in WB2_REGRID.lower() or "no 20 m" in WB2_REGRID


def test_missing_forcing_and_classification(tmp_path: Path):
    report = evaluate_phase69b(
        pairs=[_pair()],
        discharge=_discharge(),
        out_dir=tmp_path / "out",
        ifs_cache=tmp_path / "ifs",
        wb2_cache=tmp_path / "empty_wb2",
        acquire_forecast=False,
        write_docs=False,
    )
    row = report["pairs"][0]
    assert row["eligibility"] == "STATE_ONLY"
    assert row["forecast_coverage_fraction"] == 0.0
    assert row["in_horizon_as_forecast_input"] is False
    assert state_timestamp_at_or_before_t0(row["hydrology"]["glofas_state_time"], row["t0"])


def test_wb2_cache_partial_causal_and_splits(tmp_path: Path):
    wb2 = _wb2_cache(tmp_path)
    pairs = [
        _pair(),
        _pair(
            pair_id="val1",
            event_id="evt:2019-06-15",
            split="val",
            t0="2018-06-06T12:00:00Z",
            t1="2018-06-10T12:00:00Z",
            delta_t_hours=96.0,
        ),
        _pair(
            pair_id="test1",
            event_id="evt:2022-05-16",
            split="test",
            city_id="dhaka_sw",
            t0="2018-06-06T12:00:00Z",
            t1="2018-06-18T12:00:00Z",
            delta_t_hours=288.0,
        ),
    ]
    a = evaluate_phase69b(
        pairs=pairs,
        discharge=_discharge(),
        out_dir=tmp_path / "r1",
        ifs_cache=tmp_path / "ifs",
        wb2_cache=wb2,
        acquire_forecast=False,
        write_docs=False,
    )
    b = evaluate_phase69b(
        pairs=pairs,
        discharge=_discharge(),
        out_dir=tmp_path / "r2",
        ifs_cache=tmp_path / "ifs2",
        wb2_cache=wb2,
        acquire_forecast=False,
        write_docs=False,
    )
    assert a["counts"]["n_pairs"] == b["counts"]["n_pairs"] == 3
    assert a["counts"]["n_full_causal"] + a["counts"]["n_partial_causal"] == 3
    assert a["counts"]["n_train_events_causal"] == 1
    assert a["counts"]["n_val_events_causal"] == 1
    assert a["counts"]["n_test_events_causal"] == 1
    assert a["provenance"]["complete"] is True
    assert provenance_complete(a["provenance"]["envelope"]) is True
    assert (tmp_path / "r1" / "forecast_vintage_pairs.csv").exists()
    assert (tmp_path / "r1" / "forecast_vintage_coverage.json").exists()
    assert (tmp_path / "r1" / "forecast_vintage_sources.json").exists()
    assert a["cnn_trained"] is False
    assert a["model_training"] == "NOT AUTHORIZED"
    md = (tmp_path / "r1" / "PHASE_6_9B_FORECAST_VINTAGE_EXPANSION_REPORT.md").read_text(encoding="utf-8")
    assert "NOT_VALIDATED" in md
    assert "MODELLED_STATE" in md


def test_live_artifacts_train_val_test_if_present():
    cov = Path("src/floodlens/application/data/ml/spatial/phase69b/forecast_vintage_coverage.json")
    if not cov.exists():
        return
    data = __import__("json").loads(cov.read_text(encoding="utf-8"))
    c = data["counts"]
    assert c["n_pairs"] == 183
    assert c["n_independent_events"] == 15
    assert data["hydro_status"] == "MODELLED_STATE_AT_T0"
    assert data["model_training"] == "NOT AUTHORIZED"
    assert data["integrity"]["era5_in_horizon_as_forecast"] is False
    assert data["integrity"]["issue_time_le_t0"] is True
    assert c["n_train_events_causal"] >= 2
    assert c["n_val_events_causal"] >= 2
    assert c["n_test_events_causal"] >= 1
    assert data["cnn_trained"] is False
    assert data["solver_modified"] is False


def test_phase69b_does_not_train_or_touch_solver():
    spatial = load_spatial_registry()
    aoi = load_registry()
    blobs = [
        Path("src/floodlens/ml/spatial/phase69b.py").read_text(encoding="utf-8"),
        Path("src/floodlens/ml/spatial/wb2_hres.py").read_text(encoding="utf-8"),
        Path("scripts/phase69b_forecast_vintage.py").read_text(encoding="utf-8"),
    ]
    for blob in blobs:
        assert "fit_unet" not in blob
        assert "BoostingModel" not in blob
        assert "LogisticModel" not in blob
        assert "mark_spatial_validated" not in blob
        assert "TinyUNet" not in blob
    assert public_spatial_status(spatial) != "VALIDATED"
    assert public_status(aoi) == "VALIDATED"
