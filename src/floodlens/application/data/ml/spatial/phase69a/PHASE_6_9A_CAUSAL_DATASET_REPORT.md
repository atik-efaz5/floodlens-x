# Phase 6.9A — Causal Target-B dataset construction

**Status:** CAUSAL DATASET CONSTRUCTION. Not a training run. Not a VALIDATED claim.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**Solver:** `src/floodlens/numerical/**` was not modified. No solver–hydrology coupling.

**Experiment id:** `phase6.9a-causal-targetb-v1`

**Parent cube (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Decision:** **C** — CAUSAL DATASET STILL TOO SMALL — ACQUIRE BETTER FORECAST INPUTS

This phase does not train any model.

---

## 1. Objective

Construct the largest scientifically valid **causal Target-B input dataset** from currently accessible public sources. Target-B labels stay observational GFM transitions. STATE_AT_T0 and FORECAST_FORCING are not merged.

## 2. Current Phase 6.9 problem

Phase 6.9 found 183 pairs / 15 events, median Δt = 12 days, acquired forecast-vintage precipitation = 0, and cube GloFAS Q aligned to `valid_at − 192 h` (178/183 POST_T0 if used as t0 state). ERA5 in `(t0, t1]` remains POST_T0_OBSERVATION.

## 3. GloFAS reindexing methodology

Daily GloFAS reanalysis Q at the AOI proxy cell is taken from `discharge_2015_2024.json` (Open-Meteo Flood API, `forecast_days=0`).

- `t0 = earlier.valid_at`
- last complete Q calendar day = calendar day before t0 (`last_complete_q_day`)
- `glofas_state_time` = end of that day (00:00 UTC the following date)
- require `glofas_state_time <= t0`
- lookback remains Q[t0−7d … t0−1d]; t0-day Q is never a t0 feature
- kind = MODELLED; status = MODELLED_STATE; **not FORECAST**
- cube 192 h alignment is recorded only as a contrast, never used as Target-B state

Staleness uses lag from `glofas_state_time` to t0, matching daily-product completeness:

| Class | Lag |
| --- | --- |
| FRESH | ≤ 24 h |
| STALE | 24–72 h |
| VERY_STALE | > 72 h |

A noon t0 with yesterday's complete daily Q is FRESH (~12 h), not STALE. Walk-back of missing days is recorded and not filled with zeros.

## 4. Hydrological-state coverage

| Quantity | Pairs |
| --- | --- |
| MODELLED_STATE at t0 | 183 |
| UNAVAILABLE | 0 |
| FRESH | 183 |
| STALE | 0 |
| VERY_STALE | 0 |
| Mean lag (h) | 14.41 |
| Cube 192 h still POST_T0 (contrast only) | 178 |

River level, soil moisture, and GloFAS **forecast** Q remain UNAVAILABLE.

## 5. Forecast-vintage sources investigated

| Product | Vintage? | Used in 6.9A |
| --- | --- | --- |
| ERA5-Land lattice | No | Lookback only; in-horizon = POST_T0_OBSERVATION |
| Open-Meteo Historical Forecast | No (blended) | Not used |
| Open-Meteo Previous Runs | Partial, 1–7 d, 2024+ | Not used (lead cap) |
| Open-Meteo Single Runs IFS HRES | Yes, from 2024-03-14, ~10 d | Smallest public acquire |
| TIGGE ECMWF precip | Yes, 2006–present, ~15 d | Planned; not downloaded |
| NOAA GEFSv12 reforecast | Frozen 2017 model | Not operational vintage |
| GloFAS forecast Q (CDS) | Yes, 30 d | Not acquired |

Issue latency of 6 h is applied so a 12 UTC IFS run is not treated as available at 12:05 t0. Open-Meteo IFS HRES 06/18 UTC cycles returned empty in this archive; acquisition uses 00/12 UTC only.

## 6. Forecast-vintage precipitation coverage

| Quantity | Value |
| --- | --- |
| Pairs with any FORECAST_VINTAGE hours | 22 |
| Mean acquired coverage fraction | 0.100 |
| FULL_CAUSAL pairs | 10 |
| PARTIAL_CAUSAL pairs | 12 |
| IFS HRES documented lead | 240 h (10 days) |
| TIGGE acquired | False |

Open-Meteo IFS HRES 00 UTC runs with `forecast_days=16` returned 16-day hourly series (the product table lists 10 days; we use the measured timestamps, without filling). That is enough for some 2024 12-day pairs to be FULL_CAUSAL. TIGGE (~15 d) remains the covering archive for 2015–2023 and is not acquired.

## 7. Issue-time integrity

- `issue_time <= t0`: **PASS**
- `glofas_state_time <= t0`: **PASS**
- ERA5 in-horizon as forecast input: **PASS** (forbidden)

Records violating issue/valid windows are rejected, not filled.

## 8. Target-B delta_t distribution

| Statistic | Days |
| --- | --- |
| min | 3.51 |
| median | 12.00 |
| mean | 14.38 |
| max | 48.00 |

| Bucket | Pairs |
| --- | --- |
| 0-2 days | 0 |
| 2-4 days | 2 |
| 4-7 days | 3 |
| 7-10 days | 2 |
| 10-14 days | 151 |
| 14-21 days | 2 |
| 21+ days | 23 |

Pairs with Δt ≤ 7 d: **5**. Most pairs remain beyond deterministic NWP (~7 d). 2015–2023 pairs have no vintage NWP in this cube.

## 9. Causal pair coverage

| Eligibility | Pairs |
| --- | --- |
| FULL_CAUSAL | 10 |
| PARTIAL_CAUSAL | 12 |
| STATE_ONLY | 161 |
| OBSERVATIONAL_ONLY | 0 |
| UNAVAILABLE | 0 |

## 10. Coverage by event

Ten pairs from one flood remain **one** event. Official Gate B is still **FAIL** (15 < 20).

- `evt:2015-07-11`: n=8, FULL=0, PARTIAL=0, STATE_ONLY=8
- `evt:2016-06-30`: n=2, FULL=0, PARTIAL=0, STATE_ONLY=2
- `evt:2017-04-12`: n=21, FULL=0, PARTIAL=0, STATE_ONLY=21
- `evt:2017-07-31`: n=9, FULL=0, PARTIAL=0, STATE_ONLY=9
- `evt:2018-01-13`: n=5, FULL=0, PARTIAL=0, STATE_ONLY=5
- `evt:2018-06-06`: n=5, FULL=0, PARTIAL=0, STATE_ONLY=5
- `evt:2019-01-10`: n=9, FULL=0, PARTIAL=0, STATE_ONLY=9
- `evt:2019-06-15`: n=10, FULL=0, PARTIAL=0, STATE_ONLY=10
- `evt:2020-01-15`: n=7, FULL=0, PARTIAL=0, STATE_ONLY=7
- `evt:2020-06-07`: n=18, FULL=0, PARTIAL=0, STATE_ONLY=18
- `evt:2021-06-02`: n=32, FULL=0, PARTIAL=0, STATE_ONLY=32
- `evt:2022-05-16`: n=10, FULL=0, PARTIAL=0, STATE_ONLY=10
- `evt:2023-06-16`: n=25, FULL=0, PARTIAL=0, STATE_ONLY=25
- `evt:2024-06-22`: n=22, FULL=10, PARTIAL=12, STATE_ONLY=0

Events with ≥1 FULL_CAUSAL pair: **1**.
Events with multiple FULL_CAUSAL pairs: **1**.
Events with zero causal forecast (FULL+PARTIAL): **13**.

## 11. Coverage by year

- 2015: n=8, FULL=0, PARTIAL=0, STATE_ONLY=8
- 2016: n=2, FULL=0, PARTIAL=0, STATE_ONLY=2
- 2017: n=30, FULL=0, PARTIAL=0, STATE_ONLY=30
- 2018: n=10, FULL=0, PARTIAL=0, STATE_ONLY=10
- 2019: n=19, FULL=0, PARTIAL=0, STATE_ONLY=19
- 2020: n=25, FULL=0, PARTIAL=0, STATE_ONLY=25
- 2021: n=32, FULL=0, PARTIAL=0, STATE_ONLY=32
- 2022: n=10, FULL=0, PARTIAL=0, STATE_ONLY=10
- 2023: n=25, FULL=0, PARTIAL=0, STATE_ONLY=25
- 2024: n=22, FULL=10, PARTIAL=12, STATE_ONLY=0

## 12. Coverage by region

- `dhaka_ne`: n=28, FULL=2, PARTIAL=2
- `dhaka_nw`: n=28, FULL=2, PARTIAL=2
- `dhaka_se`: n=18, FULL=0, PARTIAL=1
- `dhaka_sw`: n=20, FULL=0, PARTIAL=1
- `kishoreganj`: n=29, FULL=2, PARTIAL=2
- `netrokona`: n=30, FULL=2, PARTIAL=2
- `sunamganj`: n=30, FULL=2, PARTIAL=2

## 13. Coverage by train/val/test

Frozen event-level split is unchanged.

| Split | Events with FULL | Events with PARTIAL | FULL pairs | PARTIAL pairs |
| --- | --- | --- | --- | --- |
| train | 0 | 0 | 0 | 0 |
| val | 0 | 0 | 0 | 0 |
| test | 1 | 1 | 10 | 12 |

Train and validation have **zero FULL_CAUSAL events**. A frozen-split baseline is not justified. Any 2024 Single Runs coverage sits in test only and does not create a causal train/val/test dataset.

## 14. Data-quality categories

Per forcing interval: FORECAST_VINTAGE, MODELLED_STATE, OBSERVED_LOOKBACK, POST_T0_OBSERVATION, UNAVAILABLE, UNKNOWN. These are not collapsed.

## 15. Provenance audit

Envelope complete: **True**. Each hydro/forecast feature stores source, source_version, issue_time, valid_time, retrieval_time, status, units, resolution, processing_version.

## 16. Licensing/access constraints

- ERA5-Land / Open-Meteo: CC BY 4.0.
- GloFAS reanalysis via Open-Meteo: CC BY 4.0; CEMS-FLOODS attribution.
- Open-Meteo Single Runs IFS: CC BY 4.0; ECMWF open-data terms.
- TIGGE ECMWF: CC BY 4.0; ECDS account required — **not acquired**.
- GFM labels: CEMS proprietary STAC (unchanged).

## 17. Remaining gaps

Forecast-vintage precipitation is missing for 2015–2023 (TIGGE not acquired). IFS HRES Single Runs cover only the 2024 test event (00/12 UTC; 06/18 empty in this archive). GloFAS forecast Q, river level, and soil moisture remain UNAVAILABLE. Do not substitute ERA5 in `(t0,t1]`.

## 18. Whether a causal baseline dataset can now be constructed

A causal **state** dataset (GFM + reindexed Q + pre-t0 ERA5) is constructible for almost all pairs. A causal **forecast** baseline with frozen train/val/test is not: FULL_CAUSAL coverage is too small and does not span the frozen splits. Do not train.

---

INDEPENDENT EVENTS: 15

TARGET-B PAIRS: 183

FULL CAUSAL PAIRS: 10

PARTIAL CAUSAL PAIRS: 12

STATE-ONLY PAIRS: 161

POST-T0 / OBSERVATIONAL-ONLY PAIRS: 0

FORECAST-VINTAGE COVERAGE: 12.0%

MEDIAN DELTA-T: 288 h

EVENTS WITH FULL CAUSAL COVERAGE: 1

TRAIN EVENTS WITH FULL CAUSAL PAIRS: 0

VALIDATION EVENTS WITH FULL CAUSAL PAIRS: 0

TEST EVENTS WITH FULL CAUSAL PAIRS: 1

GLOFAS STATE STATUS: REINDEXED MODELLED_STATE AT T0

TARGET B: PARTIALLY FEASIBLE — STATE CONSTRUCTIBLE, FORECAST BASELINE NOT AUTHORIZED

MODEL TRAINING: NOT AUTHORIZED

SPATIAL AI: NOT_VALIDATED

SPATIAL API: UNAVAILABLE

SOLVER MODIFIED: NO

END.
