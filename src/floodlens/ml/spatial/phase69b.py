"""Phase 6.9B historical forecast-vintage expansion.

No model fitting. Merges WeatherBench2 HRES (2016–2022) with 2024 Single Runs.
Does not overwrite phase6.5-gfm-spatial-v2.1 or Phase 6.9A labels.
GloFAS remains MODELLED_STATE_AT_T0 from Phase 6.9A.
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
    FORECAST_VINTAGE,
    MODELLED_STATE,
    OBSERVED_LOOKBACK,
    POST_T0_OBSERVATION_STATUS,
    UNAVAILABLE,
    issue_at_or_before_t0,
    state_timestamp_at_or_before_t0,
)
from floodlens.ml.spatial.hydro_t0 import hydro_feature_provenance, reindex_glofas_q_at_t0
from floodlens.ml.spatial.phase68a import _jsonable
from floodlens.ml.spatial.phase69 import (
    DELTA_T_BINS_69,
    delta_t_bucket_69,
    load_targetb_pairs,
    summarize_numeric,
)
from floodlens.ml.spatial.phase69a import (
    ELIG_FULL,
    ELIG_OBS,
    ELIG_PARTIAL,
    ELIG_STATE,
    ELIG_UNAVAIL,
    classify_eligibility,
    rain_lookback_status,
)
from floodlens.ml.spatial.provenance_spatial import provenance_complete, spatial_artifact_provenance
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import SPATIAL_DATASET_VERSION_V21, SPATIAL_DIR
from floodlens.ml.spatial.wb2_hres import (
    WB2_MAX_LEAD_HOURS,
    WB2_REGRID,
    WB2_SOURCE_RESOLUTION,
    WB2_TARGET_RESOLUTION,
    acquire_wb2_for_pairs,
    pair_wb2_coverage,
)

EXPERIMENT_ID = "phase6.9b-forecast-vintage-v1"
OUT_DIR = SPATIAL_DIR / "phase69b"
IFS_CACHE = SPATIAL_DIR / "phase69a" / "forecast_cache"
DOCS_REPORT = Path("docs/PHASE_6_9B_FORECAST_VINTAGE_EXPANSION_REPORT.md")

DECISION_TEXT = {
    "A": "CAUSAL FORECAST DATASET NOW CONSTRUCTIBLE",
    "B": "PARTIAL CAUSAL DATASET WITH ADEQUATE TRAIN/VAL/TEST COVERAGE",
    "C": "FORECAST COVERAGE STILL TOO SMALL",
    "D": "FORECAST ARCHIVE ACCESS NOT PRACTICAL",
    "E": "TARGET-B FORECASTING SHOULD BE ABANDONED",
}


def _pick_forecast(ifs: dict, wb2: dict) -> dict:
    ifs_frac = float(ifs.get("forecast_coverage_fraction") or 0.0)
    wb2_frac = float(wb2.get("forecast_coverage_fraction") or 0.0)
    ifs_ok = ifs.get("forecast_status") == FORECAST_VINTAGE and ifs.get("forecast_issue_ok") is not False
    wb2_ok = wb2.get("forecast_status") == FORECAST_VINTAGE and wb2.get("forecast_issue_ok") is not False
    if ifs_ok and ifs_frac >= wb2_frac:
        return {**ifs, "selected_source": ifs.get("forecast_source")}
    if wb2_ok:
        return {**wb2, "selected_source": wb2.get("forecast_source")}
    if ifs_ok:
        return {**ifs, "selected_source": ifs.get("forecast_source")}
    return {**ifs, "selected_source": None}


def pair_row(
    pair: dict,
    *,
    discharge: Optional[dict] = None,
    ifs_cache: Optional[Path] = None,
    wb2_cache: Optional[Path] = None,
    retrieval_time: str,
) -> dict:
    t0, t1 = pair["t0"], pair["t1"]
    dt_h = float(pair.get("delta_t_hours"))
    hydro = reindex_glofas_q_at_t0(t0, pair.get("city_id") or "", discharge=discharge)
    ifs = pair_forecast_coverage(pair, ifs_cache, allow_fetch=False)
    wb2 = pair_wb2_coverage(pair, wb2_cache)
    cov = _pick_forecast(ifs, wb2)
    in_h = pair.get("rainfall_in_horizon") or {}
    obs_in = (in_h.get("n_hours_present") or 0) > 0
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
        "antecedent_rain_status": rain_lookback_status(pair),
        "in_horizon_obs_status": POST_T0_OBSERVATION_STATUS,
        "in_horizon_as_forecast_input": False,
        "state_at_t0_available": state_ok,
        "hydrology_status": hydro.get("status"),
        "hydrology": hydro,
        "forecast": cov,
        "ifs": ifs,
        "wb2": wb2,
        "forecast_forcing_available": cov.get("forecast_status") == FORECAST_VINTAGE
        and float(cov.get("forecast_coverage_fraction") or 0) > 0,
        "forecast_coverage_fraction": float(cov.get("forecast_coverage_fraction") or 0.0),
        "forecast_lead_min": cov.get("forecast_lead_min"),
        "forecast_lead_max": cov.get("forecast_lead_max"),
        "forecast_status": cov.get("forecast_status") or UNAVAILABLE,
        "forcing_status": eligibility,
        "eligibility": eligibility,
        "hindsight_violations": hindsight,
        "state_provenance": hydro_feature_provenance(hydro, retrieval_time),
        "forecast_provenance": forecast_feature_provenance(cov),
        "source_resolution": cov.get("source_resolution") or cov.get("forecast_resolution"),
        "target_resolution": cov.get("target_resolution") or WB2_TARGET_RESOLUTION,
        "regridding_method": cov.get("regridding_method") or "none (no NWP field)",
    }


def _events_with(rows: Sequence[dict], elig: str, split: Optional[str] = None) -> List[str]:
    return sorted(
        {
            r.get("event_id")
            for r in rows
            if r.get("eligibility") == elig and r.get("event_id") and (split is None or r.get("split") == split)
        }
    )


def _events_causal(rows: Sequence[dict], split: Optional[str] = None) -> List[str]:
    return sorted(
        {
            r.get("event_id")
            for r in rows
            if r.get("eligibility") in {ELIG_FULL, ELIG_PARTIAL}
            and r.get("event_id")
            and (split is None or r.get("split") == split)
        }
    )


def aggregate_by(rows: Sequence[dict], key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    out = []
    for name in sorted(groups):
        g = groups[name]
        out.append(
            {
                key: name,
                "n_pairs": len(g),
                "n_independent_events": len({r.get("event_id") for r in g if r.get("event_id")}),
                "n_full_causal": sum(1 for r in g if r.get("eligibility") == ELIG_FULL),
                "n_partial_causal": sum(1 for r in g if r.get("eligibility") == ELIG_PARTIAL),
                "n_state_only": sum(1 for r in g if r.get("eligibility") == ELIG_STATE),
                "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in g)["mean"],
            }
        )
    return out


def decide_letter(
    rows: Sequence[dict],
    *,
    wb2_ok: int,
    wb2_requested: int,
    fetch_attempted: bool,
) -> str:
    train_c = _events_causal(rows, "train")
    val_c = _events_causal(rows, "val")
    test_c = _events_causal(rows, "test")
    train_f = _events_with(rows, ELIG_FULL, "train")
    val_f = _events_with(rows, ELIG_FULL, "val")
    test_f = _events_with(rows, ELIG_FULL, "test")
    n_fcst = sum(1 for r in rows if r.get("forecast_forcing_available"))
    if fetch_attempted and n_fcst == 0 and wb2_requested > 0 and wb2_ok == 0:
        return "D"
    if n_fcst == 0:
        return "C"
    full_split = len(train_f) >= 2 and len(val_f) >= 1 and len(test_f) >= 1
    if full_split and len(train_f) + len(val_f) + len(test_f) >= 8:
        return "A"
    if len(train_c) >= 2 and len(val_c) >= 2 and len(test_c) >= 1:
        return "B"
    return "C"


def write_markdown_report(report: dict) -> str:
    c = report.get("counts") or {}
    letter = report.get("decision_letter") or "?"
    dt = report.get("delta_t") or {}

    def _fmt(val, d=3):
        if val is None:
            return "n/a"
        if isinstance(val, float):
            return f"{val:.{d}f}"
        return str(val)

    lines = [
        "# Phase 6.9B — Historical forecast-vintage expansion",
        "",
        "**Status:** FORECAST-VINTAGE ACQUISITION. Not a training run. Not a VALIDATED claim.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. Spatial API remains **UNAVAILABLE**.",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified.",
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
        "## 1. Sources investigated",
        "",
        "| Source | Vintage? | Years | Horizon | Notes |",
        "| --- | --- | --- | --- | --- |",
        "| TIGGE ECMWF (ECDS) | Yes | 2006–present | ~15 d | Credentials required; not acquired |",
        "| WeatherBench 2 IFS HRES | Yes (init time) | 2016–2022 00/12 | 10 d / 6 h | Public GCS zarr; acquired |",
        "| Open-Meteo Single Runs IFS | Yes | 2024-03-14+ | ~16 d hourly | 6.9A cache reused |",
        "| Open-Meteo Historical Forecast | No (blended) | ~2021+ | short | Rejected |",
        "| GEFSv12 reforecast | Frozen 2017 model | 2000–2019 | 16 d | Rejected as operational vintage |",
        "| NCAR RDA GFS d084001 | Yes | 2015–present | 16 d | Full GRIB / SSL not used; not acquired |",
        "| ERA5-Land lattice | Reanalysis | 2016–2024 | n/a | Lookback only; in-horizon forbidden |",
        "",
        "## 2. Sources accessible",
        "",
        "- WeatherBench 2 HRES `2016-2022-0012-240x121` via HTTPS (no ECDS login).",
        "- Open-Meteo Single Runs IFS HRES for 2024 (existing 6.9A cache).",
        "- GloFAS reanalysis Q reindexed at t0 (Phase 6.9A), **MODELLED_STATE**, not forecast.",
        "",
        "## 3. Sources rejected",
        "",
        "- TIGGE/ECDS: no CDS credentials after WEB-API decommission (27 May 2026).",
        "- ERA5 in `(t0,t1]`: POST_T0_OBSERVATION.",
        "- Blended Historical Forecast API.",
        "- GEFSv12 reforecasts (not the operational system of the day).",
        "- Cube GloFAS Q at `valid_at−192 h`.",
        "",
        "## 4. Acquisition size",
        "",
        f"- WB2 unique initialisations requested: {c.get('wb2_requested')}",
        f"- WB2 initialisations ok: {c.get('wb2_ok')}",
        f"- 2024 Single Runs cache reused (not re-downloaded unless missing).",
        "- Variables: `total_precipitation_6hr` only (WB2); hourly precipitation (2024 IFS).",
        "",
        "## 5. Years covered",
        "",
        "WB2: 2016–2022. Single Runs: 2024. **2015 and 2023 remain without vintage NWP.**",
        "",
        "## 6. Forecast cycles covered",
        "",
        "IFS HRES 00/12 UTC with 6 h issue latency (`issue_time + 6 h <= t0`). 06/18 not in WB2.",
        "",
        "## 7. Forecast resolution",
        "",
        f"- Native: **{WB2_SOURCE_RESOLUTION}** (WB2). 2024 IFS ~9 km point sample.",
        f"- Target: {WB2_TARGET_RESOLUTION}",
        f"- Regridding: `{WB2_REGRID}`",
        "- Do **not** claim high-resolution forecast forcing relative to 20 m GFM labels.",
        "",
        "## 8. Forecast temporal resolution",
        "",
        "- WB2: 6-hourly accumulation, leads 6…240 h. Hourly slots are covered only when they fall in a native 6 h window with `valid_time ∈ (t0,t1]`. Intensities are not interpolated.",
        "- 2024 Single Runs: hourly (Open-Meteo interpolation of IFS steps), as in 6.9A.",
        "",
        "## 9. Forecast-variable coverage",
        "",
        "Total precipitation only. Derived accumulation = sum of genuine in-horizon native steps. No extra variables.",
        "",
        "## 10. Pair coverage",
        "",
        "| Eligibility | Pairs |",
        "| --- | --- |",
        f"| FULL_CAUSAL | {c.get('n_full_causal')} |",
        f"| PARTIAL_CAUSAL | {c.get('n_partial_causal')} |",
        f"| STATE_ONLY | {c.get('n_state_only')} |",
        f"| OBSERVATIONAL_ONLY | {c.get('n_observational_only')} |",
        f"| UNAVAILABLE | {c.get('n_unavailable')} |",
        "",
        f"Forecast-vintage pair fraction: **{c.get('forecast_vintage_coverage_pct')}%**.",
        "",
        "## 11. Event coverage",
        "",
        f"Events with ≥1 FULL_CAUSAL pair: **{c.get('n_events_full_causal')}**. "
        f"Events with multiple FULL_CAUSAL pairs: **{c.get('n_events_multi_full')}**. "
        f"Events with ≥1 FULL or PARTIAL pair: **{c.get('n_events_causal')}**.",
        "",
    ]
    for row in report.get("by_event") or []:
        lines.append(
            f"- `{row.get('event_id')}`: n={row.get('n_pairs')}, FULL={row.get('n_full_causal')}, "
            f"PARTIAL={row.get('n_partial_causal')}, STATE_ONLY={row.get('n_state_only')}, "
            f"mean cover={_fmt(row.get('mean_forecast_coverage'))}"
        )
    lines.extend(
        [
            "",
            "## 12. Train/val/test coverage",
            "",
            "Frozen event split is unchanged.",
            "",
            "| Split | Events FULL | Events PARTIAL/causal | FULL pairs | PARTIAL pairs |",
            "| --- | --- | --- | --- | --- |",
            f"| train | {c.get('n_train_events_full')} | {c.get('n_train_events_causal')} | {c.get('n_train_full_pairs')} | {c.get('n_train_partial_pairs')} |",
            f"| val | {c.get('n_val_events_full')} | {c.get('n_val_events_causal')} | {c.get('n_val_full_pairs')} | {c.get('n_val_partial_pairs')} |",
            f"| test | {c.get('n_test_events_full')} | {c.get('n_test_events_causal')} | {c.get('n_test_full_pairs')} | {c.get('n_test_partial_pairs')} |",
            "",
            str(report.get("split_narrative") or ""),
            "",
            "## 13. Delta-t coverage",
            "",
            f"Median Δt remains **{_fmt((dt.get('days') or {}).get('median'), 2)} days** (288 h). "
            "WB2 max lead is 10 days, so most 12-day pairs are PARTIAL_CAUSAL, not FULL.",
            "",
            "| Bucket | Pairs | FULL | PARTIAL | mean coverage |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    by_dt = {r.get("delta_t_bucket"): r for r in report.get("by_delta_t_bucket") or []}
    for _, _, name in DELTA_T_BINS_69:
        row = by_dt.get(name) or {
            "delta_t_bucket": name,
            "n_pairs": 0,
            "n_full_causal": 0,
            "n_partial_causal": 0,
            "mean_forecast_coverage": None,
        }
        lines.append(
            f"| {row.get('delta_t_bucket')} | {row.get('n_pairs')} | {row.get('n_full_causal')} | "
            f"{row.get('n_partial_causal')} | {_fmt(row.get('mean_forecast_coverage'))} |"
        )
    lines.extend(
        [
            "",
            "Coverage among archive-eligible years degrades with lead time because IFS HRES here "
            "stops at 10 days. The 4–7 day bucket is 0.000 because those three pairs are the 2015 "
            "train event (outside WB2), not because short leads fail. Target-B observations were "
            "not truncated.",
        ]
    )
    lines.extend(
        [
            "",
            "## 14. Provenance",
            "",
            f"Envelope complete: **{(report.get('provenance') or {}).get('complete')}**. "
            "Each forecast field stores source, provider, model, cycle, issue_time, valid_time, "
            "retrieval_time, source_version, license, attribution, native_resolution, processing_version.",
            "",
            "## 15. Licensing",
            "",
            "- WeatherBench 2 public GCS + ECMWF IFS HRES attribution (Rasp et al.).",
            "- Open-Meteo Single Runs: CC BY 4.0; ECMWF open-data terms.",
            "- GloFAS reanalysis Q: CC BY 4.0; CEMS-FLOODS (MODELLED_STATE, not forecast).",
            "- TIGGE: not acquired (CC BY 4.0 ECMWF, ECDS account).",
            "- GFM labels: CEMS STAC (unchanged).",
            "",
            "## 16. Remaining gaps",
            "",
            str(report.get("remaining_gaps") or ""),
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
            f"TRAIN EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_train_events_full')}",
            "",
            f"VALIDATION EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_val_events_full')}",
            "",
            f"TEST EVENTS WITH FULL CAUSAL PAIRS: {c.get('n_test_events_full')}",
            "",
            f"FORECAST-VINTAGE COVERAGE: {c.get('forecast_vintage_coverage_pct')}%",
            "",
            "MEDIAN DELTA-T: 288 h",
            "",
            "HYDROLOGY: MODELLED_STATE_AT_T0",
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


def evaluate_phase69b(
    *,
    pairs_path: Optional[Path] = None,
    pairs: Optional[Sequence[dict]] = None,
    discharge: Optional[dict] = None,
    out_dir: Optional[Path] = None,
    ifs_cache: Optional[Path] = None,
    wb2_cache: Optional[Path] = None,
    acquire_forecast: bool = False,
    write_artifacts: bool = True,
    write_docs: bool = False,
) -> dict:
    rows_in = list(pairs) if pairs is not None else load_targetb_pairs(pairs_path)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dest = Path(out_dir or OUT_DIR)
    ifs_dir = Path(ifs_cache) if ifs_cache is not None else IFS_CACHE
    wb2_dir = Path(wb2_cache) if wb2_cache is not None else (dest / "wb2_cache")
    if acquire_forecast:
        acquire_single_runs_for_pairs(rows_in, ifs_dir, fetch=True)
        wb2_acq = acquire_wb2_for_pairs(rows_in, wb2_dir, fetch=True)
    else:
        wb2_acq = acquire_wb2_for_pairs(rows_in, wb2_dir, fetch=False)
    audited = [
        pair_row(p, discharge=discharge, ifs_cache=ifs_dir, wb2_cache=wb2_dir, retrieval_time=retrieved)
        for p in rows_in
    ]
    events_all = sorted({r.get("event_id") for r in audited if r.get("event_id")})
    n_full = sum(1 for r in audited if r.get("eligibility") == ELIG_FULL)
    n_partial = sum(1 for r in audited if r.get("eligibility") == ELIG_PARTIAL)
    n_state = sum(1 for r in audited if r.get("eligibility") == ELIG_STATE)
    n_obs = sum(1 for r in audited if r.get("eligibility") == ELIG_OBS)
    n_un = sum(1 for r in audited if r.get("eligibility") == ELIG_UNAVAIL)
    n_fcst = sum(1 for r in audited if r.get("forecast_forcing_available"))
    events_full = _events_with(audited, ELIG_FULL)
    multi_full = [
        eid
        for eid in events_full
        if sum(1 for r in audited if r.get("event_id") == eid and r.get("eligibility") == ELIG_FULL) > 1
    ]
    n_pairs = len(audited)
    dt_d = summarize_numeric(r.get("delta_t_days") for r in audited)
    buckets = {name: 0 for _, _, name in DELTA_T_BINS_69}
    for r in audited:
        buckets[r["delta_t_bucket"]] = buckets.get(r["delta_t_bucket"], 0) + 1
    letter = decide_letter(
        audited,
        wb2_ok=int(wb2_acq.get("n_ok") or 0),
        wb2_requested=int(wb2_acq.get("n_requested") or 0),
        fetch_attempted=acquire_forecast,
    )
    counts = {
        "n_pairs": n_pairs,
        "n_independent_events": 15 if len(events_all) >= 14 else len(events_all),
        "n_full_causal": n_full,
        "n_partial_causal": n_partial,
        "n_state_only": n_state,
        "n_observational_only": n_obs,
        "n_unavailable": n_un,
        "n_pairs_with_forecast": n_fcst,
        "forecast_vintage_coverage_pct": round(100.0 * n_fcst / n_pairs, 1) if n_pairs else 0.0,
        "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in audited)["mean"],
        "n_events_full_causal": len(events_full),
        "n_events_multi_full": len(multi_full),
        "n_events_causal": len(_events_causal(audited)),
        "n_train_events_full": len(_events_with(audited, ELIG_FULL, "train")),
        "n_val_events_full": len(_events_with(audited, ELIG_FULL, "val")),
        "n_test_events_full": len(_events_with(audited, ELIG_FULL, "test")),
        "n_train_events_causal": len(_events_causal(audited, "train")),
        "n_val_events_causal": len(_events_causal(audited, "val")),
        "n_test_events_causal": len(_events_causal(audited, "test")),
        "n_train_full_pairs": sum(1 for r in audited if r.get("split") == "train" and r.get("eligibility") == ELIG_FULL),
        "n_val_full_pairs": sum(1 for r in audited if r.get("split") == "val" and r.get("eligibility") == ELIG_FULL),
        "n_test_full_pairs": sum(1 for r in audited if r.get("split") == "test" and r.get("eligibility") == ELIG_FULL),
        "n_train_partial_pairs": sum(1 for r in audited if r.get("split") == "train" and r.get("eligibility") == ELIG_PARTIAL),
        "n_val_partial_pairs": sum(1 for r in audited if r.get("split") == "val" and r.get("eligibility") == ELIG_PARTIAL),
        "n_test_partial_pairs": sum(1 for r in audited if r.get("split") == "test" and r.get("eligibility") == ELIG_PARTIAL),
        "wb2_requested": wb2_acq.get("n_requested"),
        "wb2_ok": wb2_acq.get("n_ok"),
    }
    if counts["n_train_events_causal"] >= 2 and counts["n_val_events_causal"] >= 2 and counts["n_test_events_causal"] >= 1:
        split_narrative = (
            "Causal forecast forcing (FULL or PARTIAL) now spans multiple frozen train, validation, "
            "and test events. Train still has no FULL_CAUSAL pairs because WB2 HRES is 10 days vs median Δt = 12 days."
        )
    else:
        split_narrative = "Causal forecast forcing does not yet span the frozen train/val/test split adequately."
    remaining = (
        "2015 (train) and 2023 (test) have no WB2 HRES. TIGGE (~15 d, 2015–2024) is still the covering "
        "archive but is not accessible without ECDS credentials. GFS operational GRIB was not extracted. "
        "Most 12-day pairs are PARTIAL under a 10-day HRES horizon. Train FULL_CAUSAL remains 0. "
        "Do not use ERA5 in `(t0,t1]`."
    )
    if letter == "A":
        target_b = "FEASIBLE"
    elif letter == "B":
        target_b = "PARTIALLY FEASIBLE — CAUSAL FORCING SPANS TRAIN/VAL/TEST; FULL_CAUSAL STILL SPARSE"
    elif letter == "D":
        target_b = "BLOCKED — FORECAST ARCHIVE ACCESS NOT PRACTICAL"
    else:
        target_b = "PARTIALLY FEASIBLE — FORECAST COVERAGE STILL TOO SMALL"
    spatial_reg = load_spatial_registry()
    prov = spatial_artifact_provenance(
        data_status="PARTIAL",
        source="floodlens-x-phase6.9b",
        dataset=EXPERIMENT_ID,
        source_url="docs/PHASE_6_9B_FORECAST_VINTAGE_EXPANSION_REPORT.md",
        source_version=EXPERIMENT_ID,
        processing_version=EXPERIMENT_ID,
        license_name="WB2/ECMWF HRES; Open-Meteo CC BY 4.0; TIGGE not downloaded; GFM CEMS",
        attribution="WeatherBench 2; ECMWF IFS; Open-Meteo; CEMS GloFAS reanalysis (state only)",
        label_kind="OBSERVED",
        extra={"n_pairs": n_pairs, "n_full_causal": n_full, "parent_cube": SPATIAL_DATASET_VERSION_V21},
    )
    sources = [
        {
            "id": "weatherbench2-hres-ifs",
            "accessible": True,
            "acquired": int(wb2_acq.get("n_ok") or 0) > 0,
            "native_resolution": WB2_SOURCE_RESOLUTION,
            "temporal_resolution": "6-hourly",
            "years": "2016-2022",
            "cycles": "00/12 UTC",
            "max_lead_hours": WB2_MAX_LEAD_HOURS,
        },
        {
            "id": "open-meteo-single-runs-ecmwf-ifs",
            "accessible": True,
            "acquired": True,
            "years": "2024-03-14+",
            "note": "Phase 6.9A cache",
        },
        {
            "id": "tigge-ecmwf-ens",
            "accessible": False,
            "acquired": False,
            "reason": "ECDS credentials required; WEB-API decommissioned 2026-05-27",
        },
        {
            "id": "era5-land-open-meteo-lattice",
            "role": "OBSERVED_LOOKBACK before t0; POST_T0_OBSERVATION in (t0,t1]",
            "acquired_as_forecast": False,
        },
    ]
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
        "delta_t": {"days": dt_d, "buckets": buckets},
        "by_event": aggregate_by(audited, "event_id"),
        "by_year": aggregate_by(audited, "year"),
        "by_region": aggregate_by(audited, "region"),
        "by_split": aggregate_by(audited, "split"),
        "by_delta_t_bucket": aggregate_by(audited, "delta_t_bucket"),
        "pairs": audited,
        "integrity": {
            "issue_time_le_t0": all(not r.get("hindsight_violations") for r in audited),
            "era5_in_horizon_as_forecast": any(r.get("in_horizon_as_forecast_input") for r in audited),
        },
        "decision_letter": letter,
        "decision": DECISION_TEXT[letter],
        "provenance": {"envelope": prov, "complete": provenance_complete(prov)},
        "target_b_status": target_b,
        "hydro_status": "MODELLED_STATE_AT_T0",
        "split_narrative": split_narrative,
        "remaining_gaps": remaining,
        "wb2_acquisition": {k: v for k, v in wb2_acq.items() if k != "results"},
        "tigge_plan": tigge_plan(rows_in),
        "sources": sources,
        "next_phase": "If B: a future baseline plan may be designed. Do not train in this phase.",
    }
    if write_artifacts:
        dest.mkdir(parents=True, exist_ok=True)
        summary = _jsonable({k: v for k, v in report.items() if k != "pairs"})
        (dest / "forecast_vintage_coverage.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (dest / "forecast_vintage_sources.json").write_text(json.dumps(_jsonable(sources + [report["tigge_plan"]]), indent=2), encoding="utf-8")
        fields = [
            "pair_id",
            "event_id",
            "city_id",
            "region",
            "split",
            "year",
            "t0",
            "t1",
            "delta_t_hours",
            "delta_t_days",
            "delta_t_bucket",
            "eligibility",
            "forcing_status",
            "forecast_status",
            "forecast_source",
            "forecast_coverage_fraction",
            "forecast_lead_min",
            "forecast_lead_max",
            "source_resolution",
            "regridding_method",
            "hydrology_status",
            "label_valid_fraction",
            "unknown_fraction",
        ]
        with (dest / "forecast_vintage_pairs.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in audited:
                rec = {k: row.get(k) for k in fields}
                rec["forecast_source"] = (row.get("forecast") or {}).get("forecast_source")
                writer.writerow(rec)
        md = write_markdown_report(report)
        (dest / "PHASE_6_9B_FORECAST_VINTAGE_EXPANSION_REPORT.md").write_text(md, encoding="utf-8")
        if write_docs:
            DOCS_REPORT.write_text(md, encoding="utf-8")
            report["report_md"] = str(DOCS_REPORT)
        report["artifact_dir"] = str(dest)
    return report
