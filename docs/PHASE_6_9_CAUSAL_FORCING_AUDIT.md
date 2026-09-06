# Phase 6.9 — Causal forecast forcing audit (Target B)

**Status:** CAUSAL FORCING AUDIT. Not a training run. Not a VALIDATED claim.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**Solver:** `src/floodlens/numerical/**` was not modified. No solver–hydrology coupling.

**Experiment id:** `phase6.9-causal-forcing-audit-v1`

**Decision:** **F** — COMBINATION OF C + E

This phase does not train any model and does not download TIGGE or GloFAS-forecast cubes.

---

## 1. Objective

Phase 6.8A found Target B **feasible as a label** (183 consecutive GFM pairs, 15 events) but **forcing insufficient**: rain in `(t0, t1]` is POST-T0 OBSERVATION. This phase asks whether those transitions can be associated with **genuinely causal forecast inputs available at t0**.

## 2. Definition of causal-at-t0

A feature is **FORECAST-AVAILABLE** at t0 only if all of the following hold:

- it does not depend on observations after t0,
- its product/version existed or is retrospectively reproducible as available at t0,
- issue_time, valid window, and lead are known,
- it is not an observed/reanalysis future value.

| Code | Category | Meaning |
| --- | --- | --- |
| A | OBSERVED-AVAILABLE | Information at/before t0 (incl. lagged GFM; reanalysis lookback ending at t0) |
| B | FORECAST-AVAILABLE | Product **issued** at/before t0, valid after t0 |
| C | POST-T0 OBSERVATION | ERA5/GloFAS reanalysis or GFM after t0 |
| D | UNAVAILABLE | Not in cube / not acquired |
| E | UNKNOWN | Semantics unclear |

These categories are not collapsed. Downloading ERA5 today for 2018-06-22 is still C if the window is after t0.

## 3. Current ERA5-Land limitation

The spatial lattice is hourly **2016-06-01 … 2024-08-31**, complete, ~11 km, Open-Meteo archive (ERA5-Land family).

- Rain **before t0**: OBSERVED-AVAILABLE (reanalysis lookback; ERA5 operational latency ~5 days is a residual caveat).
- Rain **during (t0, t1]**: POST-T0 OBSERVATION. Phase 6.8A completeness **95.6%** does **not** make it a forecast.
- A current forecast API is not a historical run archive.

## 4. Candidate forecast products

See `forecast_sources.json`. Headline:

| Product | Vintage? | Archive vs Target B | In cube? |
| --- | --- | --- | --- |
| ERA5-Land Open-Meteo lattice | No (reanalysis) | 2016–2024 | Yes |
| Open-Meteo Previous Runs | Partial (lead-offset 1–7 d) | mostly 2024+ | No |
| Open-Meteo Historical Forecast | No (blended runs) | ~2021+ | No |
| Open-Meteo Single Runs (IFS) | Yes | from 2024-03-14 | No |
| TIGGE ECMWF precip | Yes | 2006–present, covers 2015–2024 | No |
| NOAA GEFSv12 / operational GEFS | Mixed (reforecast ≠ ops) | yes if operational files used | No |
| GloFAS reanalysis Q | No | 2015–2024, 3 proxy cells | Yes, **192 h aligned** |
| GloFAS forecast Q (CDS) | Yes, 30 d | not acquired | No |

## 5. Forecast-vintage analysis

True vintage requires **RUN/ISSUE TIME + LEAD + VALID TIME** with `issue_time <= t0`.

- TIGGE stores initialisation time and step; ECMWF/NCEP TIGGE is CC BY 4.0; 48 h access delay (fine retrospectively).
- Open-Meteo Single Runs expose `run=` initialisation from March 2024 (IFS only for most of Target B history).
- Open-Meteo Previous Runs are 1–7 d offsets from Jan 2024, shorter than the 12-day median.
- GEFSv12 **reforecasts** use a frozen 2017 model: useful for skill studies, **not** “what GFS issued in 2016”.
- ERA5 has no issue_time. It cannot satisfy Gate 6.9A as FORECAST-AVAILABLE.

Acquired FORECAST-AVAILABLE precip pairs: **0** / 183.

## 6. Product availability by year

| Year | era5_lattice | tigge | openmeteo_previous_runs | openmeteo_single_runs | glofas_reanalysis_q | glofas_forecast_q |
| --- | --- | --- | --- | --- | --- | --- |
| 2015 | OUTSIDE_ARCHIVE | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2016 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2017 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2018 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2019 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2020 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2021 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2022 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2023 | COVERED | COVERED_NOT_ACQUIRED | OUTSIDE_ARCHIVE | OUTSIDE_ARCHIVE | COVERED | COVERED_NOT_ACQUIRED |
| 2024 | COVERED | COVERED_NOT_ACQUIRED | COVERED | COVERED | COVERED | COVERED_NOT_ACQUIRED |

## 7. Target-B alignment

