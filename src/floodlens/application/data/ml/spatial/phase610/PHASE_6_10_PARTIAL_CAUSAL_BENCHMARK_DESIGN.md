# Phase 6.10 — Partial-causal Target-B benchmark design

**Status:** DESIGN ONLY. Not a training run. Not a VALIDATED claim.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. Spatial API remains **UNAVAILABLE**.

**Solver:** `src/floodlens/numerical/**` was not modified.

**Experiment id:** `phase6.10-partial-causal-design-v1`

**Parent cube (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Decision:** **B** — PARTIAL-CAUSAL BENCHMARK WITH EXPLICIT MASKING

This phase does not train any model. Frozen event splits and GFM labels are unchanged.

---

## 1. Coverage definitions (do not collapse)

Never say “82% causal” without a denominator.

- **Pair-level vintage presence:** 150/183 = **82.0%** of Target-B pairs have at least one genuine in-horizon vintage hour (`FULL_CAUSAL` + `PARTIAL_CAUSAL`). This is Phase 6.9B `forecast_vintage_coverage_pct`.
- **Mean hourly coverage:** 0.612 averaged across all 183 pairs. `forecast_coverage_fraction` = hours in `(t0,t1]` inside a native vintage window / hours required. Not precipitation volume. Not 20 m cells.
- **FULL_CAUSAL pair share:** 12/183 = 6.6% (`forecast_coverage_fraction >= 0.99`).
- **Event-level FULL:** 2/15. **Event-level any vintage:** 12/15.
- **Not claimed:** 82% of rain volume, 82% of spatial cells, or 82% of independent floods.

A **PARTIAL_CAUSAL** pair means: GloFAS `MODELLED_STATE_AT_T0` is present; some vintage hours in `(t0,t1]` exist; some do not. Missing hours are unfilled. ERA5 in `(t0,t1]` remains `POST_T0_OBSERVATION`.

Typical 12-day pair under WB2 HRES 240 h + 6 h issue latency: uncovered tail ≈ 48–60 h of 288 h (**~17–21% of the observation interval**). That is a horizon fact, not a download failure.

## 2. Complete-case feasibility

Design A uses only `FULL_CAUSAL`. Under the frozen split:

- Train: **0 events / 0 pairs**
- Validation: **1 events / 2 pairs**
- Test: **1 events / 10 pairs**

Statistical failure (not “too small” as a slogan):

- **No independent training events.** Supervised complete-case learning has nothing to fit without using val/test or breaking the freeze.
- **No generalization estimate.** One validation event cannot support event-level model selection.
- **No meaningful test uncertainty.** One test event; a pair-level interval on pairs from one flood is pseudo-replication.

Complete-case Target-B training is not a valid experiment on the current archive.

## 3. Partial-case feasibility

Represent each eligible pair as native vintage precipitation **P** plus availability **M**, with M=1 only for hours inside a real window with `issue_time <= t0` and `valid_time in (t0,t1]`. Zero is not “no rain” unless M=1 and the field is 0. M=0 stores `None`, never a filled 0.0. Native 6 h mass is not interpolated into hourly intensities (`pm_from_windows` in `vintage_steps.py`).

This is feasible **if and only if**:

- `STATE_ONLY` pairs are excluded from the forecast-learning set (archive-era missingness).
- Remaining missingness is treated as HRES horizon truncation (10 d vs median Δt 12 d).
- Evaluation is event-level, stratified by coverage and Δt.
- The target stays **NEWLY_FLOODED** over the full measured `(t0,t1]`.

Coverage-weighted fill (Design C in the four-way comparison) still needs a numeric value for M=0 hours. That is silent imputation. Rejected as the primary contract.

## 4. Missingness (MNAR) audit

Missingness is not MCAR. Tabular association only — no logistic/GBDT flood model.

- Archive-gap years with mean coverage 0: **['2015', '2023']**.
- Zero-coverage pairs: 33; of those, 33 are 2015 or 2023.
- Split zero-coverage rates: `{'train': 0.16, 'val': 0.0, 'test': 0.43859649122807015}`.

Coverage=0 is year/archive (2015 train, 2023 test), hence split-correlated. Among 2016–2022/2024, missingness follows the 10-day HRES wall vs Δt. Exclude STATE_ONLY from the forecast set so the mask cannot encode era.

If STATE_ONLY were trained with an all-zero mask, a model could exploit **era/split** (2015 train vs 2023 test) rather than flood physics. Policy 2 therefore drops those pairs from the forecast set and keeps them as a state-only diagnostic companion.

## 5. Four benchmark designs

| Design | Training eligibility | Leakage | Validity | Split viability | Verdict |
| --- | --- | --- | --- | --- | --- |
| A Complete-case | FULL_CAUSAL only | Low if vintage integrity holds | 0 train events | Impossible | Reject |
| B Partial + mask | FULL∪PARTIAL, explicit M | Low if STATE_ONLY excluded and leakage suite green | Honest operational truncation | 5/5/2 events | **Select** |
| C Coverage-weighted fill | Same pairs as B | Imputation of M=0 | Missingness-dependent | Same counts, worse semantics | Reject |
| D State-only diagnostic | All 183 with hydro | None if Q stays MODELLED_STATE | Answers a different question | 6/5/3 events including archive gaps | Companion only |

## 6. Event-level coverage

Do not let the 82% pair presence hide event gaps. `evt:2016-01-19` remains in the frozen train list but has no Target-B pair (Phase 6.8A).

- `evt:2015-07-11` (train, 2015): n=8, FULL=0, PARTIAL=0, STATE_ONLY=8, mean cover=0.000, min=0.000, max=0.000, median lead h=n/a, median Δt h=576.0
- `evt:2016-06-30` (train, 2016): n=2, FULL=0, PARTIAL=2, STATE_ONLY=0, mean cover=0.397, min=0.397, max=0.397, median lead h=240.0, median Δt h=576.0
- `evt:2017-04-12` (train, 2017): n=21, FULL=0, PARTIAL=21, STATE_ONLY=0, mean cover=0.791, min=0.789, max=0.795, median lead h=240.0, median Δt h=288.0
- `evt:2017-07-31` (train, 2017): n=9, FULL=0, PARTIAL=9, STATE_ONLY=0, mean cover=0.793, min=0.792, max=0.795, median lead h=240.0, median Δt h=288.0
- `evt:2018-01-13` (train, 2018): n=5, FULL=0, PARTIAL=5, STATE_ONLY=0, mean cover=0.792, min=0.792, max=0.792, median lead h=240.0, median Δt h=288.0
- `evt:2018-06-06` (train, 2018): n=5, FULL=0, PARTIAL=5, STATE_ONLY=0, mean cover=0.789, min=0.789, max=0.789, median lead h=240.0, median Δt h=288.0
- `evt:2019-01-10` (val, 2019): n=9, FULL=0, PARTIAL=9, STATE_ONLY=0, mean cover=0.793, min=0.792, max=0.795, median lead h=240.0, median Δt h=288.0
- `evt:2019-06-15` (val, 2019): n=10, FULL=2, PARTIAL=8, STATE_ONLY=0, mean cover=0.870, min=0.792, max=1.000, median lead h=240.0, median Δt h=288.0
- `evt:2020-01-15` (val, 2020): n=7, FULL=0, PARTIAL=7, STATE_ONLY=0, mean cover=0.793, min=0.792, max=0.795, median lead h=240.0, median Δt h=288.0
- `evt:2020-06-07` (val, 2020): n=18, FULL=0, PARTIAL=18, STATE_ONLY=0, mean cover=0.522, min=0.198, max=0.792, median lead h=240.0, median Δt h=504.0
- `evt:2021-06-02` (val, 2021): n=32, FULL=0, PARTIAL=32, STATE_ONLY=0, mean cover=0.790, min=0.789, max=0.792, median lead h=240.0, median Δt h=288.0
- `evt:2022-05-16` (test, 2022): n=10, FULL=0, PARTIAL=10, STATE_ONLY=0, mean cover=0.526, min=0.264, max=0.789, median lead h=240.0, median Δt h=576.0
- `evt:2023-06-16` (test, 2023): n=25, FULL=0, PARTIAL=0, STATE_ONLY=25, mean cover=0.000, min=0.000, max=0.000, median lead h=n/a, median Δt h=288.0
- `evt:2024-06-22` (test, 2024): n=22, FULL=10, PARTIAL=12, STATE_ONLY=0, mean cover=0.832, min=0.199, max=1.000, median lead h=240.0, median Δt h=288.0

## 7. Coverage by Δt

Most Target-B transitions sit in 10–14 days while WB2 HRES ends at 10 days. Target-B observation intervals are not truncated.

| Bucket | Pairs | FULL | PARTIAL | STATE_ONLY | mean hourly coverage |
| --- | --- | --- | --- | --- | --- |
| 0-2 days | 0 | 0 | 0 | 0 | n/a |
| 2-4 days | 2 | 2 | 0 | 0 | 1.000 |
| 4-7 days | 3 | 0 | 0 | 3 | 0.000 |
| 7-10 days | 2 | 0 | 2 | 0 | 0.971 |
| 10-14 days | 151 | 10 | 116 | 25 | 0.674 |
| 14-21 days | 2 | 0 | 2 | 0 | 0.527 |
| 21+ days | 23 | 0 | 18 | 5 | 0.231 |

Among archive-eligible years, coverage falls with lead because IFS HRES here stops at 10 days. The 4–7 day bucket is 0 because those pairs are the 2015 train event.

## 8. Acceptable partial-input policy

- **Policy 1 (drop below X%):** X is not chosen by taste. The only non-arbitrary completeness cut in code is `COMPLETE_COVERAGE_EPS = 0.99` (FULL_CAUSAL). A second cut near 10/12 ≈ 0.83 only rediscovers the HRES horizon. Not primary.
- **Policy 2 (P + M):** **Primary** forecast contract.
- **Policy 3 (covered prefix as the target window):** Invalid. That converts Target-B into a 10-day flood map. Prefix as input only is Policy 2.
- **Policy 4 (missing hours as uncertainty):** Evaluation companion — stratify metrics by coverage/Δt; do not fill.
- **Policy 5 (no partial forcing):** Same as complete-case; impossible.

Hydrology: **mandatory** `MODELLED_STATE_AT_T0`. Record `STATE_FRESHNESS_MASK` but do not drop currently FRESH pairs. Never label Q as FORECAST.

## 9. Target B is unchanged

Primary target remains **NEWLY_FLOODED** between consecutive GFM scenes on jointly valid pixels. Δt is the measured scene gap. Do not recode to 24/48/72 h maps.

## 10. Model input contract

Every channel specifies source, timestamp, status, units, resolution. Regrid to 64×64 is compatibility only. Do **not** claim high-resolution forecast forcing relative to 20 m GFM.

- **STATE_AT_T0:** source=`GloFAS reanalysis Q (Open-Meteo Flood API, forecast_days=0)`; timestamp=`end of last complete Q calendar day before t0`; status=`MODELLED_STATE`; units=`m3 s-1`; resolution=`daily 0.05deg proxy cell`; required=True. Not forecast forcing. Freshness recorded; currently FRESH on 183/183.
- **FORECAST_FORCING:** source=`WB2 IFS HRES total_precipitation_6hr (2016–2022); Open-Meteo Single Runs IFS (2024)`; timestamp=`issue_time <= t0; valid_time in (t0,t1]`; status=`FORECAST_VINTAGE`; units=`mm (native accumulation window)`; resolution=`1.5° (240×121 equiangular with poles)`; required=True. Native steps only. No ERA5 in (t0,t1]. No interpolation of missing leads.
- **FORCING_MASK:** source=`derived from vintage windows`; timestamp=`same as FORECAST_FORCING valid_time`; status=`MASK`; units=`1 = genuine vintage hour; 0 = unavailable`; resolution=`hourly coverage of native windows; not 20 m`; required=True. M=0 precipitation is None, never 0.0 fill.
- **STATIC_SPATIAL_FEATURES:** source=`existing GFM working-grid statics (parent cube)`; timestamp=`time-invariant`; status=`STATIC`; units=`channel-specific`; resolution=`GFM working grid 64x64; native DEM/HAND as recorded in v2.1`; required=True. Unchanged. Not a substitute for vintage precipitation.
- **STATE_FRESHNESS_MASK:** source=`GloFAS staleness class (FRESH/STALE/VERY_STALE)`; timestamp=`glofas_state_time`; status=`OPTIONAL`; units=`categorical`; resolution=`pair scalar`; required=False. Currently constant FRESH; keep for future stale days. Do not drop pairs today.
- **FORECAST_LEAD_FEATURES:** source=`vintage issue/valid timestamps`; timestamp=`issue_time`; status=`OPTIONAL`; units=`hours`; resolution=`pair scalar (lead min/max)`; required=False. Already on Phase 6.9B pair rows.

## 11. Leakage tests (no training)

Automated checks: `state_timestamp <= t0`; `issue_time <= t0`; `valid_time in (t0,t1]`; no post-t0 ERA5 as input; no future GloFAS as forecast; no target-derived features; no temporal fill.

Suite on current rows: **ok=True**, violations=0.

## 12. Frozen train/val/test (Policy 2 forecast set)

Split file [`splits_v2/splits.json`](src/floodlens/application/data/ml/spatial/splits_v2/splits.json) is not rewritten.

| Policy | Train | Val | Test |
| --- | --- | --- | --- |
| 2 Forecast (FULL∪PARTIAL) | 5 events / 42 pairs | 5 events / 76 pairs | 2 events / 32 pairs |
| 5/A Complete-case FULL | 0 events / 0 pairs | 1 events / 2 pairs | 1 events / 10 pairs |
| D State-only diagnostic (all pairs) | 6 events / 50 pairs | 5 events / 76 pairs | 3 events / 57 pairs |

Forecast-eligible events: train 2016/2017/2018 (5 events, 42 pairs); val all five events (76 pairs); test 2022+2024 (2 events, 32 pairs). 2015 and 2023 remain STATE_ONLY.

## 13. Generalization

- **Temporal / event:** the honest claim. Test still has **two** independent floods.
- **Geographic:** weak. Target-B reuses the same Haor AOIs across years; the named geographic holdout in `splits.json` is a Track A construct, not a Target-B region split.
- Label the benchmark **research/diagnostic** until more independent test events exist.

## 14. Statistical power

15 meteorological episodes (`EVENT_GAP_DAYS = 45`). 183 pairs are nested repeats (AOI × consecutive scenes), not 183 independent floods. Pair-level CIs are anti-conservative.

Use Phase 6.7 `event_bootstrap_ci` on forecast-eligible events (5/5/2). Hierarchical (pairs nested in events) is acceptable for variance decomposition. **Pair-level bootstrap is not.** Two test events ⇒ wide intervals; not a product claim.

## 15. Track B and Track C

**Track B:** separate historical coarse-observation benchmark (Phase 6.8 §9). Same partial-forcing class of problem exists for composites if t0 is not before the window; do not merge stores or labels.

**Track C:** not designed. Partial-causal Target-B must exist as a contract first. n=15 cannot separate multi-resolution transfer from event identity.

## 16. Training-entry gates

This phase does **not** authorize training. A later baseline phase may request authorization only if all hold:

- Causal input integrity: `True`
- Missingness audit published: `True`
- STATE_ONLY excluded from forecast set: `True`
- Minimum split events (≥2 train, ≥2 val, ≥1 test FULL|PARTIAL): `True`
- Event-level evaluation specified: `True`
- Input contract frozen: `True`
- Human approval of a baseline experiment phase: `False`

**training_authorized:** `False`

## 17. Scientific decision

**B** is selected because complete-case cannot be trained under the freeze; archive-eligible missingness is the operational 10-day HRES wall on a 12-day GFM gap and can be represented honestly with P+M; archive-gap zeros (2015, 2023) are split confounders and are excluded from the forecast set. State-only is a companion diagnostic, not the forecast benchmark. More TIGGE/GFS (letter E) would help FULL_CAUSAL train events but is not required to define the contract. Abandoning Target-B (letter D) is too strong: the label is valid (Phase 6.8A).

B is not selected because 150 > 12. The 12 FULL_CAUSAL pairs remain insufficient for supervised complete-case learning.

---

INDEPENDENT EVENTS: 15

TARGET-B PAIRS: 183

FULL CAUSAL PAIRS: 12

PARTIAL CAUSAL PAIRS: 138

STATE-ONLY PAIRS: 33

FORECAST-ELIGIBLE PAIRS (POLICY 2): 150

TRAIN EVENTS / PAIRS (POLICY 2): 5 events / 42 pairs

VALIDATION EVENTS / PAIRS (POLICY 2): 5 events / 76 pairs

TEST EVENTS / PAIRS (POLICY 2): 2 events / 32 pairs

HYDROLOGY: MODELLED_STATE_AT_T0

TARGET B: PARTIALLY FEASIBLE

MODEL TRAINING: NOT AUTHORIZED

SPATIAL AI: NOT_VALIDATED

SPATIAL API: UNAVAILABLE

TRACK B: SEPARATE

TRACK C: NOT YET IMPLEMENTED

SOLVER MODIFIED: NO

END.
