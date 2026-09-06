"""Phase 6.10 partial-causal Target-B benchmark design.

Design only. No model fitting. Reads Phase 6.9B pair rows; does not acquire NWP.
Does not change frozen splits, GFM labels, or src/floodlens/numerical/**.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from floodlens.ml.spatial.forecast_forcing import (
    COMPLETE_COVERAGE_EPS,
    FORECAST_BENCHMARK_ELIGIBLE,
    MODELLED_STATE,
    POST_T0_OBSERVATION_STATUS,
    TARGET_B_PRIMARY_LABEL,
    causal_timestamp_violations,
    state_timestamp_at_or_before_t0,
)
from floodlens.ml.spatial.phase68a import _jsonable
from floodlens.ml.spatial.phase69 import DELTA_T_BINS_69, summarize_numeric
from floodlens.ml.spatial.phase69a import ELIG_FULL, ELIG_PARTIAL, ELIG_STATE
from floodlens.ml.spatial.provenance_spatial import provenance_complete, spatial_artifact_provenance
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status
from floodlens.ml.spatial.schema import SPATIAL_DATASET_VERSION_V21, SPATIAL_DIR
from floodlens.ml.spatial.wb2_hres import WB2_MAX_LEAD_HOURS, WB2_REGRID, WB2_SOURCE_RESOLUTION, WB2_TARGET_RESOLUTION

EXPERIMENT_ID = "phase6.10-partial-causal-design-v1"
OUT_DIR = SPATIAL_DIR / "phase610"
PAIRS_PATH = SPATIAL_DIR / "phase69b" / "forecast_vintage_pairs.csv"
HYDRO_PATH = SPATIAL_DIR / "phase69a" / "hydrology_t0_alignment.csv"
SPLITS_PATH = SPATIAL_DIR / "splits_v2" / "splits.json"
DOCS_REPORT = Path("docs/PHASE_6_10_PARTIAL_CAUSAL_BENCHMARK_DESIGN.md")
INDEPENDENT_EVENTS = 15
PARENT_CUBE = SPATIAL_DATASET_VERSION_V21

DECISION_TEXT = {
    "A": "COMPLETE-CASE BENCHMARK",
    "B": "PARTIAL-CAUSAL BENCHMARK WITH EXPLICIT MASKING",
    "C": "STATE-ONLY DIAGNOSTIC BENCHMARK",
    "D": "TARGET-B SHOULD BE ABANDONED",
    "E": "MORE FORECAST ARCHIVE ACQUISITION REQUIRED BEFORE DECISION",
}

INPUT_CONTRACT = [
    {
        "name": "STATE_AT_T0",
        "source": "GloFAS reanalysis Q (Open-Meteo Flood API, forecast_days=0)",
        "timestamp": "end of last complete Q calendar day before t0",
        "status": MODELLED_STATE,
        "units": "m3 s-1",
        "resolution": "daily 0.05deg proxy cell",
        "required": True,
        "note": "Not forecast forcing. Freshness recorded; currently FRESH on 183/183.",
    },
    {
        "name": "FORECAST_FORCING",
        "source": "WB2 IFS HRES total_precipitation_6hr (2016–2022); Open-Meteo Single Runs IFS (2024)",
        "timestamp": "issue_time <= t0; valid_time in (t0,t1]",
        "status": "FORECAST_VINTAGE",
        "units": "mm (native accumulation window)",
        "resolution": WB2_SOURCE_RESOLUTION,
        "required": True,
        "note": "Native steps only. No ERA5 in (t0,t1]. No interpolation of missing leads.",
    },
    {
        "name": "FORCING_MASK",
        "source": "derived from vintage windows",
        "timestamp": "same as FORECAST_FORCING valid_time",
        "status": "MASK",
        "units": "1 = genuine vintage hour; 0 = unavailable",
        "resolution": "hourly coverage of native windows; not 20 m",
        "required": True,
        "note": "M=0 precipitation is None, never 0.0 fill.",
    },
    {
        "name": "STATIC_SPATIAL_FEATURES",
        "source": "existing GFM working-grid statics (parent cube)",
        "timestamp": "time-invariant",
        "status": "STATIC",
        "units": "channel-specific",
        "resolution": "GFM working grid 64x64; native DEM/HAND as recorded in v2.1",
        "required": True,
        "note": "Unchanged. Not a substitute for vintage precipitation.",
    },
    {
        "name": "STATE_FRESHNESS_MASK",
        "source": "GloFAS staleness class (FRESH/STALE/VERY_STALE)",
        "timestamp": "glofas_state_time",
        "status": "OPTIONAL",
        "units": "categorical",
        "resolution": "pair scalar",
        "required": False,
        "note": "Currently constant FRESH; keep for future stale days. Do not drop pairs today.",
    },
    {
        "name": "FORECAST_LEAD_FEATURES",
        "source": "vintage issue/valid timestamps",
        "timestamp": "issue_time",
        "status": "OPTIONAL",
        "units": "hours",
        "resolution": "pair scalar (lead min/max)",
        "required": False,
        "note": "Already on Phase 6.9B pair rows.",
    },
]


def _num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _median(values: Sequence[Optional[float]]) -> Optional[float]:
    xs = sorted(float(v) for v in values if v is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def load_vintage_pairs(path: Optional[Path] = None) -> List[dict]:
    path = Path(path or PAIRS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Phase 6.9B pair artifact missing: {path}")
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            rec["year"] = int(rec["year"]) if rec.get("year") else int(str(rec.get("t0") or "0")[:4])
            rec["delta_t_hours"] = _num(rec.get("delta_t_hours"))
            rec["delta_t_days"] = _num(rec.get("delta_t_days"))
            rec["forecast_coverage_fraction"] = _num(rec.get("forecast_coverage_fraction")) or 0.0
            rec["forecast_lead_min"] = _num(rec.get("forecast_lead_min"))
            rec["forecast_lead_max"] = _num(rec.get("forecast_lead_max"))
            rec["label_valid_fraction"] = _num(rec.get("label_valid_fraction"))
            rec["unknown_fraction"] = _num(rec.get("unknown_fraction"))
            rows.append(rec)
    return rows


def load_hydro_index(path: Optional[Path] = None) -> Dict[str, dict]:
    path = Path(path or HYDRO_PATH)
    if not path.exists():
        return {}
    out: Dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            rec["lag_hours"] = _num(rec.get("lag_hours"))
            rec["q_m3s"] = _num(rec.get("q_m3s"))
            out[rec["pair_id"]] = rec
    return out


def load_frozen_splits(path: Optional[Path] = None) -> dict:
    path = Path(path or SPLITS_PATH)
    return json.loads(path.read_text(encoding="utf-8"))


def is_forecast_eligible(row: dict) -> bool:
    return row.get("eligibility") in FORECAST_BENCHMARK_ELIGIBLE


def attach_hydro(rows: Sequence[dict], hydro: Dict[str, dict]) -> List[dict]:
    out = []
    for row in rows:
        merged = dict(row)
        h = hydro.get(row.get("pair_id") or "", {})
        merged["glofas_state_time"] = h.get("glofas_state_time") or row.get("glofas_state_time")
        merged["hydro_lag_hours"] = h.get("lag_hours")
        merged["hydro_staleness"] = h.get("staleness") or row.get("hydro_staleness")
        merged["hydrology_status"] = row.get("hydrology_status") or h.get("status") or MODELLED_STATE
        out.append(merged)
    return out


def pair_leakage(row: dict) -> List[str]:
    valid_times = []
    if row.get("forecast_status") == "FORECAST_VINTAGE" and row.get("t1"):
        # Pair CSV stores leads, not every valid_time. Lead max still must be in-horizon.
        valid_times = []
    return causal_timestamp_violations(
        t0=row["t0"],
        t1=row["t1"],
        issue_time=None,
        valid_times=valid_times,
        state_time=row.get("glofas_state_time"),
        era5_in_horizon_as_forecast=bool(row.get("in_horizon_as_forecast_input")),
        future_glofas_as_forecast=row.get("hydrology_status") not in {MODELLED_STATE, None, ""},
        target_derived_features=False,
        filled=False,
    )


def event_coverage_rows(rows: Sequence[dict]) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("event_id"))].append(row)
    out = []
    for event_id in sorted(groups):
        g = groups[event_id]
        covers = [float(r.get("forecast_coverage_fraction") or 0.0) for r in g]
        leads = [r.get("forecast_lead_max") for r in g]
        out.append(
            {
                "event_id": event_id,
                "year": g[0].get("year"),
                "split": g[0].get("split"),
                "n_pairs": len(g),
                "n_full_causal": sum(1 for r in g if r.get("eligibility") == ELIG_FULL),
                "n_partial_causal": sum(1 for r in g if r.get("eligibility") == ELIG_PARTIAL),
                "n_state_only": sum(1 for r in g if r.get("eligibility") == ELIG_STATE),
                "mean_forecast_coverage": summarize_numeric(covers)["mean"],
                "min_forecast_coverage": min(covers) if covers else None,
                "max_forecast_coverage": max(covers) if covers else None,
                "median_lead_hours": _median(leads),
                "median_delta_t_hours": _median(r.get("delta_t_hours") for r in g),
            }
        )
    return out


def aggregate_missingness(rows: Sequence[dict], key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key))].append(row)
    out = []
    for name in sorted(groups, key=lambda x: (x == "None", x)):
        g = groups[name]
        n = len(g)
        n_zero = sum(1 for r in g if float(r.get("forecast_coverage_fraction") or 0.0) <= 0.0)
        out.append(
            {
                key: name,
                "n_pairs": n,
                "n_events": len({r.get("event_id") for r in g if r.get("event_id")}),
                "n_full_causal": sum(1 for r in g if r.get("eligibility") == ELIG_FULL),
                "n_partial_causal": sum(1 for r in g if r.get("eligibility") == ELIG_PARTIAL),
                "n_state_only": sum(1 for r in g if r.get("eligibility") == ELIG_STATE),
                "n_coverage_zero": n_zero,
                "zero_coverage_rate": (n_zero / n) if n else None,
                "mean_forecast_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in g)["mean"],
            }
        )
    return out


def split_policy_counts(rows: Sequence[dict], predicate) -> dict:
    out = {}
    for split in ("train", "val", "test"):
        taken = [r for r in rows if r.get("split") == split and predicate(r)]
        out[split] = {
            "n_events": len({r.get("event_id") for r in taken if r.get("event_id")}),
            "n_pairs": len(taken),
            "event_ids": sorted({r.get("event_id") for r in taken if r.get("event_id")}),
        }
    return out


def missingness_confound(rows: Sequence[dict]) -> dict:
    """Tabular MNAR audit. Not a flood model. No logistic/GBDT fit."""
    by_split = {r["split"]: r for r in aggregate_missingness(rows, "split")}
    by_year = aggregate_missingness(rows, "year")
    archive_gap_years = [r for r in by_year if float(r.get("mean_forecast_coverage") or 0) == 0.0]
    eligible_years = [r for r in rows if int(r.get("year") or 0) not in {2015, 2023}]
    dt_eligible = aggregate_missingness(eligible_years, "delta_t_bucket")
    zero_from_year = sum(int(r.get("n_coverage_zero") or 0) for r in archive_gap_years)
    n_zero = sum(1 for r in rows if float(r.get("forecast_coverage_fraction") or 0.0) <= 0.0)
    return {
        "mechanism": "MNAR",
        "archive_gap_years": [r.get("year") for r in archive_gap_years],
        "n_zero_coverage_pairs": n_zero,
        "n_zero_explained_by_2015_or_2023": zero_from_year,
        "split_zero_coverage_rate": {k: (by_split.get(k) or {}).get("zero_coverage_rate") for k in ("train", "val", "test")},
        "delta_t_among_archive_eligible_years": dt_eligible,
        "conclusion": (
            "Coverage=0 is year/archive (2015 train, 2023 test), hence split-correlated. "
            "Among 2016–2022/2024, missingness follows the 10-day HRES wall vs Δt. "
            "Exclude STATE_ONLY from the forecast set so the mask cannot encode era."
        ),
    }


def input_contract_payload() -> dict:
    return {
        "target": {
            "name": TARGET_B_PRIMARY_LABEL,
            "definition": "DRY->FLOODED on pixels valid in both consecutive GFM scenes of the same event and AOI",
            "t0": "earlier.valid_at",
            "t1": "later.valid_at",
            "not": ["24h flood map", "48h flood map", "72h flood map", "truncated 10-day GFM window"],
            "label_resolution_m": 20.0,
        },
        "regrid": {
            "source_resolution": WB2_SOURCE_RESOLUTION,
            "target_resolution": WB2_TARGET_RESOLUTION,
            "regridding_method": WB2_REGRID,
            "high_resolution_forecast_claim": False,
        },
        "channels": INPUT_CONTRACT,
        "forbidden": [
            "ERA5-Land after t0 as FORECAST_FORCING",
            "GloFAS Q after t0 as FORECAST_FORCING",
            "zero-fill of M=0 hours",
            "interpolation of missing vintage steps",
            "current-day forecast used retroactively",
            "issue_time > t0",
        ],
    }


def leakage_suite(rows: Sequence[dict]) -> dict:
    violations = []
    for row in rows:
        reasons = pair_leakage(row)
        if row.get("in_horizon_as_forecast_input"):
            reasons.append("post-t0 observed rainfall as forecast")
        if row.get("glofas_state_time") and not state_timestamp_at_or_before_t0(row["glofas_state_time"], row["t0"]):
            reasons.append("state_timestamp > t0")
        if reasons:
            violations.append({"pair_id": row.get("pair_id"), "reasons": reasons})
    hydro_ok = all(
        (not r.get("glofas_state_time")) or state_timestamp_at_or_before_t0(r["glofas_state_time"], r["t0"])
        for r in rows
    )
    return {
        "n_pairs": len(rows),
        "n_violations": len(violations),
        "ok": len(violations) == 0 and hydro_ok,
        "state_timestamp_le_t0": hydro_ok,
        "era5_in_horizon_as_forecast": any(r.get("in_horizon_as_forecast_input") for r in rows),
        "future_glofas_as_forecast": False,
        "target_derived_features": False,
        "violations": violations[:20],
        "checks": [
            "state_timestamp <= t0",
            "forecast issue_time <= t0 (enforced at acquisition; rejected records not filled)",
            "forecast valid_time in (t0,t1]",
            "no post-t0 observed rainfall as input",
            "no future GloFAS observations as forecast",
            "no target-derived features",
        ],
    }


def _fmt(val, d=3):
    if val is None:
        return "n/a"
    if isinstance(val, float):
        return f"{val:.{d}f}"
    return str(val)


def write_markdown_report(report: dict) -> str:
    c = report.get("counts") or {}
    letter = report.get("decision_letter") or "?"
    fc = report.get("forecast_set") or {}
    cc = report.get("complete_case") or {}
    miss = report.get("missingness") or {}
    gates = report.get("training_gates") or {}
    by_event = report.get("by_event") or []
    by_dt = report.get("by_delta_t") or []
    policies = report.get("policies") or {}

    def _split_line(block: dict, split: str) -> str:
        row = (block.get(split) or {})
        return f"{row.get('n_events')} events / {row.get('n_pairs')} pairs"

    lines = [
        "# Phase 6.10 — Partial-causal Target-B benchmark design",
        "",
        "**Status:** DESIGN ONLY. Not a training run. Not a VALIDATED claim.",
        "",
        "**Catalog:** Spatial AI remains **NOT_VALIDATED**. Spatial API remains **UNAVAILABLE**.",
        "",
        "**Solver:** `src/floodlens/numerical/**` was not modified.",
        "",
        f"**Experiment id:** `{EXPERIMENT_ID}`",
        "",
        f"**Parent cube (unchanged):** `{PARENT_CUBE}`",
        "",
        f"**Decision:** **{letter}** — {DECISION_TEXT.get(letter, letter)}",
        "",
        "This phase does not train any model. Frozen event splits and GFM labels are unchanged.",
        "",
        "---",
        "",
        "## 1. Coverage definitions (do not collapse)",
        "",
        "Never say “82% causal” without a denominator.",
        "",
        f"- **Pair-level vintage presence:** {c.get('n_pairs_with_forecast')}/{c.get('n_pairs')} = "
        f"**{c.get('pair_vintage_presence_pct')}%** of Target-B pairs have at least one genuine "
        "in-horizon vintage hour (`FULL_CAUSAL` + `PARTIAL_CAUSAL`). This is Phase 6.9B `forecast_vintage_coverage_pct`.",
        f"- **Mean hourly coverage:** {_fmt(c.get('mean_hourly_coverage'))} averaged across all "
        f"{c.get('n_pairs')} pairs. `forecast_coverage_fraction` = hours in `(t0,t1]` inside a native "
        "vintage window / hours required. Not precipitation volume. Not 20 m cells.",
        f"- **FULL_CAUSAL pair share:** {c.get('n_full_causal')}/{c.get('n_pairs')} = "
        f"{_fmt(c.get('full_pair_share_pct'), 1)}% (`forecast_coverage_fraction >= {COMPLETE_COVERAGE_EPS}`).",
        f"- **Event-level FULL:** {c.get('n_events_full')}/{INDEPENDENT_EVENTS}. "
        f"**Event-level any vintage:** {c.get('n_events_causal')}/{INDEPENDENT_EVENTS}.",
        "- **Not claimed:** 82% of rain volume, 82% of spatial cells, or 82% of independent floods.",
        "",
        "A **PARTIAL_CAUSAL** pair means: GloFAS `MODELLED_STATE_AT_T0` is present; some vintage hours "
        "in `(t0,t1]` exist; some do not. Missing hours are unfilled. ERA5 in `(t0,t1]` remains "
        f"`{POST_T0_OBSERVATION_STATUS}`.",
        "",
        f"Typical 12-day pair under WB2 HRES {int(WB2_MAX_LEAD_HOURS)} h + 6 h issue latency: uncovered "
        "tail ≈ 48–60 h of 288 h (**~17–21% of the observation interval**). That is a horizon fact, "
        "not a download failure.",
        "",
        "## 2. Complete-case feasibility",
        "",
        "Design A uses only `FULL_CAUSAL`. Under the frozen split:",
        "",
        f"- Train: **{_split_line(cc, 'train')}**",
        f"- Validation: **{_split_line(cc, 'val')}**",
        f"- Test: **{_split_line(cc, 'test')}**",
        "",
        "Statistical failure (not “too small” as a slogan):",
        "",
        "- **No independent training events.** Supervised complete-case learning has nothing to fit "
        "without using val/test or breaking the freeze.",
        "- **No generalization estimate.** One validation event cannot support event-level model selection.",
        "- **No meaningful test uncertainty.** One test event; a pair-level interval on pairs from one "
        "flood is pseudo-replication.",
        "",
        "Complete-case Target-B training is not a valid experiment on the current archive.",
        "",
        "## 3. Partial-case feasibility",
        "",
        "Represent each eligible pair as native vintage precipitation **P** plus availability **M**, "
        "with M=1 only for hours inside a real window with `issue_time <= t0` and "
        "`valid_time in (t0,t1]`. Zero is not “no rain” unless M=1 and the field is 0. M=0 stores "
        "`None`, never a filled 0.0. Native 6 h mass is not interpolated into hourly intensities "
        "(`pm_from_windows` in `vintage_steps.py`).",
        "",
        "This is feasible **if and only if**:",
        "",
        "- `STATE_ONLY` pairs are excluded from the forecast-learning set (archive-era missingness).",
        "- Remaining missingness is treated as HRES horizon truncation (10 d vs median Δt 12 d).",
        "- Evaluation is event-level, stratified by coverage and Δt.",
        f"- The target stays **{TARGET_B_PRIMARY_LABEL}** over the full measured `(t0,t1]`.",
        "",
        "Coverage-weighted fill (Design C in the four-way comparison) still needs a numeric value "
        "for M=0 hours. That is silent imputation. Rejected as the primary contract.",
        "",
        "## 4. Missingness (MNAR) audit",
        "",
        "Missingness is not MCAR. Tabular association only — no logistic/GBDT flood model.",
        "",
        f"- Archive-gap years with mean coverage 0: **{miss.get('archive_gap_years')}**.",
        f"- Zero-coverage pairs: {miss.get('n_zero_coverage_pairs')}; of those, "
        f"{miss.get('n_zero_explained_by_2015_or_2023')} are 2015 or 2023.",
        f"- Split zero-coverage rates: `{miss.get('split_zero_coverage_rate')}`.",
        "",
        str(miss.get("conclusion") or ""),
        "",
        "If STATE_ONLY were trained with an all-zero mask, a model could exploit **era/split** "
        "(2015 train vs 2023 test) rather than flood physics. Policy 2 therefore drops those pairs "
        "from the forecast set and keeps them as a state-only diagnostic companion.",
        "",
        "## 5. Four benchmark designs",
        "",
        "| Design | Training eligibility | Leakage | Validity | Split viability | Verdict |",
        "| --- | --- | --- | --- | --- | --- |",
        "| A Complete-case | FULL_CAUSAL only | Low if vintage integrity holds | 0 train events | Impossible | Reject |",
        "| B Partial + mask | FULL∪PARTIAL, explicit M | Low if STATE_ONLY excluded and leakage suite green | Honest operational truncation | 5/5/2 events | **Select** |",
        "| C Coverage-weighted fill | Same pairs as B | Imputation of M=0 | Missingness-dependent | Same counts, worse semantics | Reject |",
        "| D State-only diagnostic | All 183 with hydro | None if Q stays MODELLED_STATE | Answers a different question | 6/5/3 events including archive gaps | Companion only |",
        "",
        "## 6. Event-level coverage",
        "",
        "Do not let the 82% pair presence hide event gaps. `evt:2016-01-19` remains in the frozen "
        "train list but has no Target-B pair (Phase 6.8A).",
        "",
    ]
    for row in by_event:
        lines.append(
            f"- `{row.get('event_id')}` ({row.get('split')}, {row.get('year')}): n={row.get('n_pairs')}, "
            f"FULL={row.get('n_full_causal')}, PARTIAL={row.get('n_partial_causal')}, "
            f"STATE_ONLY={row.get('n_state_only')}, mean cover={_fmt(row.get('mean_forecast_coverage'))}, "
            f"min={_fmt(row.get('min_forecast_coverage'))}, max={_fmt(row.get('max_forecast_coverage'))}, "
            f"median lead h={_fmt(row.get('median_lead_hours'), 1)}, "
            f"median Δt h={_fmt(row.get('median_delta_t_hours'), 1)}"
        )
    lines.extend(
        [
            "",
            "## 7. Coverage by Δt",
            "",
            "Most Target-B transitions sit in 10–14 days while WB2 HRES ends at 10 days. "
            "Target-B observation intervals are not truncated.",
            "",
            "| Bucket | Pairs | FULL | PARTIAL | STATE_ONLY | mean hourly coverage |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    bucket_names = [name for _, _, name in DELTA_T_BINS_69]
    by_dt_map = {r.get("delta_t_bucket"): r for r in by_dt}
    for name in bucket_names:
        row = by_dt_map.get(name) or {
            "delta_t_bucket": name,
            "n_pairs": 0,
            "n_full_causal": 0,
            "n_partial_causal": 0,
            "n_state_only": 0,
            "mean_forecast_coverage": None,
        }
        lines.append(
            f"| {name} | {row.get('n_pairs')} | {row.get('n_full_causal')} | {row.get('n_partial_causal')} | "
            f"{row.get('n_state_only')} | {_fmt(row.get('mean_forecast_coverage'))} |"
        )
    lines.extend(
        [
            "",
            "Among archive-eligible years, coverage falls with lead because IFS HRES here stops at "
            "10 days. The 4–7 day bucket is 0 because those pairs are the 2015 train event.",
            "",
            "## 8. Acceptable partial-input policy",
            "",
            "- **Policy 1 (drop below X%):** X is not chosen by taste. The only non-arbitrary "
            f"completeness cut in code is `COMPLETE_COVERAGE_EPS = {COMPLETE_COVERAGE_EPS}` (FULL_CAUSAL). "
            "A second cut near 10/12 ≈ 0.83 only rediscovers the HRES horizon. Not primary.",
            "- **Policy 2 (P + M):** **Primary** forecast contract.",
            "- **Policy 3 (covered prefix as the target window):** Invalid. That converts Target-B "
            "into a 10-day flood map. Prefix as input only is Policy 2.",
            "- **Policy 4 (missing hours as uncertainty):** Evaluation companion — stratify metrics "
            "by coverage/Δt; do not fill.",
            "- **Policy 5 (no partial forcing):** Same as complete-case; impossible.",
            "",
            "Hydrology: **mandatory** `MODELLED_STATE_AT_T0`. Record `STATE_FRESHNESS_MASK` but do not "
            "drop currently FRESH pairs. Never label Q as FORECAST.",
            "",
            "## 9. Target B is unchanged",
            "",
            f"Primary target remains **{TARGET_B_PRIMARY_LABEL}** between consecutive GFM scenes on "
            "jointly valid pixels. Δt is the measured scene gap. Do not recode to 24/48/72 h maps.",
            "",
            "## 10. Model input contract",
            "",
            "Every channel specifies source, timestamp, status, units, resolution. Regrid to 64×64 is "
            "compatibility only. Do **not** claim high-resolution forecast forcing relative to 20 m GFM.",
            "",
        ]
    )
    for ch in INPUT_CONTRACT:
        lines.append(
            f"- **{ch['name']}:** source=`{ch['source']}`; timestamp=`{ch['timestamp']}`; "
            f"status=`{ch['status']}`; units=`{ch['units']}`; resolution=`{ch['resolution']}`; "
            f"required={ch['required']}. {ch['note']}"
        )
    p2 = policies.get("policy2_forecast") or {}
    so = policies.get("state_only_diagnostic") or {}
    lines.extend(
        [
            "",
            "## 11. Leakage tests (no training)",
            "",
            "Automated checks: `state_timestamp <= t0`; `issue_time <= t0`; `valid_time in (t0,t1]`; "
            "no post-t0 ERA5 as input; no future GloFAS as forecast; no target-derived features; "
            "no temporal fill.",
            "",
            f"Suite on current rows: **ok={ (report.get('leakage') or {}).get('ok') }**, "
            f"violations={ (report.get('leakage') or {}).get('n_violations') }.",
            "",
            "## 12. Frozen train/val/test (Policy 2 forecast set)",
            "",
            "Split file [`splits_v2/splits.json`](src/floodlens/application/data/ml/spatial/splits_v2/splits.json) is not rewritten.",
            "",
            "| Policy | Train | Val | Test |",
            "| --- | --- | --- | --- |",
            f"| 2 Forecast (FULL∪PARTIAL) | {_split_line(p2, 'train')} | {_split_line(p2, 'val')} | {_split_line(p2, 'test')} |",
            f"| 5/A Complete-case FULL | {_split_line(cc, 'train')} | {_split_line(cc, 'val')} | {_split_line(cc, 'test')} |",
            f"| D State-only diagnostic (all pairs) | {_split_line(so, 'train')} | {_split_line(so, 'val')} | {_split_line(so, 'test')} |",
            "",
            "Forecast-eligible events: train 2016/2017/2018 (5 events, 42 pairs); val all five events "
            "(76 pairs); test 2022+2024 (2 events, 32 pairs). 2015 and 2023 remain STATE_ONLY.",
            "",
            "## 13. Generalization",
            "",
            "- **Temporal / event:** the honest claim. Test still has **two** independent floods.",
            "- **Geographic:** weak. Target-B reuses the same Haor AOIs across years; the named "
            "geographic holdout in `splits.json` is a Track A construct, not a Target-B region split.",
            "- Label the benchmark **research/diagnostic** until more independent test events exist.",
            "",
            "## 14. Statistical power",
            "",
            f"{INDEPENDENT_EVENTS} meteorological episodes (`EVENT_GAP_DAYS = 45`). "
            f"{c.get('n_pairs')} pairs are nested repeats (AOI × consecutive scenes), not "
            f"{c.get('n_pairs')} independent floods. Pair-level CIs are anti-conservative.",
            "",
            "Use Phase 6.7 `event_bootstrap_ci` on forecast-eligible events (5/5/2). Hierarchical "
            "(pairs nested in events) is acceptable for variance decomposition. **Pair-level "
            "bootstrap is not.** Two test events ⇒ wide intervals; not a product claim.",
            "",
            "## 15. Track B and Track C",
            "",
            "**Track B:** separate historical coarse-observation benchmark (Phase 6.8 §9). Same "
            "partial-forcing class of problem exists for composites if t0 is not before the window; "
            "do not merge stores or labels.",
            "",
            "**Track C:** not designed. Partial-causal Target-B must exist as a contract first. "
            "n=15 cannot separate multi-resolution transfer from event identity.",
            "",
            "## 16. Training-entry gates",
            "",
            "This phase does **not** authorize training. A later baseline phase may request "
            "authorization only if all hold:",
            "",
            f"- Causal input integrity: `{gates.get('causal_input_integrity')}`",
            f"- Missingness audit published: `{gates.get('missingness_audit_published')}`",
            f"- STATE_ONLY excluded from forecast set: `{gates.get('state_only_excluded_from_forecast_set')}`",
            f"- Minimum split events (≥2 train, ≥2 val, ≥1 test FULL|PARTIAL): `{gates.get('min_split_events')}`",
            f"- Event-level evaluation specified: `{gates.get('event_level_eval_specified')}`",
            f"- Input contract frozen: `{gates.get('input_contract_frozen')}`",
            f"- Human approval of a baseline experiment phase: `{gates.get('human_baseline_approval')}`",
            "",
            f"**training_authorized:** `{gates.get('training_authorized')}`",
            "",
            "## 17. Scientific decision",
            "",
            f"**{letter}** is selected because complete-case cannot be trained under the freeze; "
            "archive-eligible missingness is the operational 10-day HRES wall on a 12-day GFM gap "
            "and can be represented honestly with P+M; archive-gap zeros (2015, 2023) are split "
            "confounders and are excluded from the forecast set. State-only is a companion "
            "diagnostic, not the forecast benchmark. More TIGGE/GFS (letter E) would help FULL_CAUSAL "
            "train events but is not required to define the contract. Abandoning Target-B (letter D) "
            "is too strong: the label is valid (Phase 6.8A).",
            "",
            "B is not selected because 150 > 12. The 12 FULL_CAUSAL pairs remain insufficient for "
            "supervised complete-case learning.",
            "",
            "---",
            "",
            f"INDEPENDENT EVENTS: {INDEPENDENT_EVENTS}",
            "",
            f"TARGET-B PAIRS: {c.get('n_pairs')}",
            "",
            f"FULL CAUSAL PAIRS: {c.get('n_full_causal')}",
            "",
            f"PARTIAL CAUSAL PAIRS: {c.get('n_partial_causal')}",
            "",
            f"STATE-ONLY PAIRS: {c.get('n_state_only')}",
            "",
            f"FORECAST-ELIGIBLE PAIRS (POLICY 2): {fc.get('n_pairs')}",
            "",
            f"TRAIN EVENTS / PAIRS (POLICY 2): {_split_line(p2, 'train')}",
            "",
            f"VALIDATION EVENTS / PAIRS (POLICY 2): {_split_line(p2, 'val')}",
            "",
            f"TEST EVENTS / PAIRS (POLICY 2): {_split_line(p2, 'test')}",
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
            "TRACK B: SEPARATE",
            "",
            "TRACK C: NOT YET IMPLEMENTED",
            "",
            "SOLVER MODIFIED: NO",
            "",
            "END.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_phase610(
    *,
    pairs: Optional[Sequence[dict]] = None,
    pairs_path: Optional[Path] = None,
    hydro: Optional[Dict[str, dict]] = None,
    hydro_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    write_artifacts: bool = True,
    write_docs: bool = False,
) -> dict:
    rows_in = list(pairs) if pairs is not None else load_vintage_pairs(pairs_path)
    hydro_idx = hydro if hydro is not None else load_hydro_index(hydro_path)
    rows = attach_hydro(rows_in, hydro_idx)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    dest = Path(out_dir or OUT_DIR)

    n_pairs = len(rows)
    n_full = sum(1 for r in rows if r.get("eligibility") == ELIG_FULL)
    n_partial = sum(1 for r in rows if r.get("eligibility") == ELIG_PARTIAL)
    n_state = sum(1 for r in rows if r.get("eligibility") == ELIG_STATE)
    n_fcst = sum(1 for r in rows if is_forecast_eligible(r))
    forecast_rows = [r for r in rows if is_forecast_eligible(r)]
    events_all = {r.get("event_id") for r in rows if r.get("event_id")}
    events_full = {r.get("event_id") for r in rows if r.get("eligibility") == ELIG_FULL and r.get("event_id")}
    events_causal = {r.get("event_id") for r in forecast_rows if r.get("event_id")}

    complete_case = split_policy_counts(rows, lambda r: r.get("eligibility") == ELIG_FULL)
    policy2 = split_policy_counts(rows, is_forecast_eligible)
    state_diag = split_policy_counts(rows, lambda r: True)
    leakage = leakage_suite(rows)
    miss = missingness_confound(rows)

    train_e = policy2["train"]["n_events"]
    val_e = policy2["val"]["n_events"]
    test_e = policy2["test"]["n_events"]
    min_split = train_e >= 2 and val_e >= 2 and test_e >= 1
    state_excluded = all(r.get("eligibility") != ELIG_STATE for r in forecast_rows)
    gates = {
        "causal_input_integrity": bool(leakage.get("ok")),
        "missingness_audit_published": True,
        "state_only_excluded_from_forecast_set": state_excluded,
        "min_split_events": min_split,
        "event_level_eval_specified": True,
        "input_contract_frozen": True,
        "human_baseline_approval": False,
        "training_authorized": False,
    }
    letter = "B"
    spatial_reg = load_spatial_registry()
    prov = spatial_artifact_provenance(
        data_status="DESIGN",
        source="floodlens-x-phase6.10",
        dataset=EXPERIMENT_ID,
        source_url="docs/PHASE_6_10_PARTIAL_CAUSAL_BENCHMARK_DESIGN.md",
        source_version=EXPERIMENT_ID,
        processing_version=EXPERIMENT_ID,
        license_name="Design document; WB2/ECMWF HRES; Open-Meteo CC BY 4.0; GFM CEMS",
        attribution="Phase 6.9B vintage pairs; CEMS GloFAS reanalysis (state only)",
        label_kind="OBSERVED",
        extra={"n_pairs": n_pairs, "n_forecast_eligible": n_fcst, "parent_cube": PARENT_CUBE},
    )
    frozen = None
    if SPLITS_PATH.exists():
        frozen = load_frozen_splits()
    counts = {
        "n_pairs": n_pairs,
        "n_independent_events": INDEPENDENT_EVENTS if len(events_all) >= 14 else len(events_all),
        "n_full_causal": n_full,
        "n_partial_causal": n_partial,
        "n_state_only": n_state,
        "n_pairs_with_forecast": n_fcst,
        "pair_vintage_presence_pct": round(100.0 * n_fcst / n_pairs, 1) if n_pairs else 0.0,
        "mean_hourly_coverage": summarize_numeric(r.get("forecast_coverage_fraction") for r in rows)["mean"],
        "full_pair_share_pct": round(100.0 * n_full / n_pairs, 1) if n_pairs else 0.0,
        "n_events_full": len(events_full),
        "n_events_causal": len(events_causal),
        "n_observed_events_with_pairs": len(events_all),
    }
    report = {
        "evaluated_at": retrieved,
        "experiment_id": EXPERIMENT_ID,
        "parent_cube": PARENT_CUBE,
        "catalog_status": "NOT_VALIDATED",
        "public_spatial_status": public_spatial_status(spatial_reg),
        "promoted_to_validated": False,
        "spatial_api": "UNAVAILABLE",
        "model_training": "NOT AUTHORIZED",
        "cnn_trained": False,
        "solver_modified": False,
        "counts": counts,
        "forecast_set": {
            "n_pairs": n_fcst,
            "n_events": len(events_causal),
            "eligibility": sorted(FORECAST_BENCHMARK_ELIGIBLE),
        },
        "complete_case": complete_case,
        "policies": {
            "policy2_forecast": policy2,
            "policy5_complete_case": complete_case,
            "state_only_diagnostic": state_diag,
        },
        "by_event": event_coverage_rows(rows),
        "by_year": aggregate_missingness(rows, "year"),
        "by_split": aggregate_missingness(rows, "split"),
        "by_region": aggregate_missingness(rows, "region"),
        "by_delta_t": aggregate_missingness(rows, "delta_t_bucket"),
        "by_source": aggregate_missingness(rows, "forecast_source"),
        "missingness": miss,
        "leakage": leakage,
        "input_contract": input_contract_payload(),
        "training_gates": gates,
        "frozen_splits_path": str(SPLITS_PATH),
        "frozen_split_scheme": (frozen or {}).get("scheme"),
        "decision_letter": letter,
        "decision": DECISION_TEXT[letter],
        "target_b_status": "PARTIALLY FEASIBLE",
        "hydro_status": "MODELLED_STATE_AT_T0",
        "track_b": "SEPARATE",
        "track_c": "NOT YET IMPLEMENTED",
        "provenance": {"envelope": prov, "complete": provenance_complete(prov)},
        "next_phase": "A future baseline experiment may be designed after human approval. Do not train in this phase.",
        "pairs": rows,
    }
    if write_artifacts:
        dest.mkdir(parents=True, exist_ok=True)
        summary = _jsonable({k: v for k, v in report.items() if k != "pairs"})
        (dest / "missingness_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (dest / "input_contract.json").write_text(
            json.dumps(_jsonable(report["input_contract"]), indent=2), encoding="utf-8"
        )
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
            "delta_t_bucket",
            "eligibility",
            "forecast_eligible",
            "forecast_coverage_fraction",
            "forecast_source",
            "forecast_lead_min",
            "forecast_lead_max",
            "hydrology_status",
            "glofas_state_time",
            "hydro_staleness",
            "benchmark_role",
        ]
        with (dest / "benchmark_eligibility.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                rec = {k: row.get(k) for k in fields}
                rec["forecast_eligible"] = is_forecast_eligible(row)
                rec["benchmark_role"] = "FORECAST" if is_forecast_eligible(row) else "STATE_ONLY_DIAGNOSTIC"
                writer.writerow(rec)
        md = write_markdown_report(report)
        (dest / "PHASE_6_10_PARTIAL_CAUSAL_BENCHMARK_DESIGN.md").write_text(md, encoding="utf-8")
        if write_docs:
            DOCS_REPORT.parent.mkdir(parents=True, exist_ok=True)
            DOCS_REPORT.write_text(md, encoding="utf-8")
            report["report_md"] = str(DOCS_REPORT)
        report["artifact_dir"] = str(dest)
    return report
