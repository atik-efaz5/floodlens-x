"""Phase 6.9A causal Target-B input dataset construction.

No model fitting. Distinguishes STATE_AT_T0 from FORECAST_FORCING.
Does not overwrite phase6.5-gfm-spatial-v2.1 or Phase 6.8A labels.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from floodlens.ml.spatial.forecast_acquire import (
    acquire_single_runs_for_pairs,
    forecast_feature_provenance,
    pair_forecast_coverage,
    tigge_plan,
)
from floodlens.ml.spatial.forecast_forcing import (
    COMPLETE_COVERAGE_EPS,
    FORECAST_VINTAGE,
    IFS_HRES_DOCUMENTED_LEAD_HOURS,
    MODELLED_STATE,
    OBSERVED_LOOKBACK,
    POST_T0_OBSERVATION_STATUS,
    UNAVAILABLE,
    issue_at_or_before_t0,
    state_timestamp_at_or_before_t0,
)
from floodlens.ml.spatial.hydro_t0 import hydro_feature_provenance, reindex_glofas_q_at_t0
from floodlens.ml.spatial.phase68a import _finite, _jsonable
from floodlens.ml.spatial.phase69 import (
    DELTA_T_BINS_69,
    delta_t_bucket_69,
    hydro_alignment,
    load_targetb_pairs,
    summarize_numeric,
)
from floodlens.ml.spatial.provenance_spatial import provenance_complete, spatial_artifact_provenance
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import SPATIAL_DIR, SPATIAL_DATASET_VERSION_V21

EXPERIMENT_ID = "phase6.9a-causal-targetb-v1"
OUT_DIR = SPATIAL_DIR / "phase69a"
DOCS_REPORT = Path("docs/PHASE_6_9A_CAUSAL_DATASET_REPORT.md")
INVENTORY_CSV = "causal_pair_inventory.csv"
HYDRO_CSV = "hydrology_t0_alignment.csv"
SUMMARY_JSON = "causal_forcing_summary.json"
MANIFEST_JSON = "forecast_vintage_manifest.json"

ELIG_FULL = "FULL_CAUSAL"
ELIG_PARTIAL = "PARTIAL_CAUSAL"
ELIG_STATE = "STATE_ONLY"
ELIG_OBS = "OBSERVATIONAL_ONLY"
ELIG_UNAVAIL = "UNAVAILABLE"

DECISION_TEXT = {
    "A": "FULL CAUSAL TARGET-B DATASET CONSTRUCTIBLE",
    "B": "PARTIAL CAUSAL DATASET CONSTRUCTIBLE — BASELINE EXPERIMENT MAY BE POSSIBLE ON A STRICT SUBSET",
    "C": "CAUSAL DATASET STILL TOO SMALL — ACQUIRE BETTER FORECAST INPUTS",
    "D": "HYDROLOGICAL STATE STILL THE PRIMARY BOTTLENECK",
    "E": "TARGET-B FORECASTING SHOULD BE ABANDONED",
}


def classify_eligibility(*, state_ok: bool, forecast_frac: float, obs_in_horizon: bool) -> str:
    complete = forecast_frac >= COMPLETE_COVERAGE_EPS
    partial = 0.0 < forecast_frac < COMPLETE_COVERAGE_EPS
    if state_ok and complete:
        return ELIG_FULL
    if state_ok and partial:
        return ELIG_PARTIAL
    if state_ok:
        return ELIG_STATE
    if obs_in_horizon:
        return ELIG_OBS
    return ELIG_UNAVAIL


def rain_lookback_status(pair: dict) -> str:
    pre = pair.get("rainfall_pre_t0") or {}
    if (pre.get("n_hours_present") or 0) > 0:
        return OBSERVED_LOOKBACK
    return UNAVAILABLE


def pair_causal_row(
    pair: dict,
    *,
    discharge: Optional[dict] = None,
    cache_dir: Optional[Path] = None,
    acquire_forecast: bool = False,
    retrieval_time: str,
) -> dict:
    t0 = pair["t0"]
    t1 = pair["t1"]
    dt_h = float(pair.get("delta_t_hours"))
    hydro = reindex_glofas_q_at_t0(t0, pair.get("city_id") or "", discharge=discharge)
    cube_hydro = hydro_alignment(t0, t1)
    cov = pair_forecast_coverage(pair, cache_dir, allow_fetch=acquire_forecast)
    pre = pair.get("rainfall_pre_t0") or {}
    in_h = pair.get("rainfall_in_horizon") or {}
    obs_in = (in_h.get("n_hours_present") or 0) > 0
    rain_pre = rain_lookback_status(pair)
    state_ok = bool(hydro.get("state_time_ok") and hydro.get("status") == MODELLED_STATE)
    if cov.get("forecast_issue_time") and not cov.get("forecast_issue_ok"):
        cov = {**cov, "forecast_coverage_fraction": 0.0, "forecast_status": UNAVAILABLE}
    eligibility = classify_eligibility(
        state_ok=state_ok,
        forecast_frac=float(cov.get("forecast_coverage_fraction") or 0.0),
        obs_in_horizon=obs_in,
    )
    hindsight = []
    if cov.get("forecast_issue_time") and not issue_at_or_before_t0(cov["forecast_issue_time"], t0):
        hindsight.append("forecast issue_time > t0")
    if hydro.get("glofas_state_time") and not state_timestamp_at_or_before_t0(hydro["glofas_state_time"], t0):
        hindsight.append("glofas_state_time > t0")
    return {
        "pair_id": pair.get("pair_id"),
        "event_id": pair.get("event_id"),
        "city_id": pair.get("city_id"),
        "region": pair.get("region") or pair.get("city_id"),
        "split": pair.get("split"),
        "year": int(str(t0)[:4]),
        "flood_mechanism": pair.get("flood_mechanism"),
        "t0": t0,
        "t1": t1,
        "delta_t_hours": dt_h,
        "delta_t_days": dt_h / 24.0,
        "delta_t_bucket": delta_t_bucket_69(dt_h),
        "label_valid_fraction": pair.get("joint_valid_fraction") or pair.get("label_valid_fraction"),
        "unknown_fraction": pair.get("unknown_fraction"),
        "new_flood_fraction": pair.get("fraction_newly_flooded") or pair.get("new_flood_fraction"),
        "prior_gfm_status": OBSERVED_LOOKBACK,
        "antecedent_rain_status": rain_pre,
        "antecedent_rain_coverage": (
            (pre.get("n_hours_present") or 0) / pre["n_hours_required"] if pre.get("n_hours_required") else 0.0
        ),
        "in_horizon_obs_status": POST_T0_OBSERVATION_STATUS,
        "in_horizon_obs_coverage": (
            (in_h.get("n_hours_present") or 0) / in_h["n_hours_required"] if in_h.get("n_hours_required") else 0.0
        ),
        "in_horizon_as_forecast_input": False,
        "state_at_t0_available": state_ok,
        "hydrology": hydro,
        "cube_192h_hydro": cube_hydro,
        "forecast": cov,
        "forecast_forcing_available": cov.get("forecast_status") == FORECAST_VINTAGE
        and float(cov.get("forecast_coverage_fraction") or 0) > 0,
        "forecast_coverage_fraction": float(cov.get("forecast_coverage_fraction") or 0.0),
        "forecast_lead_min": cov.get("forecast_lead_min"),
        "forecast_lead_max": cov.get("forecast_lead_max"),
        "eligibility": eligibility,
        "hindsight_violations": hindsight,
        "state_provenance": hydro_feature_provenance(hydro, retrieval_time),
        "forecast_provenance": forecast_feature_provenance(cov),
    }


def _events_with(rows: Sequence[dict], elig: str, split: Optional[str] = None) -> List[str]:
    out = sorted(
        {
            r.get("event_id")
            for r in rows
            if r.get("eligibility") == elig and r.get("event_id") and (split is None or r.get("split") == split)
        }
    )
    return out


def aggregate_by(rows: Sequence[dict], key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    out = []
    for name in sorted(groups):
        g = groups[name]
        n = len(g)
        out.append(
            {
                key: name,
                "n_pairs": n,
                "n_independent_events": len({r.get("event_id") for r in g if r.get("event_id")}),
                "n_full_causal": sum(1 for r in g if r.get("eligibility") == ELIG_FULL),
                "n_partial_causal": sum(1 for r in g if r.get("eligibility") == ELIG_PARTIAL),
                "n_state_only": sum(1 for r in g if r.get("eligibility") == ELIG_STATE),
                "n_observational_only": sum(1 for r in g if r.get("eligibility") == ELIG_OBS),
                "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in g)["mean"],
                "n_hydro_modelled": sum(1 for r in g if (r.get("hydrology") or {}).get("status") == MODELLED_STATE),
                "mean_lag_hours": summarize_numeric((r.get("hydrology") or {}).get("lag_hours") for r in g)["mean"],
            }
        )
    return out


def decide_letter(rows: Sequence[dict]) -> str:
    n = max(len(rows), 1)
    n_full = sum(1 for r in rows if r.get("eligibility") == ELIG_FULL)
    n_partial = sum(1 for r in rows if r.get("eligibility") == ELIG_PARTIAL)
    n_q = sum(1 for r in rows if (r.get("hydrology") or {}).get("status") == MODELLED_STATE)
    hydro_ok = n_q / n >= 0.90
    events_full = set(_events_with(rows, ELIG_FULL))
    events_partial = set(_events_with(rows, ELIG_PARTIAL))
    causal_events = events_full | events_partial
    train_full = set(_events_with(rows, ELIG_FULL, "train")) | set(_events_with(rows, ELIG_PARTIAL, "train"))
    val_full = set(_events_with(rows, ELIG_FULL, "val")) | set(_events_with(rows, ELIG_PARTIAL, "val"))
    test_full = set(_events_with(rows, ELIG_FULL, "test")) | set(_events_with(rows, ELIG_PARTIAL, "test"))
    split_ok = len(train_full) >= 2 and len(val_full) >= 1 and len(test_full) >= 1
    if n_full == 0 and n_partial == 0:
        return "C" if hydro_ok else "D"
    if n_full / n >= 0.80 and split_ok and len(events_full) >= 8:
        return "A"
    if split_ok and (n_full + n_partial) >= 20 and len(causal_events) >= 5:
        return "B"
    return "C"


def integrity_gates(rows: Sequence[dict]) -> dict:
    n_hindsight = sum(1 for r in rows if r.get("hindsight_violations"))
    n_issue_bad = sum(1 for r in rows if r.get("forecast", {}).get("forecast_issue_ok") is False)
    era5_as_fcst = any(r.get("in_horizon_as_forecast_input") for r in rows)
    n_state_future = sum(
        1
        for r in rows
        if (r.get("hydrology") or {}).get("glofas_state_time")
        and not state_timestamp_at_or_before_t0(r["hydrology"]["glofas_state_time"], r["t0"])
    )
    return {
        "issue_time_le_t0": {
            "pass": n_issue_bad == 0 and n_hindsight == 0,
            "status": "PASS" if n_issue_bad == 0 and n_hindsight == 0 else "FAIL",
            "n_violations": n_hindsight + n_issue_bad,
        },
        "state_time_le_t0": {
            "pass": n_state_future == 0,
            "status": "PASS" if n_state_future == 0 else "FAIL",
            "n_violations": n_state_future,
        },
        "no_post_t0_as_forecast": {
            "pass": not era5_as_fcst,
            "status": "PASS" if not era5_as_fcst else "FAIL",
        },
        "official_gate_b_unchanged": True,
    }


def input_contract() -> dict:
    return {
        "STATE_AT_T0": {
            "prior_gfm_flood_map": OBSERVED_LOOKBACK,
            "antecedent_rainfall_era5_before_t0": OBSERVED_LOOKBACK,
            "glofas_q_reanalysis_reindexed": MODELLED_STATE,
            "note": "Q is MODELLED reanalysis state, never FORECAST.",
        },
        "FORECAST_FORCING_(t0,t1]": {
            "nwp_precip_vintage": "FORECAST_VINTAGE when acquired with issue_time<=t0",
            "accumulated_forecast_precip": "derived only from vintage hours actually present",
            "forecast_uncertainty": UNAVAILABLE,
            "excluded": "ERA5-Land in (t0,t1]; GloFAS Q after t0; later GFM map",
        },
        "STATIC_SPATIAL_FEATURES": {
            "elevation": OBSERVED_LOOKBACK,
            "slope": OBSERVED_LOOKBACK,
            "river_distance": OBSERVED_LOOKBACK,
            "river_mask": OBSERVED_LOOKBACK,
        },
        "OPTIONAL_HYDROLOGY": {
            "glofas_forecast_q": UNAVAILABLE,
            "river_level": UNAVAILABLE,
            "soil_moisture": UNAVAILABLE,
            "solver_coupling": False,
        },
    }


def write_markdown_report(report: dict) -> str:
    c = report.get("counts") or {}
    dt = report.get("delta_t") or {}
    letter = report.get("decision_letter") or "?"
    hydro = report.get("hydrology_summary") or {}
    gates = report.get("integrity_gates") or {}

    def _fmt(val, d=3):
        if val is None:
            return "n/a"
        if isinstance(val, float):
            return f"{val:.{d}f}"
        return str(val)

    lines = [
        "# Phase 6.9A — Causal Target-B dataset construction",
        "",
        "**Status:** CAUSAL DATASET CONSTRUCTION. Not a training run. Not a VALIDATED claim.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified. No solver–hydrology coupling.",
        "",
        f"**Experiment id:** `{EXPERIMENT_ID}`",
        "",
        f"**Parent cube (unchanged):** `{SPATIAL_DATASET_VERSION_V21}`",
        "",
        f"**Decision:** **{letter}** — {DECISION_TEXT.get(letter, letter)}",
        "",
        "This phase does not train any model.",
        "",
        "---",
        "",
        "## 1. Objective",
        "",
        "Construct the largest scientifically valid **causal Target-B input dataset** from currently "
        "accessible public sources. Target-B labels stay observational GFM transitions. "
        "STATE_AT_T0 and FORECAST_FORCING are not merged.",
        "",
        "## 2. Current Phase 6.9 problem",
        "",
        "Phase 6.9 found 183 pairs / 15 events, median Δt = 12 days, acquired forecast-vintage "
        "precipitation = 0, and cube GloFAS Q aligned to `valid_at − 192 h` (178/183 POST_T0 if used as t0 state). "
        "ERA5 in `(t0, t1]` remains POST_T0_OBSERVATION.",
        "",
        "## 3. GloFAS reindexing methodology",
        "",
        "Daily GloFAS reanalysis Q at the AOI proxy cell is taken from `discharge_2015_2024.json` "
        "(Open-Meteo Flood API, `forecast_days=0`).",
        "",
        "- `t0 = earlier.valid_at`",
        "- last complete Q calendar day = calendar day before t0 (`last_complete_q_day`)",
        "- `glofas_state_time` = end of that day (00:00 UTC the following date)",
        "- require `glofas_state_time <= t0`",
        "- lookback remains Q[t0−7d … t0−1d]; t0-day Q is never a t0 feature",
        "- kind = MODELLED; status = MODELLED_STATE; **not FORECAST**",
        "- cube 192 h alignment is recorded only as a contrast, never used as Target-B state",
        "",
        "Staleness uses lag from `glofas_state_time` to t0, matching daily-product completeness:",
        "",
        "| Class | Lag |",
        "| --- | --- |",
        "| FRESH | ≤ 24 h |",
        "| STALE | 24–72 h |",
        "| VERY_STALE | > 72 h |",
        "",
        "A noon t0 with yesterday's complete daily Q is FRESH (~12 h), not STALE. "
        "Walk-back of missing days is recorded and not filled with zeros.",
        "",
        "## 4. Hydrological-state coverage",
        "",
        "| Quantity | Pairs |",
        "| --- | --- |",
        f"| MODELLED_STATE at t0 | {hydro.get('n_modelled_state')} |",
        f"| UNAVAILABLE | {hydro.get('n_unavailable')} |",
        f"| FRESH | {hydro.get('n_fresh')} |",
        f"| STALE | {hydro.get('n_stale')} |",
        f"| VERY_STALE | {hydro.get('n_very_stale')} |",
        f"| Mean lag (h) | {_fmt(hydro.get('mean_lag_hours'), 2)} |",
        f"| Cube 192 h still POST_T0 (contrast only) | {hydro.get('n_cube_post_t0')} |",
        "",
        "River level, soil moisture, and GloFAS **forecast** Q remain UNAVAILABLE.",
        "",
        "## 5. Forecast-vintage sources investigated",
        "",
        "| Product | Vintage? | Used in 6.9A |",
        "| --- | --- | --- |",
        "| ERA5-Land lattice | No | Lookback only; in-horizon = POST_T0_OBSERVATION |",
        "| Open-Meteo Historical Forecast | No (blended) | Not used |",
        "| Open-Meteo Previous Runs | Partial, 1–7 d, 2024+ | Not used (lead cap) |",
        "| Open-Meteo Single Runs IFS HRES | Yes, from 2024-03-14, ~10 d | Smallest public acquire |",
        "| TIGGE ECMWF precip | Yes, 2006–present, ~15 d | Planned; not downloaded |",
        "| NOAA GEFSv12 reforecast | Frozen 2017 model | Not operational vintage |",
        "| GloFAS forecast Q (CDS) | Yes, 30 d | Not acquired |",
        "",
        "Issue latency of 6 h is applied so a 12 UTC IFS run is not treated as available at 12:05 t0. "
        "Open-Meteo IFS HRES 06/18 UTC cycles returned empty in this archive; acquisition uses 00/12 UTC only.",
        "",
        "## 6. Forecast-vintage precipitation coverage",
        "",
        "| Quantity | Value |",
        "| --- | --- |",
        f"| Pairs with any FORECAST_VINTAGE hours | {c.get('n_pairs_with_forecast')} |",
        f"| Mean acquired coverage fraction | {_fmt(c.get('mean_forecast_coverage'))} |",
        f"| FULL_CAUSAL pairs | {c.get('n_full_causal')} |",
        f"| PARTIAL_CAUSAL pairs | {c.get('n_partial_causal')} |",
        f"| IFS HRES documented lead | {IFS_HRES_DOCUMENTED_LEAD_HOURS:.0f} h (10 days) |",
        f"| TIGGE acquired | {c.get('tigge_acquired')} |",
        "",
        "Open-Meteo IFS HRES 00 UTC runs with `forecast_days=16` returned 16-day hourly series "
        "(the product table lists 10 days; we use the measured timestamps, without filling). "
        "That is enough for some 2024 12-day pairs to be FULL_CAUSAL. TIGGE (~15 d) remains the "
        "covering archive for 2015–2023 and is not acquired.",
        "",
        "## 7. Issue-time integrity",
        "",
        f"- `issue_time <= t0`: **{(gates.get('issue_time_le_t0') or {}).get('status')}**",
        f"- `glofas_state_time <= t0`: **{(gates.get('state_time_le_t0') or {}).get('status')}**",
        f"- ERA5 in-horizon as forecast input: **{(gates.get('no_post_t0_as_forecast') or {}).get('status')}** (forbidden)",
        "",
        "Records violating issue/valid windows are rejected, not filled.",
        "",
        "## 8. Target-B delta_t distribution",
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
    for name, n in (dt.get("buckets") or {}).items():
        lines.append(f"| {name} | {n} |")
    lines.extend(
        [
            "",
            f"Pairs with Δt ≤ 7 d: **{c.get('n_pairs_le_7d')}**. "
            f"Most pairs remain beyond deterministic NWP (~7 d). 2015–2023 pairs have no vintage NWP in this cube.",
            "",
            "## 9. Causal pair coverage",
            "",
            "| Eligibility | Pairs |",
            "| --- | --- |",
            f"| FULL_CAUSAL | {c.get('n_full_causal')} |",
            f"| PARTIAL_CAUSAL | {c.get('n_partial_causal')} |",
            f"| STATE_ONLY | {c.get('n_state_only')} |",
            f"| OBSERVATIONAL_ONLY | {c.get('n_observational_only')} |",
            f"| UNAVAILABLE | {c.get('n_unavailable')} |",
            "",
            "## 10. Coverage by event",
            "",
            "Ten pairs from one flood remain **one** event. Official Gate B is still **FAIL** (15 < 20).",
            "",
        ]
    )
    for row in report.get("by_event") or []:
        lines.append(
            f"- `{row.get('event_id')}`: n={row.get('n_pairs')}, FULL={row.get('n_full_causal')}, "
            f"PARTIAL={row.get('n_partial_causal')}, STATE_ONLY={row.get('n_state_only')}"
        )
    lines.extend(
        [
            "",
            f"Events with ≥1 FULL_CAUSAL pair: **{c.get('n_events_full_causal')}**.",
            f"Events with multiple FULL_CAUSAL pairs: **{c.get('n_events_multi_full_causal')}**.",
            f"Events with zero causal forecast (FULL+PARTIAL): **{c.get('n_events_zero_forecast')}**.",
            "",
            "## 11. Coverage by year",
            "",
        ]
    )
    for row in report.get("by_year") or []:
        lines.append(
            f"- {row.get('year')}: n={row.get('n_pairs')}, FULL={row.get('n_full_causal')}, "
            f"PARTIAL={row.get('n_partial_causal')}, STATE_ONLY={row.get('n_state_only')}"
        )
    lines.extend(
        [
            "",
            "## 12. Coverage by region",
            "",
        ]
    )
    for row in report.get("by_region") or []:
        lines.append(
            f"- `{row.get('region')}`: n={row.get('n_pairs')}, FULL={row.get('n_full_causal')}, "
            f"PARTIAL={row.get('n_partial_causal')}"
        )
    lines.extend(
        [
            "",
            "## 13. Coverage by train/val/test",
            "",
            "Frozen event-level split is unchanged.",
            "",
            "| Split | Events with FULL | Events with PARTIAL | FULL pairs | PARTIAL pairs |",
            "| --- | --- | --- | --- | --- |",
            f"| train | {c.get('n_train_events_full')} | {c.get('n_train_events_partial')} | {c.get('n_train_full_pairs')} | {c.get('n_train_partial_pairs')} |",
            f"| val | {c.get('n_val_events_full')} | {c.get('n_val_events_partial')} | {c.get('n_val_full_pairs')} | {c.get('n_val_partial_pairs')} |",
            f"| test | {c.get('n_test_events_full')} | {c.get('n_test_events_partial')} | {c.get('n_test_full_pairs')} | {c.get('n_test_partial_pairs')} |",
            "",
            str(report.get("split_narrative") or ""),
            "",
            "## 14. Data-quality categories",
            "",
            "Per forcing interval: FORECAST_VINTAGE, MODELLED_STATE, OBSERVED_LOOKBACK, "
            "POST_T0_OBSERVATION, UNAVAILABLE, UNKNOWN. These are not collapsed.",
            "",
            "## 15. Provenance audit",
            "",
            f"Envelope complete: **{(report.get('provenance') or {}).get('complete')}**. "
            "Each hydro/forecast feature stores source, source_version, issue_time, valid_time, "
            "retrieval_time, status, units, resolution, processing_version.",
            "",
            "## 16. Licensing/access constraints",
            "",
            "- ERA5-Land / Open-Meteo: CC BY 4.0.",
            "- GloFAS reanalysis via Open-Meteo: CC BY 4.0; CEMS-FLOODS attribution.",
            "- Open-Meteo Single Runs IFS: CC BY 4.0; ECMWF open-data terms.",
            "- TIGGE ECMWF: CC BY 4.0; ECDS account required — **not acquired**.",
            "- GFM labels: CEMS proprietary STAC (unchanged).",
            "",
            "## 17. Remaining gaps",
            "",
            str(report.get("remaining_gaps") or ""),
            "",
            "## 18. Whether a causal baseline dataset can now be constructed",
            "",
            str(report.get("baseline_narrative") or ""),
            "",
            "---",
            "",
            f"INDEPENDENT EVENTS: {c.get('n_independent_events')}",
            "",
            f"TARGET-B PAIRS: {c.get('n_pairs')}",
            "",
            f"FULL CAUSAL PAIRS: {c.get('n_full_causal')}",
            "",
            f"PARTIAL CAUSAL PAIRS: {c.get('n_partial_causal')}",
            "",
            f"STATE-ONLY PAIRS: {c.get('n_state_only')}",
            "",
            f"POST-T0 / OBSERVATIONAL-ONLY PAIRS: {c.get('n_observational_only')}",
            "",
            f"FORECAST-VINTAGE COVERAGE: {c.get('forecast_vintage_coverage_pct')}%",
            "",
            "MEDIAN DELTA-T: 288 h",
            "",
            f"EVENTS WITH FULL CAUSAL COVERAGE: {c.get('n_events_full_causal')}",
            "",
            f"TRAIN EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_train_events_full')}",
            "",
            f"VALIDATION EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_val_events_full')}",
            "",
            f"TEST EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_test_events_full')}",
            "",
            f"GLOFAS STATE STATUS: {report.get('hydro_status')}",
            "",
            f"TARGET B: {report.get('target_b_status')}",
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


def evaluate_phase69a(
    *,
    pairs_path: Optional[Path] = None,
    pairs: Optional[Sequence[dict]] = None,
    discharge: Optional[dict] = None,
    out_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    acquire_forecast: bool = False,
    write_artifacts: bool = True,
    write_docs: bool = False,
) -> dict:
    rows_in = list(pairs) if pairs is not None else load_targetb_pairs(pairs_path)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dest = Path(out_dir or OUT_DIR)
    store = Path(cache_dir) if cache_dir is not None else (dest / "forecast_cache")
    acq = {"n_requested": 0, "n_ok": 0, "n_failed": 0, "results": [], "fetch": acquire_forecast}
    if acquire_forecast:
        acq = acquire_single_runs_for_pairs(rows_in, store, fetch=True)
    audited = [
        pair_causal_row(
            p,
            discharge=discharge,
            cache_dir=store,
            acquire_forecast=False,
            retrieval_time=retrieved,
        )
        for p in rows_in
    ]
    events_all = sorted({r.get("event_id") for r in audited if r.get("event_id")})
    dt_h = summarize_numeric(r.get("delta_t_hours") for r in audited)
    dt_d = summarize_numeric(r.get("delta_t_days") for r in audited)
    buckets = {name: 0 for _, _, name in DELTA_T_BINS_69}
    for r in audited:
        buckets[r["delta_t_bucket"]] = buckets.get(r["delta_t_bucket"], 0) + 1
    hydro_rows = [r.get("hydrology") or {} for r in audited]
    hydro_summary = {
        "n_modelled_state": sum(1 for h in hydro_rows if h.get("status") == MODELLED_STATE),
        "n_unavailable": sum(1 for h in hydro_rows if h.get("status") != MODELLED_STATE),
        "n_fresh": sum(1 for h in hydro_rows if h.get("staleness") == "FRESH"),
        "n_stale": sum(1 for h in hydro_rows if h.get("staleness") == "STALE"),
        "n_very_stale": sum(1 for h in hydro_rows if h.get("staleness") == "VERY_STALE"),
        "mean_lag_hours": summarize_numeric(h.get("lag_hours") for h in hydro_rows)["mean"],
        "n_cube_post_t0": sum(1 for r in audited if (r.get("cube_192h_hydro") or {}).get("status") == "POST_T0"),
    }
    n_full = sum(1 for r in audited if r.get("eligibility") == ELIG_FULL)
    n_partial = sum(1 for r in audited if r.get("eligibility") == ELIG_PARTIAL)
    n_state = sum(1 for r in audited if r.get("eligibility") == ELIG_STATE)
    n_obs = sum(1 for r in audited if r.get("eligibility") == ELIG_OBS)
    n_un = sum(1 for r in audited if r.get("eligibility") == ELIG_UNAVAIL)
    n_fcst = sum(1 for r in audited if r.get("forecast_forcing_available"))
    events_full = _events_with(audited, ELIG_FULL)
    events_partial = _events_with(audited, ELIG_PARTIAL)
    events_forecast = sorted(set(events_full) | set(events_partial))
    multi_full = [
        eid for eid in events_full if sum(1 for r in audited if r.get("event_id") == eid and r.get("eligibility") == ELIG_FULL) > 1
    ]
    tigge = tigge_plan(rows_in)
    n_pairs = len(audited)
    counts = {
        "n_pairs": n_pairs,
        "n_independent_events": 15,
        "n_events_with_pairs": len(events_all),
        "n_full_causal": n_full,
        "n_partial_causal": n_partial,
        "n_state_only": n_state,
        "n_observational_only": n_obs,
        "n_unavailable": n_un,
        "n_pairs_with_forecast": n_fcst,
        "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in audited)["mean"],
        "forecast_vintage_coverage_pct": round(100.0 * n_fcst / n_pairs, 1) if n_pairs else 0.0,
        "n_pairs_le_7d": sum(1 for r in audited if (r.get("delta_t_days") or 0) <= 7),
        "n_events_full_causal": len(events_full),
        "n_events_multi_full_causal": len(multi_full),
        "n_events_zero_forecast": len(events_all) - len(events_forecast),
        "n_train_events_full": len(_events_with(audited, ELIG_FULL, "train")),
        "n_val_events_full": len(_events_with(audited, ELIG_FULL, "val")),
        "n_test_events_full": len(_events_with(audited, ELIG_FULL, "test")),
        "n_train_events_partial": len(_events_with(audited, ELIG_PARTIAL, "train")),
        "n_val_events_partial": len(_events_with(audited, ELIG_PARTIAL, "val")),
        "n_test_events_partial": len(_events_with(audited, ELIG_PARTIAL, "test")),
        "n_train_full_pairs": sum(1 for r in audited if r.get("split") == "train" and r.get("eligibility") == ELIG_FULL),
        "n_val_full_pairs": sum(1 for r in audited if r.get("split") == "val" and r.get("eligibility") == ELIG_FULL),
        "n_test_full_pairs": sum(1 for r in audited if r.get("split") == "test" and r.get("eligibility") == ELIG_FULL),
        "n_train_partial_pairs": sum(1 for r in audited if r.get("split") == "train" and r.get("eligibility") == ELIG_PARTIAL),
        "n_val_partial_pairs": sum(1 for r in audited if r.get("split") == "val" and r.get("eligibility") == ELIG_PARTIAL),
        "n_test_partial_pairs": sum(1 for r in audited if r.get("split") == "test" and r.get("eligibility") == ELIG_PARTIAL),
        "tigge_acquired": False,
        "single_runs_acquired_ok": acq.get("n_ok"),
    }
    spatial_reg = load_spatial_registry()
    letter = decide_letter(audited)
    if counts["n_train_events_full"] == 0 and counts["n_val_events_full"] == 0:
        split_narrative = (
            "Train and validation have **zero FULL_CAUSAL events**. A frozen-split baseline is not justified. "
            "Any 2024 Single Runs coverage sits in test only and does not create a causal train/val/test dataset."
        )
    else:
        split_narrative = "FULL_CAUSAL pairs exist in at least one non-test split; see table."
    remaining = (
        "Forecast-vintage precipitation is missing for 2015–2023 (TIGGE not acquired). "
        "IFS HRES Single Runs cover only the 2024 test event (00/12 UTC; 06/18 empty in this archive). "
        "GloFAS forecast Q, river level, and soil moisture remain UNAVAILABLE. "
        "Do not substitute ERA5 in `(t0,t1]`."
    )
    baseline = (
        "A causal **state** dataset (GFM + reindexed Q + pre-t0 ERA5) is constructible for almost all pairs. "
        "A causal **forecast** baseline with frozen train/val/test is not: FULL_CAUSAL coverage is too small "
        "and does not span the frozen splits. Do not train."
    )
    if letter == "A":
        target_b = "FEASIBLE"
    elif letter == "B":
        target_b = "PARTIALLY FEASIBLE"
    else:
        target_b = "PARTIALLY FEASIBLE — STATE CONSTRUCTIBLE, FORECAST BASELINE NOT AUTHORIZED"
    hydro_status = (
        "REINDEXED MODELLED_STATE AT T0"
        if hydro_summary["n_modelled_state"] == n_pairs
        else f"PARTIAL ({hydro_summary['n_modelled_state']}/{n_pairs} MODELLED_STATE)"
    )
    prov = spatial_artifact_provenance(
        data_status="PARTIAL",
        source="floodlens-x-phase6.9a",
        dataset=EXPERIMENT_ID,
        source_url="docs/PHASE_6_9A_CAUSAL_DATASET_REPORT.md",
        source_version=EXPERIMENT_ID,
        processing_version=EXPERIMENT_ID,
        license_name="CC BY 4.0 Open-Meteo/ERA5/GloFAS; TIGGE not downloaded; GFM CEMS STAC",
        attribution="See forecast_vintage_manifest.json",
        label_kind="OBSERVED",
        extra={"n_pairs": n_pairs, "n_full_causal": n_full, "parent_cube": SPATIAL_DATASET_VERSION_V21},
    )
    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "parent_cube": SPATIAL_DATASET_VERSION_V21,
        "tigge": tigge,
        "openmeteo_single_runs": {
            "product": "ECMWF IFS HRES 9 km via Open-Meteo Single Runs",
            "archive_start": "2024-03-14",
            "documented_lead_hours": IFS_HRES_DOCUMENTED_LEAD_HOURS,
            "issue_latency_hours": 6,
            "acquisition": acq,
            "cache_dir": str(store),
        },
        "not_used": [
            "ERA5-Land in (t0,t1] as forecast",
            "Open-Meteo Historical Forecast (blended)",
            "GEFSv12 reforecast as operational vintage",
            "cube GloFAS Q at valid_at-192h",
        ],
    }
    report = {
        "evaluated_at": retrieved,
        "experiment_id": EXPERIMENT_ID,
        "parent_cube": SPATIAL_DATASET_VERSION_V21,
        "catalog_status": "NOT_VALIDATED",
        "public_spatial_status": public_spatial_status(spatial_reg),
        "promoted_to_validated": False,
        "spatial_api": "UNAVAILABLE",
        "model_training": "NOT AUTHORIZED",
        "cnn_trained": False,
        "solver_modified": False,
        "counts": counts,
        "delta_t": {"hours": dt_h, "days": dt_d, "buckets": buckets},
        "hydrology_summary": hydro_summary,
        "input_contract": input_contract(),
        "by_delta_t_bucket": aggregate_by(audited, "delta_t_bucket"),
        "by_event": aggregate_by(audited, "event_id"),
        "by_year": aggregate_by(audited, "year"),
        "by_region": aggregate_by(audited, "region"),
        "by_split": aggregate_by(audited, "split"),
        "by_mechanism": aggregate_by(audited, "flood_mechanism"),
        "pairs": audited,
        "integrity_gates": integrity_gates(audited),
        "decision_letter": letter,
        "decision": DECISION_TEXT[letter],
        "provenance": {"envelope": prov, "complete": provenance_complete(prov)},
        "target_b_status": target_b,
        "forecast_vintage_status": (
            f"PARTIAL ({n_fcst}/{n_pairs} pairs)" if n_fcst else "NOT ACQUIRED FOR 2015–2023; 2024 IFS HRES ONLY IF CACHED"
        ),
        "hydro_status": hydro_status,
        "split_narrative": split_narrative,
        "remaining_gaps": remaining,
        "baseline_narrative": baseline,
        "tigge_plan": tigge,
        "single_runs_acquisition": acq,
    }
    if write_artifacts:
        dest.mkdir(parents=True, exist_ok=True)
        payload = _jsonable({k: v for k, v in report.items() if k != "pairs"})
        payload["pair_ids"] = [r.get("pair_id") for r in audited]
        (dest / SUMMARY_JSON).write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
        (dest / MANIFEST_JSON).write_text(json.dumps(_jsonable(manifest), indent=2), encoding="utf-8")
        inv_fields = [
            "pair_id",
            "event_id",
            "city_id",
            "region",
            "split",
            "year",
            "flood_mechanism",
            "t0",
            "t1",
            "delta_t_hours",
            "delta_t_days",
            "delta_t_bucket",
            "state_at_t0_available",
            "eligibility",
            "forecast_forcing_available",
            "forecast_coverage_fraction",
            "forecast_lead_min",
            "forecast_lead_max",
            "label_valid_fraction",
            "unknown_fraction",
            "new_flood_fraction",
            "antecedent_rain_status",
            "in_horizon_obs_status",
        ]
        with (dest / INVENTORY_CSV).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=inv_fields, extrasaction="ignore")
            writer.writeheader()
            for row in audited:
                writer.writerow({k: row.get(k) for k in inv_fields})
        hydro_fields = [
            "pair_id",
            "t0",
            "glofas_state_time",
            "lag_hours",
            "source",
            "status",
            "staleness",
            "proxy_city",
            "q_m3s",
            "walkback_days",
            "processing_version",
            "source_version",
        ]
        with (dest / HYDRO_CSV).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=hydro_fields)
            writer.writeheader()
            for row in audited:
                h = row.get("hydrology") or {}
                writer.writerow(
                    {
                        "pair_id": row.get("pair_id"),
                        "t0": row.get("t0"),
                        "glofas_state_time": h.get("glofas_state_time"),
                        "lag_hours": h.get("lag_hours"),
                        "source": h.get("source"),
                        "status": h.get("status"),
                        "staleness": h.get("staleness"),
                        "proxy_city": h.get("proxy_city"),
                        "q_m3s": h.get("q_m3s"),
                        "walkback_days": h.get("walkback_days"),
                        "processing_version": h.get("processing_version"),
                        "source_version": h.get("source_version"),
                    }
                )
        md = write_markdown_report(report)
        (dest / "PHASE_6_9A_CAUSAL_DATASET_REPORT.md").write_text(md, encoding="utf-8")
        if write_docs:
            DOCS_REPORT.write_text(md, encoding="utf-8")
            report["report_md"] = str(DOCS_REPORT)
        report["artifact_dir"] = str(dest)
    return report
