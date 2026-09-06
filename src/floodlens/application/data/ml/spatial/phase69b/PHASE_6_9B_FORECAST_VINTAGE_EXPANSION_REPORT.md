# Phase 6.9B — Historical forecast-vintage expansion

**Status:** FORECAST-VINTAGE ACQUISITION. Not a training run. Not a VALIDATED claim.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. Spatial API remains **UNAVAILABLE**.

**Solver:** `src/floodlens/numerical/**` was not modified.

**Experiment id:** `phase6.9b-forecast-vintage-v1`

**Parent cube (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Decision:** **B** — PARTIAL CAUSAL DATASET WITH ADEQUATE TRAIN/VAL/TEST COVERAGE

This phase does not train any model.

---

## 1. Sources investigated

| Source | Vintage? | Years | Horizon | Notes |
| --- | --- | --- | --- | --- |
| TIGGE ECMWF (ECDS) | Yes | 2006–present | ~15 d | Credentials required; not acquired |
| WeatherBench 2 IFS HRES | Yes (init time) | 2016–2022 00/12 | 10 d / 6 h | Public GCS zarr; acquired |
| Open-Meteo Single Runs IFS | Yes | 2024-03-14+ | ~16 d hourly | 6.9A cache reused |
| Open-Meteo Historical Forecast | No (blended) | ~2021+ | short | Rejected |
| GEFSv12 reforecast | Frozen 2017 model | 2000–2019 | 16 d | Rejected as operational vintage |
| NCAR RDA GFS d084001 | Yes | 2015–present | 16 d | Full GRIB / SSL not used; not acquired |
| ERA5-Land lattice | Reanalysis | 2016–2024 | n/a | Lookback only; in-horizon forbidden |

## 2. Sources accessible

- WeatherBench 2 HRES `2016-2022-0012-240x121` via HTTPS (no ECDS login).
- Open-Meteo Single Runs IFS HRES for 2024 (existing 6.9A cache).
- GloFAS reanalysis Q reindexed at t0 (Phase 6.9A), **MODELLED_STATE**, not forecast.

## 3. Sources rejected

- TIGGE/ECDS: no CDS credentials after WEB-API decommission (27 May 2026).
- ERA5 in `(t0,t1]`: POST_T0_OBSERVATION.
- Blended Historical Forecast API.
- GEFSv12 reforecasts (not the operational system of the day).
- Cube GloFAS Q at `valid_at−192 h`.

## 4. Acquisition size

- WB2 unique initialisations requested: 38
- WB2 initialisations ok: 38
- 2024 Single Runs cache reused (not re-downloaded unless missing).
- Variables: `total_precipitation_6hr` only (WB2); hourly precipitation (2024 IFS).

## 5. Years covered

WB2: 2016–2022. Single Runs: 2024. **2015 and 2023 remain without vintage NWP.**

## 6. Forecast cycles covered

IFS HRES 00/12 UTC with 6 h issue latency (`issue_time + 6 h <= t0`). 06/18 not in WB2.

## 7. Forecast resolution

- Native: **1.5° (240×121 equiangular with poles)** (WB2). 2024 IFS ~9 km point sample.
- Target: nearest GloFAS proxy point; GFM working grid 64×64 is not the NWP grid
- Regridding: `nearest-neighbor point sample at proxy lat/lon; no 20 m downscale`
- Do **not** claim high-resolution forecast forcing relative to 20 m GFM labels.

## 8. Forecast temporal resolution

- WB2: 6-hourly accumulation, leads 6…240 h. Hourly slots are covered only when they fall in a native 6 h window with `valid_time ∈ (t0,t1]`. Intensities are not interpolated.
- 2024 Single Runs: hourly (Open-Meteo interpolation of IFS steps), as in 6.9A.

## 9. Forecast-variable coverage

Total precipitation only. Derived accumulation = sum of genuine in-horizon native steps. No extra variables.

## 10. Pair coverage

| Eligibility | Pairs |
| --- | --- |
| FULL_CAUSAL | 12 |
| PARTIAL_CAUSAL | 138 |
| STATE_ONLY | 33 |
| OBSERVATIONAL_ONLY | 0 |
| UNAVAILABLE | 0 |

Forecast-vintage pair fraction: **82.0%**.

## 11. Event coverage

Events with ≥1 FULL_CAUSAL pair: **2**. Events with multiple FULL_CAUSAL pairs: **2**. Events with ≥1 FULL or PARTIAL pair: **12**.

- `evt:2015-07-11`: n=8, FULL=0, PARTIAL=0, STATE_ONLY=8, mean cover=0.000
- `evt:2016-06-30`: n=2, FULL=0, PARTIAL=2, STATE_ONLY=0, mean cover=0.397
- `evt:2017-04-12`: n=21, FULL=0, PARTIAL=21, STATE_ONLY=0, mean cover=0.791
- `evt:2017-07-31`: n=9, FULL=0, PARTIAL=9, STATE_ONLY=0, mean cover=0.793
- `evt:2018-01-13`: n=5, FULL=0, PARTIAL=5, STATE_ONLY=0, mean cover=0.792
- `evt:2018-06-06`: n=5, FULL=0, PARTIAL=5, STATE_ONLY=0, mean cover=0.789
- `evt:2019-01-10`: n=9, FULL=0, PARTIAL=9, STATE_ONLY=0, mean cover=0.793
- `evt:2019-06-15`: n=10, FULL=2, PARTIAL=8, STATE_ONLY=0, mean cover=0.870
- `evt:2020-01-15`: n=7, FULL=0, PARTIAL=7, STATE_ONLY=0, mean cover=0.793
- `evt:2020-06-07`: n=18, FULL=0, PARTIAL=18, STATE_ONLY=0, mean cover=0.522
- `evt:2021-06-02`: n=32, FULL=0, PARTIAL=32, STATE_ONLY=0, mean cover=0.790
- `evt:2022-05-16`: n=10, FULL=0, PARTIAL=10, STATE_ONLY=0, mean cover=0.526
- `evt:2023-06-16`: n=25, FULL=0, PARTIAL=0, STATE_ONLY=25, mean cover=0.000
- `evt:2024-06-22`: n=22, FULL=10, PARTIAL=12, STATE_ONLY=0, mean cover=0.832

## 12. Train/val/test coverage

Frozen event split is unchanged.

| Split | Events FULL | Events PARTIAL/causal | FULL pairs | PARTIAL pairs |
| --- | --- | --- | --- | --- |
| train | 0 | 5 | 0 | 42 |
| val | 1 | 5 | 2 | 74 |
| test | 1 | 2 | 10 | 22 |

Causal forecast forcing (FULL or PARTIAL) now spans multiple frozen train, validation, and test events. Train still has no FULL_CAUSAL pairs because WB2 HRES is 10 days vs median Δt = 12 days.

## 13. Delta-t coverage

Median Δt remains **12.00 days** (288 h). WB2 max lead is 10 days, so most 12-day pairs are PARTIAL_CAUSAL, not FULL.

| Bucket | Pairs | FULL | PARTIAL | mean coverage |
| --- | --- | --- | --- | --- |
| 0-2 days | 0 | 0 | 0 | n/a |
| 2-4 days | 2 | 2 | 0 | 1.000 |
| 4-7 days | 3 | 0 | 0 | 0.000 |
| 7-10 days | 2 | 0 | 2 | 0.971 |
| 10-14 days | 151 | 10 | 116 | 0.674 |
| 14-21 days | 2 | 0 | 2 | 0.527 |
| 21+ days | 23 | 0 | 18 | 0.231 |

Coverage among archive-eligible years degrades with lead time because IFS HRES here stops at 10 days. The 4–7 day bucket is 0.000 because those three pairs are the 2015 train event (outside WB2), not because short leads fail. Target-B observations were not truncated.

## 14. Provenance

Envelope complete: **True**. Each forecast field stores source, provider, model, cycle, issue_time, valid_time, retrieval_time, source_version, license, attribution, native_resolution, processing_version.

## 15. Licensing

- WeatherBench 2 public GCS + ECMWF IFS HRES attribution (Rasp et al.).
- Open-Meteo Single Runs: CC BY 4.0; ECMWF open-data terms.
- GloFAS reanalysis Q: CC BY 4.0; CEMS-FLOODS (MODELLED_STATE, not forecast).
- TIGGE: not acquired (CC BY 4.0 ECMWF, ECDS account).
- GFM labels: CEMS STAC (unchanged).

## 16. Remaining gaps

2015 (train) and 2023 (test) have no WB2 HRES. TIGGE (~15 d, 2015–2024) is still the covering archive but is not accessible without ECDS credentials. GFS operational GRIB was not extracted. Most 12-day pairs are PARTIAL under a 10-day HRES horizon. Train FULL_CAUSAL remains 0. Do not use ERA5 in `(t0,t1]`.

---

INDEPENDENT EVENTS: 15

TARGET-B PAIRS: 183

FULL CAUSAL PAIRS: 12

PARTIAL CAUSAL PAIRS: 138

STATE-ONLY PAIRS: 33

TRAIN EVENTS WITH FULL CAUSAL PAIRS: 0

VALIDATION EVENTS WITH FULL CAUSAL PAIRS: 1

TEST EVENTS WITH FULL CAUSAL PAIRS: 1

FORECAST-VINTAGE COVERAGE: 82.0%

MEDIAN DELTA-T: 288 h

HYDROLOGY: MODELLED_STATE_AT_T0

TARGET B: PARTIALLY FEASIBLE — CAUSAL FORCING SPANS TRAIN/VAL/TEST; FULL_CAUSAL STILL SPARSE

MODEL TRAINING: NOT AUTHORIZED

SPATIAL AI: NOT_VALIDATED

SPATIAL API: UNAVAILABLE

SOLVER MODIFIED: NO

END.