`t0 = earlier.valid_at`, `t1 = later.valid_at`, `delta_t = t1 − t0` (unchanged from 6.8A). Labels were not rewritten. Splits remain event-isolated.

Cube hydrology issue is `t1 − 192 h`. Offset vs t0 is `192 − Δt` hours. At the median Δt = 12 d, cube Q ends **~4 days after t0**.

## 8. Rainfall coverage

| Quantity | Value |
| --- | --- |
| Observational in-horizon coverage (ERA5, POST-T0) | 0.956 |
| Acquired forecast in-horizon coverage | 0.000 |
| Hypothetical TIGGE 15 d mean coverage if acquired | 0.935 |
| Hypothetical deterministic 7 d mean coverage | 0.551 |

Hypothetical fractions are **not** data in the cube.

## 9. Hydrology coverage

| Cube Q vs Target B t0 | Pairs |
| --- | --- |
| POST_T0 (leak if used) | 178 |
| CAUSAL_BUT_STALE | 5 |
| CAUSAL_AT_T0 (Δt ≈ 192 h) | 0 |

River **level**, soil moisture, flow accumulation, and upstream routing: **UNAVAILABLE**. Reindexing reanalysis Q to t0 is specified, not implemented. GloFAS **forecast** Q is not acquired.

## 10. Delta-t distribution

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

Pairs with Δt ≤ 7 d: **5**. Pairs with Δt ≤ 15 d: **158**. Pairs with Δt > 15 d: **25**.

**Most pairs are beyond the useful deterministic NWP range (~7 days).** The median 12-day gap sits at the tail of ECMWF ENS / TIGGE (~15 d). 21–48 day pairs need subseasonal hydrology, not weather NWP.

## 11. Forcing coverage by delta_t

- 10-14 days: n=151, acquired forecast frac=0.000, hyp. TIGGE 15 d=1.000, hyp. 7 d=0.583, hydro POST_T0=151
- 14-21 days: n=2, acquired forecast frac=0.000, hyp. TIGGE 15 d=0.833, hyp. 7 d=0.389, hydro POST_T0=2
- 2-4 days: n=2, acquired forecast frac=0.000, hyp. TIGGE 15 d=1.000, hyp. 7 d=1.000, hydro POST_T0=0
- 21+ days: n=23, acquired forecast frac=0.000, hyp. TIGGE 15 d=0.501, hyp. 7 d=0.234, hydro POST_T0=23
- 4-7 days: n=3, acquired forecast frac=0.000, hyp. TIGGE 15 d=1.000, hyp. 7 d=1.000, hydro POST_T0=0
- 7-10 days: n=2, acquired forecast frac=0.000, hyp. TIGGE 15 d=1.000, hyp. 7 d=0.824, hydro POST_T0=2

## 12. Data availability matrix

| Input | Before t0 | Forecast at t0 | Post-t0 only | Status |
| --- | --- | --- | --- | --- |
| rainfall (ERA5-Land lattice) | OBSERVED-AVAILABLE | UNAVAILABLE | POST-T0 OBSERVATION | REANALYSIS in cube; in-horizon not a forecast input |
| rainfall accumulation | OBSERVED-AVAILABLE | UNAVAILABLE | POST-T0 OBSERVATION | 24/72 h maps end at 192 h issue in cube; Target B needs re-window at t0 |
| elevation | OBSERVED-AVAILABLE | n/a (static) | n/a | AVAILABLE static |
| slope | OBSERVED-AVAILABLE | n/a (static) | n/a | AVAILABLE static |
| river distance | OBSERVED-AVAILABLE | n/a (static) | n/a | AVAILABLE static |
| river mask | OBSERVED-AVAILABLE | n/a (static) | n/a | AVAILABLE static |
| river discharge | UNAVAILABLE in cube at Target B t0; reindexable MODELLED reanalysis | UNAVAILABLE | cube Q often POST_T0 vs Target B t0 | 192 h misaligned; GloFAS forecast not acquired |
| river level | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| prior GFM flood state | OBSERVED-AVAILABLE | n/a (state) | n/a | earlier GFM scene is the state at t0 |
| soil moisture | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | GloFAS historical SWI on CDS; not in cube |
| flow accumulation | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| NWP precipitation (TIGGE / Single Runs / GEFS) | n/a | EXISTENT_NOT_ACQUIRED | n/a | UNAVAILABLE |

## 13. Event-level coverage

Ten pairs from one flood remain **one** event. Official Gate B is still **FAIL** (15 < 20).

