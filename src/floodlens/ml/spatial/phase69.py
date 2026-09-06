"""Phase 6.9 causal forecast-forcing audit for Target B.

No model fitting. Does not acquire TIGGE/GloFAS-forecast rasters.
Does not treat ERA5 in (t0, t1] as a forecast input.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from floodlens.ml.leakage import hours_between, parse_ts
from floodlens.ml.real_dataset import Q_LOOKBACK_DAYS
from floodlens.ml.spatial.forecast_forcing import (
    FORECAST_AVAILABLE,
    FORECAST_SOURCES,
    KIND_MODELLED,
    KIND_REANALYSIS,
    OBSERVED_AVAILABLE,
    POST_T0_OBSERVATION,
    UNAVAILABLE,
    ForecastForcing,
    classify_precip,
    cube_issue_192h,
    hypothetical_lead_coverage,
    product_year_coverage,
    reject_hindsight_forecast,
)
from floodlens.ml.spatial.phase68a import OUT_DIR as PHASE68A_DIR
from floodlens.ml.spatial.phase68a import _finite, _jsonable, delta_t_hours
from floodlens.ml.spatial.provenance_spatial import provenance_complete, spatial_artifact_provenance
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import HORIZON_HOURS, SPATIAL_DIR

EXPERIMENT_ID = "phase6.9-causal-forcing-audit-v1"
PAIRS_PATH = PHASE68A_DIR / "transition_pairs.json"
OUT_DIR = SPATIAL_DIR / "phase69"
REPORT_JSON = SPATIAL_DIR / "phase69_eval.json"
DOCS_REPORT = Path("docs/PHASE_6_9_CAUSAL_FORCING_AUDIT.md")
CSV_NAME = "pair_forcing_coverage.csv"

DELTA_T_BINS_69 = (
    (0.0, 2.0, "0-2 days"),
    (2.0, 4.0, "2-4 days"),
    (4.0, 7.0, "4-7 days"),
    (7.0, 10.0, "7-10 days"),
    (10.0, 14.0, "10-14 days"),
    (14.0, 21.0, "14-21 days"),
    (21.0, None, "21+ days"),
)
NWP_DETERMINISTIC_HOURS = 168
NWP_ENSEMBLE_HOURS = 360
GFS_HOURS = 384
OPENMETEO_PREV_HOURS = 168
GLOFAS_FCST_HOURS = 720

DECISION_TEXT = {
    "A": "CAUSAL FORCING IS SUFFICIENT — TARGET-B BASELINES MAY BE CONSIDERED IN A SEPARATE APPROVAL",
    "B": "PARTIAL CAUSAL FORCING — SUBSET EXPERIMENT MAY BE JUSTIFIED",
    "C": "CAUSAL FORCING IS INSUFFICIENT — ACQUIRE BETTER FORECAST DATA",
    "D": "TARGET-B HORIZONS ARE TOO LONG — REFORMULATE TARGET",
    "E": "HYDROLOGICAL STATE IS THE PRIMARY MISSING INPUT",
    "F": "COMBINATION OF C + E",
}


def delta_t_bucket_69(hours: float) -> str:
    days = float(hours) / 24.0
    for lo, hi, name in DELTA_T_BINS_69:
        if hi is None:
            if days >= lo:
                return name
        elif lo <= days < hi:
            return name
    return "21+ days"


def load_targetb_pairs(path: Optional[Path] = None) -> List[dict]:
    path = Path(path or PAIRS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Phase 6.8A pair artifact missing: {path}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("transition_pairs.json must be a list")
    return rows


def last_complete_q_day(t0: str) -> str:
    """Daily Q for calendar day D includes hours after a mid-day t0. Use D−1."""
    stamp = parse_ts(t0)
    prev = (stamp.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).date()
    return prev.isoformat()


def hydro_alignment(t0: str, t1: str) -> dict:
    cube_issue = cube_issue_192h(t1)
    offset_h = hours_between(t0, cube_issue)
    cube_minus_t0 = hours_between(cube_issue, t0)
    if cube_minus_t0 > 1.0:
        status = "POST_T0"
        note = "Cube Q lookback ends after Target B t0 (leak if used as t0 hydrology)."
    elif abs(cube_minus_t0) <= 1.0:
        status = "CAUSAL_AT_T0"
        note = "Cube 192 h issue coincides with Target B t0 (only if Δt≈192 h)."
    else:
        status = "CAUSAL_BUT_STALE"
        note = "Cube Q is before t0 but not aligned to Target B t0."
    return {
        "target_b_t0": t0,
        "cube_issue_192h": cube_issue,
        "q_lookback_would_end": last_complete_q_day(t0),
        "q_lookback_days": Q_LOOKBACK_DAYS,
        "cube_issue_minus_t0_hours": cube_minus_t0,
        "t0_minus_cube_issue_hours": offset_h,
        "status": status,
        "kind": KIND_MODELLED,
        "availability_if_reindexed": OBSERVED_AVAILABLE,
        "availability_in_cube": UNAVAILABLE,
        "note": note,
    }


def pair_forcing_row(pair: dict) -> dict:
    t0 = pair["t0"]
    t1 = pair["t1"]
    dt_h = float(pair.get("delta_t_hours") if pair.get("delta_t_hours") is not None else delta_t_hours(t0, t1))
    year = int(str(t1)[:4])
    obs_in = pair.get("rainfall_in_horizon") or {}
    obs_pre = pair.get("rainfall_pre_t0") or {}
    pre_class = classify_precip(window="pre_t0", kind=KIND_REANALYSIS, issue_time=None, t0=t0)
    in_class = classify_precip(window="in_horizon", kind=KIND_REANALYSIS, issue_time=None, t0=t0)
    hydro = hydro_alignment(t0, t1)
    era5_fc = ForecastForcing(
        source="era5-land-open-meteo-lattice",
        provider="Open-Meteo / ERA5-Land",
        issue_time=None,
        valid_start=t0,
        valid_end=t1,
        lead_time_hours=dt_h,
        variable="precipitation",
        units="mm",
        spatial_resolution="~11 km lattice",
        temporal_resolution="hourly",
        coverage="Bangladesh AOI lattice" if obs_in.get("rainfall_complete") else "incomplete or missing",
        status=obs_in.get("forcing_class") or "FORCING_MISSING",
        kind=KIND_REANALYSIS,
        availability=in_class,
        provenance={"window": "in_horizon", "causal_feature": False},
        acquired=True,
        filled=False,
    )
    leak = reject_hindsight_forecast(era5_fc, t0)
    hypothetical = {
        "tigge_15d": hypothetical_lead_coverage(dt_h, NWP_ENSEMBLE_HOURS),
        "gfs_16d": hypothetical_lead_coverage(dt_h, GFS_HOURS),
        "openmeteo_previous_7d": (
            hypothetical_lead_coverage(dt_h, OPENMETEO_PREV_HOURS) if year >= 2024 else 0.0
        ),
        "deterministic_7d": hypothetical_lead_coverage(dt_h, NWP_DETERMINISTIC_HOURS),
        "glofas_forecast_30d": hypothetical_lead_coverage(dt_h, GLOFAS_FCST_HOURS),
    }
    return {
        "pair_id": pair.get("pair_id"),
        "event_id": pair.get("event_id"),
        "city_id": pair.get("city_id"),
        "split": pair.get("split"),
        "year": year,
        "t0": t0,
        "t1": t1,
        "delta_t_hours": dt_h,
        "delta_t_days": dt_h / 24.0,
        "delta_t_bucket": delta_t_bucket_69(dt_h),
        "label_valid_fraction": pair.get("joint_valid_fraction") or pair.get("label_valid_fraction"),
        "unknown_fraction": pair.get("unknown_fraction"),
        "new_flood_fraction": pair.get("fraction_newly_flooded") or pair.get("new_flood_fraction"),
        "recession_fraction": pair.get("fraction_receding"),
        "obs_pre_t0_availability": pre_class,
        "obs_pre_t0_coverage": obs_pre.get("n_hours_present") / obs_pre["n_hours_required"]
        if obs_pre.get("n_hours_required")
        else 0.0,
        "obs_in_horizon_availability": in_class,
        "obs_in_horizon_coverage": obs_in.get("n_hours_present") / obs_in["n_hours_required"]
        if obs_in.get("n_hours_required")
        else 0.0,
        "obs_in_horizon_as_forecast_input": False,
        "forecast_forcing_available": False,
        "forecast_coverage_fraction": 0.0,
        "forecast_lead_range": None,
        "forecast_resolution": None,
        "forecast_status": UNAVAILABLE,
        "forecast_issue_ok": True,
        "hindsight_forecast_error": leak,
        "hypothetical_coverage": hypothetical,
        "hydrology": hydro,
        "hydrological_state_availability": hydro["status"],
        "prior_flood_map": OBSERVED_AVAILABLE,
        "era5_in_horizon": era5_fc.to_dict(),
    }


def summarize_numeric(values: Iterable[Optional[float]]) -> dict:
    nums = [float(v) for v in values if v is not None and _finite(v) is not None]
    if not nums:
        return {"n": 0, "min": None, "median": None, "mean": None, "max": None}
    arr = sorted(nums)
    n = len(arr)
    mid = n // 2
    median = arr[mid] if n % 2 else 0.5 * (arr[mid - 1] + arr[mid])
    return {"n": n, "min": arr[0], "median": median, "mean": sum(arr) / n, "max": arr[-1]}


def aggregate_by(rows: Sequence[dict], key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    out = []
    for name in sorted(groups):
        g = groups[name]
        events = sorted({r.get("event_id") for r in g if r.get("event_id")})
        out.append(
            {
                key: name,
                "n_pairs": len(g),
                "n_independent_events": len(events),
                "forecast_available_frac": sum(1 for r in g if r.get("forecast_forcing_available")) / len(g),
                "mean_obs_in_horizon_coverage": summarize_numeric(r.get("obs_in_horizon_coverage") for r in g)["mean"],
                "mean_hypothetical_tigge_15d": summarize_numeric(
                    (r.get("hypothetical_coverage") or {}).get("tigge_15d") for r in g
                )["mean"],
                "mean_hypothetical_7d": summarize_numeric(
                    (r.get("hypothetical_coverage") or {}).get("deterministic_7d") for r in g
                )["mean"],
                "n_hydro_post_t0": sum(1 for r in g if (r.get("hydrology") or {}).get("status") == "POST_T0"),
                "n_hydro_stale": sum(1 for r in g if (r.get("hydrology") or {}).get("status") == "CAUSAL_BUT_STALE"),
                "mean_new_flood_fraction": summarize_numeric(r.get("new_flood_fraction") for r in g)["mean"],
            }
        )
    return out


def data_availability_matrix() -> List[dict]:
    return [
        {
            "input": "rainfall (ERA5-Land lattice)",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": POST_T0_OBSERVATION,
            "status": "REANALYSIS in cube; in-horizon not a forecast input",
        },
        {
            "input": "rainfall accumulation",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": POST_T0_OBSERVATION,
            "status": "24/72 h maps end at 192 h issue in cube; Target B needs re-window at t0",
        },
        {
            "input": "elevation",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": "n/a (static)",
            "post_t0_only": "n/a",
            "status": "AVAILABLE static",
        },
        {
            "input": "slope",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": "n/a (static)",
            "post_t0_only": "n/a",
            "status": "AVAILABLE static",
        },
        {
            "input": "river distance",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": "n/a (static)",
            "post_t0_only": "n/a",
            "status": "AVAILABLE static",
        },
        {
            "input": "river mask",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": "n/a (static)",
            "post_t0_only": "n/a",
            "status": "AVAILABLE static",
        },
        {
            "input": "river discharge",
            "before_t0": "UNAVAILABLE in cube at Target B t0; reindexable MODELLED reanalysis",
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": "cube Q often POST_T0 vs Target B t0",
            "status": "192 h misaligned; GloFAS forecast not acquired",
        },
        {
            "input": "river level",
            "before_t0": UNAVAILABLE,
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": UNAVAILABLE,
            "status": UNAVAILABLE,
        },
        {
            "input": "prior GFM flood state",
            "before_t0": OBSERVED_AVAILABLE,
            "forecast_at_t0": "n/a (state)",
            "post_t0_only": "n/a",
            "status": "earlier GFM scene is the state at t0",
        },
        {
            "input": "soil moisture",
            "before_t0": UNAVAILABLE,
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": UNAVAILABLE,
            "status": "GloFAS historical SWI on CDS; not in cube",
        },
        {
            "input": "flow accumulation",
            "before_t0": UNAVAILABLE,
            "forecast_at_t0": UNAVAILABLE,
            "post_t0_only": UNAVAILABLE,
            "status": UNAVAILABLE,
        },
        {
            "input": "NWP precipitation (TIGGE / Single Runs / GEFS)",
            "before_t0": "n/a",
            "forecast_at_t0": "EXISTENT_NOT_ACQUIRED",
            "post_t0_only": "n/a",
            "status": UNAVAILABLE,
        },
    ]


def input_contract() -> dict:
    return {
        "STATE_AT_T0": {
            "prior_gfm_flood_map": OBSERVED_AVAILABLE,
            "note": "The earlier GFM scene is the flood state at t0.",
        },
        "HISTORICAL_WEATHER": {
            "era5_land_precip_before_t0": OBSERVED_AVAILABLE,
            "note": "Reanalysis with ERA5 latency. Re-window lookback to Target B t0, not valid_at−192 h.",
        },
        "FORECAST_WEATHER": {
            "nwp_precip_t0_to_t1": UNAVAILABLE,
            "note": "Requires forecast-vintage archive (TIGGE or Single Runs). ERA5 in (t0,t1] is forbidden.",
        },
        "STATIC_TERRAIN": {"elevation": OBSERVED_AVAILABLE, "slope": OBSERVED_AVAILABLE},
        "STATIC_RIVER": {"river_distance": OBSERVED_AVAILABLE, "river_mask": OBSERVED_AVAILABLE},
        "OPTIONAL_HYDROLOGY": {
            "glofas_q_reanalysis_at_t0": "REINDEX_REQUIRED",
            "glofas_q_forecast_t0_to_t1": UNAVAILABLE,
            "river_level": UNAVAILABLE,
            "soil_moisture": UNAVAILABLE,
            "note": "Reindex daily Q to last complete day before t0. Kind remains MODELLED. No solver coupling.",
        },
        "excluded": [
            "ERA5 / Open-Meteo archive rain in (t0, t1]",
            "GloFAS Q aligned to valid_at−192 h",
            "later GFM map",
            "invented 24–168 h GFM labels",
        ],
    }


def hydro_realign_spec() -> dict:
    return {
        "do_not_implement_in_this_phase": True,
        "solver_coupling": False,
        "current": {
            "issue_time": "later.valid_at − 192 h (Track A cube)",
            "lookback": "daily Q t−7 … t−1 at that issue (Open-Meteo GloFAS reanalysis)",
            "kind": KIND_MODELLED,
            "spatial": "tile scalar via q_proxy_city",
        },
        "required_for_target_b": {
            "hydro_t0": "earlier.valid_at (Target B t0)",
            "last_complete_day": "calendar day before t0 (daily stamp includes post-noon hours)",
            "lookback": "Q[t0−7d … t0−1d] exclusive of t0",
            "forbid": "any Q date >= t0 as a t0 feature",
            "still_not_forecast": "reanalysis Q is OBSERVED-AVAILABLE state proxy, not GloFAS forecast",
            "forecast_layer": "cems-glofas-forecast with issue_time <= t0 covering (t0, t1] — not acquired",
        },
    }


def evaluate_gates_69(rows: Sequence[dict], n_events: int) -> dict:
    n = len(rows)
    n_fcst = sum(1 for r in rows if r.get("forecast_forcing_available"))
    n_hindsight = sum(1 for r in rows if r.get("hindsight_forecast_error"))
    n_post = sum(1 for r in rows if (r.get("hydrology") or {}).get("status") == "POST_T0")
    n_aligned = sum(1 for r in rows if (r.get("hydrology") or {}).get("status") == "CAUSAL_AT_T0")
    era5_as_fcst = any(r.get("obs_in_horizon_as_forecast_input") for r in rows)
    in_horizon_ok = all(r.get("obs_in_horizon_availability") == POST_T0_OBSERVATION for r in rows) if rows else False
    events = sorted({r.get("event_id") for r in rows if r.get("event_id")})
    gates = {
        "6.9A": {
            "pass": n_hindsight == 0,
            "status": "PASS" if n_hindsight == 0 else "FAIL",
            "rule": "forecast-vintage integrity: FORECAST-AVAILABLE implies issue_time <= t0",
            "n_violations": n_hindsight,
        },
        "6.9B": {
            "pass": False,
            "status": "FAIL",
            "rule": "in-horizon forecast precip coverage in the cube",
            "n_pairs_with_forecast": n_fcst,
            "forecast_pair_fraction": (n_fcst / n) if n else None,
        },
        "6.9C": {
            "pass": False,
            "status": "FAIL",
            "rule": "hydrological state available and aligned to Target B t0",
            "n_cube_q_post_t0": n_post,
            "n_cube_q_aligned": n_aligned,
        },
        "6.9D": {
            "pass": False,
            "status": "FAIL",
            "rule": "temporal alignment of forecast/hydro forcing to Target B t0 (not valid_at−192 h)",
        },
        "6.9E": {
            "pass": (not era5_as_fcst) and in_horizon_ok,
            "status": "PASS" if (not era5_as_fcst) and in_horizon_ok else "FAIL",
            "rule": "no hindsight contamination: ERA5 in (t0,t1] is POST-T0 OBSERVATION, not a forecast input",
        },
        "6.9F": {
            "pass": False,
            "status": "FAIL",
            "rule": "usable Target-B pairs with acquired causal in-horizon forecast forcing",
            "n_usable_forecast_pairs": n_fcst,
        },
        "6.9G": {
            "pass": len(events) >= 8,
            "status": "PASS" if len(events) >= 8 else "FAIL",
            "rule": "event diversity of Target B pairs (not pair count); official Gate B still 20",
            "n_independent_events": n_events,
            "n_events_in_audit": len(events),
            "official_gate_b": "FAIL (15 < 20, unchanged)",
        },
    }
    return {
        "gates": gates,
        "class": "CAUSAL FORCING AUDIT",
        "validated": False,
        "official_gate_b_unchanged": True,
    }


def decide_letter(rows: Sequence[dict]) -> str:
    n_fcst = sum(1 for r in rows if r.get("forecast_forcing_available"))
    n_hydro_post = sum(1 for r in rows if (r.get("hydrology") or {}).get("status") == "POST_T0")
    if n_fcst == 0 and n_hydro_post > 0:
        return "F"
    if n_fcst == 0:
        return "C"
    if n_fcst > 0 and n_fcst < 0.5 * max(len(rows), 1):
        return "B"
    dt = summarize_numeric(r.get("delta_t_days") for r in rows)
    median_d = dt.get("median") or 0
    n_le7 = sum(1 for r in rows if (r.get("delta_t_days") or 99) <= 7)
    if median_d >= 10 and n_le7 < 0.2 * max(len(rows), 1):
        return "D"
    if n_hydro_post > 0.5 * max(len(rows), 1) and n_fcst > 0:
        return "E"
    return "A"


def write_markdown_report(report: dict) -> str:
    c = report.get("counts") or {}
    dt = report.get("delta_t") or {}
    gates = (report.get("gates") or {}).get("gates") or {}
    letter = report.get("decision_letter") or "?"
    hydro = report.get("hydrology_summary") or {}

    def _g(name):
        return (gates.get(name) or {}).get("status")

    def _fmt(val, d=3):
        if val is None:
            return "n/a"
        if isinstance(val, float):
            return f"{val:.{d}f}"
        return str(val)

    lines = [
        "# Phase 6.9 — Causal forecast forcing audit (Target B)",
        "",
        "**Status:** CAUSAL FORCING AUDIT. Not a training run. Not a VALIDATED claim.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified. No solver–hydrology coupling.",
        "",
        f"**Experiment id:** `{EXPERIMENT_ID}`",
        "",
        f"**Decision:** **{letter}** — {DECISION_TEXT.get(letter, letter)}",
        "",
        "This phase does not train any model and does not download TIGGE or GloFAS-forecast cubes.",
        "",
        "---",
        "",
        "## 1. Objective",
        "",
        "Phase 6.8A found Target B **feasible as a label** (183 consecutive GFM pairs, 15 events) but "
        "**forcing insufficient**: rain in `(t0, t1]` is POST-T0 OBSERVATION. This phase asks whether "
        "those transitions can be associated with **genuinely causal forecast inputs available at t0**.",
        "",
        "## 2. Definition of causal-at-t0",
        "",
        "A feature is **FORECAST-AVAILABLE** at t0 only if all of the following hold:",
        "",
        "- it does not depend on observations after t0,",
        "- its product/version existed or is retrospectively reproducible as available at t0,",
        "- issue_time, valid window, and lead are known,",
        "- it is not an observed/reanalysis future value.",
        "",
        "| Code | Category | Meaning |",
        "| --- | --- | --- |",
        "| A | OBSERVED-AVAILABLE | Information at/before t0 (incl. lagged GFM; reanalysis lookback ending at t0) |",
        "| B | FORECAST-AVAILABLE | Product **issued** at/before t0, valid after t0 |",
        "| C | POST-T0 OBSERVATION | ERA5/GloFAS reanalysis or GFM after t0 |",
        "| D | UNAVAILABLE | Not in cube / not acquired |",
        "| E | UNKNOWN | Semantics unclear |",
        "",
        "These categories are not collapsed. Downloading ERA5 today for 2018-06-22 is still C if the window is after t0.",
        "",
        "## 3. Current ERA5-Land limitation",
        "",
        "The spatial lattice is hourly **2016-06-01 … 2024-08-31**, complete, ~11 km, Open-Meteo archive (ERA5-Land family).",
        "",
        "- Rain **before t0**: OBSERVED-AVAILABLE (reanalysis lookback; ERA5 operational latency ~5 days is a residual caveat).",
        "- Rain **during (t0, t1]**: POST-T0 OBSERVATION. Phase 6.8A completeness **95.6%** does **not** make it a forecast.",
        "- A current forecast API is not a historical run archive.",
        "",
        "## 4. Candidate forecast products",
        "",
        "See `forecast_sources.json`. Headline:",
        "",
        "| Product | Vintage? | Archive vs Target B | In cube? |",
        "| --- | --- | --- | --- |",
        "| ERA5-Land Open-Meteo lattice | No (reanalysis) | 2016–2024 | Yes |",
        "| Open-Meteo Previous Runs | Partial (lead-offset 1–7 d) | mostly 2024+ | No |",
        "| Open-Meteo Historical Forecast | No (blended runs) | ~2021+ | No |",
        "| Open-Meteo Single Runs (IFS) | Yes | from 2024-03-14 | No |",
        "| TIGGE ECMWF precip | Yes | 2006–present, covers 2015–2024 | No |",
        "| NOAA GEFSv12 / operational GEFS | Mixed (reforecast ≠ ops) | yes if operational files used | No |",
        "| GloFAS reanalysis Q | No | 2015–2024, 3 proxy cells | Yes, **192 h aligned** |",
        "| GloFAS forecast Q (CDS) | Yes, 30 d | not acquired | No |",
        "",
        "## 5. Forecast-vintage analysis",
        "",
        "True vintage requires **RUN/ISSUE TIME + LEAD + VALID TIME** with `issue_time <= t0`.",
        "",
        "- TIGGE stores initialisation time and step; ECMWF/NCEP TIGGE is CC BY 4.0; 48 h access delay (fine retrospectively).",
        "- Open-Meteo Single Runs expose `run=` initialisation from March 2024 (IFS only for most of Target B history).",
        "- Open-Meteo Previous Runs are 1–7 d offsets from Jan 2024, shorter than the 12-day median.",
        "- GEFSv12 **reforecasts** use a frozen 2017 model: useful for skill studies, **not** “what GFS issued in 2016”.",
        "- ERA5 has no issue_time. It cannot satisfy Gate 6.9A as FORECAST-AVAILABLE.",
        "",
        f"Acquired FORECAST-AVAILABLE precip pairs: **{c.get('n_pairs_with_acquired_forecast')}** / {c.get('n_pairs')}.",
        "",
        "## 6. Product availability by year",
        "",
    ]
    years = report.get("year_coverage") or {}
    if years:
        header = "| Year | " + " | ".join(years.get("_columns") or []) + " |"
        lines.append(header)
        lines.append("| --- | " + " | ".join("---" for _ in (years.get("_columns") or [])) + " |")
        for y in years.get("rows") or []:
            cols = [str(y.get("year"))] + [str(y.get(k, "")) for k in (years.get("_columns") or [])]
            lines.append("| " + " | ".join(cols) + " |")
    lines.extend(
        [
            "",
            "## 7. Target-B alignment",
            "",
            "`t0 = earlier.valid_at`, `t1 = later.valid_at`, `delta_t = t1 − t0` (unchanged from 6.8A). "
            "Labels were not rewritten. Splits remain event-isolated.",
            "",
            f"Cube hydrology issue is `t1 − {HORIZON_HOURS} h`. Offset vs t0 is `192 − Δt` hours. "
            "At the median Δt = 12 d, cube Q ends **~4 days after t0**.",
            "",
            "## 8. Rainfall coverage",
            "",
            "| Quantity | Value |",
            "| --- | --- |",
            f"| Observational in-horizon coverage (ERA5, POST-T0) | {_fmt(c.get('mean_obs_in_horizon_coverage'))} |",
            f"| Acquired forecast in-horizon coverage | {_fmt(c.get('mean_forecast_coverage'))} |",
            f"| Hypothetical TIGGE 15 d mean coverage if acquired | {_fmt(c.get('mean_hypothetical_tigge'))} |",
            f"| Hypothetical deterministic 7 d mean coverage | {_fmt(c.get('mean_hypothetical_7d'))} |",
            "",
            "Hypothetical fractions are **not** data in the cube.",
            "",
            "## 9. Hydrology coverage",
            "",
            "| Cube Q vs Target B t0 | Pairs |",
            "| --- | --- |",
            f"| POST_T0 (leak if used) | {hydro.get('n_post_t0')} |",
            f"| CAUSAL_BUT_STALE | {hydro.get('n_stale')} |",
            f"| CAUSAL_AT_T0 (Δt ≈ 192 h) | {hydro.get('n_aligned')} |",
            "",
            "River **level**, soil moisture, flow accumulation, and upstream routing: **UNAVAILABLE**. "
            "Reindexing reanalysis Q to t0 is specified, not implemented. GloFAS **forecast** Q is not acquired.",
            "",
            "## 10. Delta-t distribution",
            "",
            "| Statistic | Days |",
            "| --- | --- |",
            f"| min | {_fmt((dt.get('days') or {}).get('min'), 2)} |",
            f"| median | {_fmt((dt.get('days') or {}).get('median'), 2)} |",
            f"| mean | {_fmt((dt.get('days') or {}).get('mean'), 2)} |",
            f"| max | {_fmt((dt.get('days') or {}).get('max'), 2)} |",
            "",
            "| Bucket | Pairs |",
            "| --- | --- |",
        ]
    )
    for name, n in (dt.get("buckets") or {}).items():
        lines.append(f"| {name} | {n} |")
    lines.extend(
        [
            "",
            f"Pairs with Δt ≤ 7 d: **{c.get('n_pairs_le_7d')}**. "
            f"Pairs with Δt ≤ 15 d: **{c.get('n_pairs_le_15d')}**. "
            f"Pairs with Δt > 15 d: **{c.get('n_pairs_gt_15d')}**.",
            "",
            "**Most pairs are beyond the useful deterministic NWP range (~7 days).** "
            "The median 12-day gap sits at the tail of ECMWF ENS / TIGGE (~15 d). "
            "21–48 day pairs need subseasonal hydrology, not weather NWP.",
            "",
            "## 11. Forcing coverage by delta_t",
            "",
        ]
    )
    for row in report.get("by_delta_t_bucket") or []:
        lines.append(
            f"- {row.get('delta_t_bucket')}: n={row.get('n_pairs')}, "
            f"acquired forecast frac={_fmt(row.get('forecast_available_frac'))}, "
            f"hyp. TIGGE 15 d={_fmt(row.get('mean_hypothetical_tigge_15d'))}, "
            f"hyp. 7 d={_fmt(row.get('mean_hypothetical_7d'))}, "
            f"hydro POST_T0={row.get('n_hydro_post_t0')}"
        )
    lines.extend(
        [
            "",
            "## 12. Data availability matrix",
            "",
            "| Input | Before t0 | Forecast at t0 | Post-t0 only | Status |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("availability_matrix") or []:
        lines.append(
            f"| {row.get('input')} | {row.get('before_t0')} | {row.get('forecast_at_t0')} | "
            f"{row.get('post_t0_only')} | {row.get('status')} |"
        )
    lines.extend(
        [
            "",
            "## 13. Event-level coverage",
            "",
            "Ten pairs from one flood remain **one** event. Official Gate B is still **FAIL** (15 < 20).",
            "",
        ]
    )
    for row in report.get("by_event") or []:
        lines.append(
            f"- `{row.get('event_id')}`: {row.get('n_pairs')} pairs, forecast frac={_fmt(row.get('forecast_available_frac'))}, "
            f"hydro POST_T0={row.get('n_hydro_post_t0')}"
        )
    lines.extend(
        [
            "",
            "## 14. Provenance",
            "",
            "Audit provenance is attached on `forecast_sources.json` and `targetb_forcing_audit.json`. "
            "ERA5 lattice and GloFAS reanalysis snapshots already carry Phase 4.5 / 6.5 provenance. "
            "TIGGE/GloFAS-forecast are documented, not retrieved.",
            "",
            f"Provenance complete (audit envelope): **{(report.get('provenance') or {}).get('complete')}**.",
            "",
            "## 15. Licensing",
            "",
            "- ERA5-Land / Open-Meteo: CC BY 4.0.",
            "- GloFAS reanalysis via Open-Meteo: CC BY 4.0; CEMS-FLOODS attribution.",
            "- TIGGE ECMWF/NCEP: CC BY 4.0; some TIGGE centres CC BY-NC 4.0 — prefer ECMWF/NCEP for a commercial-safe path.",
            "- GFM labels: CEMS proprietary STAC (unchanged).",
            "- No WorldFloods. No global GloFAS cube download.",
            "",
            "## 16. Gates 6.9A–G",
            "",
            "| Gate | Status | Rule |",
            "| --- | --- | --- |",
            f"| 6.9A | {_g('6.9A')} | {(gates.get('6.9A') or {}).get('rule')} |",
            f"| 6.9B | {_g('6.9B')} | {(gates.get('6.9B') or {}).get('rule')} |",
            f"| 6.9C | {_g('6.9C')} | {(gates.get('6.9C') or {}).get('rule')} |",
            f"| 6.9D | {_g('6.9D')} | {(gates.get('6.9D') or {}).get('rule')} |",
            f"| 6.9E | {_g('6.9E')} | {(gates.get('6.9E') or {}).get('rule')} |",
            f"| 6.9F | {_g('6.9F')} | {(gates.get('6.9F') or {}).get('rule')} |",
            f"| 6.9G | {_g('6.9G')} | {(gates.get('6.9G') or {}).get('rule')} |",
            "",
            "Official Gate B is **not** modified.",
            "",
            "## 17. Recommended input contract",
            "",
            "```",
            "STATE_AT_T0          = earlier GFM map",
            "HISTORICAL_WEATHER   = ERA5-Land strictly before t0 (re-windowed)",
            "FORECAST_WEATHER     = NWP vintage issue<=t0 covering (t0,t1]  — NOT IN CUBE",
            "STATIC_TERRAIN       = DEM, slope",
            "STATIC_RIVER         = distance, mask",
            "OPTIONAL_HYDROLOGY   = GloFAS reanalysis Q reindexed to t0 (MODELLED); GloFAS forecast Q if acquired",
            "```",
            "",
            "Exclude: ERA5 in `(t0,t1]`, cube Q at valid_at−192 h, later GFM map.",
            "",
            "## 18. Whether Target B can support forecasting",
            "",
            str(report.get("forecast_support_narrative") or ""),
            "",
            "## 19. Exact remaining blocker",
            "",
            str(report.get("blocker") or ""),
            "",
            "## 20. Next-phase recommendation",
            "",
            str(report.get("next_step") or ""),
            "",
            "---",
            "",
            f"TARGET B: {report.get('target_b_status')}",
            "",
            f"FORECAST-VINTAGE FORCING: {report.get('forecast_vintage_status')}",
            "",
            f"HYDROLOGICAL STATE: {report.get('hydro_status')}",
            "",
            "MODEL TRAINING: NOT AUTHORIZED",
            "",
            "SPATIAL AI: NOT_VALIDATED",
            "",
            "SPATIAL API: UNAVAILABLE",
            "",
            "SOLVER MODIFIED: NO",
            "",
            "END.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_phase69(
    *,
    pairs_path: Optional[Path] = None,
    pairs: Optional[Sequence[dict]] = None,
    out_dir: Optional[Path] = None,
    write_artifacts: bool = True,
    write_docs: bool = False,
) -> dict:
    rows_in = list(pairs) if pairs is not None else load_targetb_pairs(pairs_path)
    audited = [pair_forcing_row(p) for p in rows_in]
    events = sorted({r.get("event_id") for r in audited if r.get("event_id")})
    dt_h = summarize_numeric(r.get("delta_t_hours") for r in audited)
    dt_d = summarize_numeric(r.get("delta_t_days") for r in audited)
    buckets = {name: 0 for _, _, name in DELTA_T_BINS_69}
    for r in audited:
        buckets[r["delta_t_bucket"]] = buckets.get(r["delta_t_bucket"], 0) + 1
    hydro_counts = {
        "n_post_t0": sum(1 for r in audited if (r.get("hydrology") or {}).get("status") == "POST_T0"),
        "n_stale": sum(1 for r in audited if (r.get("hydrology") or {}).get("status") == "CAUSAL_BUT_STALE"),
        "n_aligned": sum(1 for r in audited if (r.get("hydrology") or {}).get("status") == "CAUSAL_AT_T0"),
    }
    year_cols = [
        "era5_lattice",
        "tigge",
        "openmeteo_previous_runs",
        "openmeteo_single_runs",
        "glofas_reanalysis_q",
        "glofas_forecast_q",
    ]
    src = {s["id"]: s for s in FORECAST_SOURCES}
    year_rows = []
    for year in sorted({int(r["year"]) for r in audited}):
        year_rows.append(
            {
                "year": year,
                "era5_lattice": product_year_coverage(src["era5-land-open-meteo-lattice"], year),
                "tigge": product_year_coverage(src["tigge-ecmwf-ens"], year),
                "openmeteo_previous_runs": product_year_coverage(src["open-meteo-previous-runs"], year),
                "openmeteo_single_runs": product_year_coverage(src["open-meteo-single-runs"], year),
                "glofas_reanalysis_q": product_year_coverage(src["glofas-reanalysis-open-meteo"], year),
                "glofas_forecast_q": product_year_coverage(src["cems-glofas-forecast"], year),
            }
        )
    n_fcst = sum(1 for r in audited if r.get("forecast_forcing_available"))
    counts = {
        "n_pairs": len(audited),
        "n_independent_events": len(events),
        "n_pairs_with_acquired_forecast": n_fcst,
        "mean_obs_in_horizon_coverage": summarize_numeric(r.get("obs_in_horizon_coverage") for r in audited)["mean"],
        "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in audited)["mean"],
        "mean_hypothetical_tigge": summarize_numeric(
            (r.get("hypothetical_coverage") or {}).get("tigge_15d") for r in audited
        )["mean"],
        "mean_hypothetical_7d": summarize_numeric(
            (r.get("hypothetical_coverage") or {}).get("deterministic_7d") for r in audited
        )["mean"],
        "n_pairs_le_7d": sum(1 for r in audited if (r.get("delta_t_days") or 0) <= 7),
        "n_pairs_le_15d": sum(1 for r in audited if (r.get("delta_t_days") or 0) <= 15),
        "n_pairs_gt_15d": sum(1 for r in audited if (r.get("delta_t_days") or 0) > 15),
    }
    spatial_reg = load_spatial_registry()
    prov = spatial_artifact_provenance(
        data_status="PARTIAL",
        source="floodlens-x-phase6.9",
        dataset=EXPERIMENT_ID,
        source_url="docs/PHASE_6_9_CAUSAL_FORCING_AUDIT.md",
        source_version=EXPERIMENT_ID,
        processing_version=EXPERIMENT_ID,
        license_name="audit of existing CC BY 4.0 / CEMS products; TIGGE not downloaded",
        attribution="See forecast_sources.json",
        label_kind="OBSERVED",
        extra={"n_pairs": len(audited), "acquired_forecast_pairs": n_fcst},
    )
    letter = decide_letter(audited)
    report = {
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "experiment_id": EXPERIMENT_ID,
        "catalog_status": "NOT_VALIDATED",
        "public_spatial_status": public_spatial_status(spatial_reg),
        "promoted_to_validated": False,
        "spatial_api": "UNAVAILABLE",
        "model_training": "NOT AUTHORIZED",
        "cnn_trained": False,
        "solver_modified": False,
        "counts": counts,
        "delta_t": {"hours": dt_h, "days": dt_d, "buckets": buckets},
        "hydrology_summary": hydro_counts,
        "hydrology_realign_spec": hydro_realign_spec(),
        "availability_matrix": data_availability_matrix(),
        "input_contract": input_contract(),
        "year_coverage": {"_columns": year_cols, "rows": year_rows},
        "by_delta_t_bucket": aggregate_by(audited, "delta_t_bucket"),
        "by_event": aggregate_by(audited, "event_id"),
        "by_year": aggregate_by(audited, "year"),
        "pairs": audited,
        "gates": evaluate_gates_69(audited, len(events)),
        "decision_letter": letter,
        "decision": DECISION_TEXT[letter],
        "forecast_sources": FORECAST_SOURCES,
        "provenance": {"envelope": prov, "complete": provenance_complete(prov)},
        "categories": {
            "A": OBSERVED_AVAILABLE,
            "B": FORECAST_AVAILABLE,
            "C": POST_T0_OBSERVATION,
            "D": UNAVAILABLE,
        },
        "target_b_status": "PARTIALLY FEASIBLE",
        "forecast_vintage_status": "NOT ACQUIRED (TIGGE/Single Runs exist off-cube)",
        "hydro_status": "MISALIGNED (cube Q at valid_at−192 h); reanalysis reindex specified, forecast Q absent",
    }
    report["forecast_support_narrative"] = (
        "Target B remains an honest **observation** of flood change. It cannot yet support a causal "
        "spatial **forecast** experiment: acquired in-horizon NWP coverage is 0 pairs; ERA5 in the "
        "gap is POST-T0 OBSERVATION; cube GloFAS Q is 192 h-aligned and is POST_T0 for most 12-day pairs. "
        f"Median Δt = {_finite(dt_d.get('median'))} days is at/beyond deterministic NWP skill. "
        "A later TIGGE (or 2024-only Single Runs) acquisition would still leave hydrology thin."
    )
    report["blocker"] = (
        "Two first-class gaps: (1) no forecast-vintage precipitation with issue_time≤t0 covering (t0,t1] "
        "in the cube; (2) no Target-B-aligned hydrological state (Q/level/wetness). "
        "Do not treat ERA5-in-gap completeness as a substitute."
    )
    report["next_step"] = (
        "Do not train Target B baselines. If a next phase is approved, either (i) acquire TIGGE ECMWF "
        "precip (issue+lead+valid) for the 15 events without filling gaps, and/or (ii) reindex GloFAS "
        "reanalysis Q to last complete day before t0 as MODELLED state — still not a forecast. "
        "Do not invent 24 h GFM maps. Do not enable the spatial API. Do not couple the solver."
    )

    if write_artifacts:
        dest = Path(out_dir or OUT_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        payload = _jsonable(report)
        (dest / "forecast_sources.json").write_text(
            json.dumps(_jsonable(FORECAST_SOURCES), indent=2), encoding="utf-8"
        )
        (dest / "targetb_forcing_audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        csv_path = dest / CSV_NAME
        fields = [
            "pair_id",
            "event_id",
            "city_id",
            "year",
            "t0",
            "t1",
            "delta_t_hours",
            "delta_t_days",
            "delta_t_bucket",
            "forecast_forcing_available",
            "forecast_coverage_fraction",
            "forecast_status",
            "obs_in_horizon_coverage",
            "obs_in_horizon_availability",
            "hydrological_state_availability",
            "label_valid_fraction",
            "unknown_fraction",
            "new_flood_fraction",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in audited:
                writer.writerow({k: row.get(k) for k in fields})
        (dest / "gate_results.json").write_text(json.dumps(_jsonable(report["gates"]), indent=2), encoding="utf-8")
        md = write_markdown_report(report)
        (dest / "PHASE_6_9_CAUSAL_FORCING_AUDIT.md").write_text(md, encoding="utf-8")
        if write_docs:
            REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            (SPATIAL_DIR / "forecast_sources.json").write_text(
                json.dumps(_jsonable(FORECAST_SOURCES), indent=2), encoding="utf-8"
            )
            (SPATIAL_DIR / "targetb_forcing_audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            (SPATIAL_DIR / CSV_NAME).write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
            DOCS_REPORT.write_text(md, encoding="utf-8")
            report["report_md"] = str(DOCS_REPORT)
        report["artifact_dir"] = str(dest)
    return report