- `evt:2015-07-11`: 8 pairs, forecast frac=0.000, hydro POST_T0=5
- `evt:2016-06-30`: 2 pairs, forecast frac=0.000, hydro POST_T0=2
- `evt:2017-04-12`: 21 pairs, forecast frac=0.000, hydro POST_T0=21
- `evt:2017-07-31`: 9 pairs, forecast frac=0.000, hydro POST_T0=9
- `evt:2018-01-13`: 5 pairs, forecast frac=0.000, hydro POST_T0=5
- `evt:2018-06-06`: 5 pairs, forecast frac=0.000, hydro POST_T0=5
- `evt:2019-01-10`: 9 pairs, forecast frac=0.000, hydro POST_T0=9
- `evt:2019-06-15`: 10 pairs, forecast frac=0.000, hydro POST_T0=8
- `evt:2020-01-15`: 7 pairs, forecast frac=0.000, hydro POST_T0=7
- `evt:2020-06-07`: 18 pairs, forecast frac=0.000, hydro POST_T0=18
- `evt:2021-06-02`: 32 pairs, forecast frac=0.000, hydro POST_T0=32
- `evt:2022-05-16`: 10 pairs, forecast frac=0.000, hydro POST_T0=10
- `evt:2023-06-16`: 25 pairs, forecast frac=0.000, hydro POST_T0=25
- `evt:2024-06-22`: 22 pairs, forecast frac=0.000, hydro POST_T0=22

## 14. Provenance

Audit provenance is attached on `forecast_sources.json` and `targetb_forcing_audit.json`. ERA5 lattice and GloFAS reanalysis snapshots already carry Phase 4.5 / 6.5 provenance. TIGGE/GloFAS-forecast are documented, not retrieved.

Provenance complete (audit envelope): **True**.

## 15. Licensing

- ERA5-Land / Open-Meteo: CC BY 4.0.
- GloFAS reanalysis via Open-Meteo: CC BY 4.0; CEMS-FLOODS attribution.
- TIGGE ECMWF/NCEP: CC BY 4.0; some TIGGE centres CC BY-NC 4.0 — prefer ECMWF/NCEP for a commercial-safe path.
- GFM labels: CEMS proprietary STAC (unchanged).
- No WorldFloods. No global GloFAS cube download.

## 16. Gates 6.9A–G

| Gate | Status | Rule |
| --- | --- | --- |
| 6.9A | PASS | forecast-vintage integrity: FORECAST-AVAILABLE implies issue_time <= t0 |
| 6.9B | FAIL | in-horizon forecast precip coverage in the cube |
| 6.9C | FAIL | hydrological state available and aligned to Target B t0 |
| 6.9D | FAIL | temporal alignment of forecast/hydro forcing to Target B t0 (not valid_at−192 h) |
| 6.9E | PASS | no hindsight contamination: ERA5 in (t0,t1] is POST-T0 OBSERVATION, not a forecast input |
| 6.9F | FAIL | usable Target-B pairs with acquired causal in-horizon forecast forcing |
| 6.9G | PASS | event diversity of Target B pairs (not pair count); official Gate B still 20 |

Official Gate B is **not** modified.

## 17. Recommended input contract

```
STATE_AT_T0          = earlier GFM map
HISTORICAL_WEATHER   = ERA5-Land strictly before t0 (re-windowed)
FORECAST_WEATHER     = NWP vintage issue<=t0 covering (t0,t1]  — NOT IN CUBE
STATIC_TERRAIN       = DEM, slope
STATIC_RIVER         = distance, mask
OPTIONAL_HYDROLOGY   = GloFAS reanalysis Q reindexed to t0 (MODELLED); GloFAS forecast Q if acquired
```

Exclude: ERA5 in `(t0,t1]`, cube Q at valid_at−192 h, later GFM map.

## 18. Whether Target B can support forecasting

Target B remains an honest **observation** of flood change. It cannot yet support a causal spatial **forecast** experiment: acquired in-horizon NWP coverage is 0 pairs; ERA5 in the gap is POST-T0 OBSERVATION; cube GloFAS Q is 192 h-aligned and is POST_T0 for most 12-day pairs. Median Δt = 12.000011574074074 days is at/beyond deterministic NWP skill. A later TIGGE (or 2024-only Single Runs) acquisition would still leave hydrology thin.

## 19. Exact remaining blocker

Two first-class gaps: (1) no forecast-vintage precipitation with issue_time≤t0 covering (t0,t1] in the cube; (2) no Target-B-aligned hydrological state (Q/level/wetness). Do not treat ERA5-in-gap completeness as a substitute.

## 20. Next-phase recommendation

Do not train Target B baselines. If a next phase is approved, either (i) acquire TIGGE ECMWF precip (issue+lead+valid) for the 15 events without filling gaps, and/or (ii) reindex GloFAS reanalysis Q to last complete day before t0 as MODELLED state — still not a forecast. Do not invent 24 h GFM maps. Do not enable the spatial API. Do not couple the solver.

---

TARGET B: PARTIALLY FEASIBLE

FORECAST-VINTAGE FORCING: NOT ACQUIRED (TIGGE/Single Runs exist off-cube)

HYDROLOGICAL STATE: MISALIGNED (cube Q at valid_at−192 h); reanalysis reindex specified, forecast Q absent

MODEL TRAINING: NOT AUTHORIZED

SPATIAL AI: NOT_VALIDATED

SPATIAL API: UNAVAILABLE

SOLVER MODIFIED: NO

END.
