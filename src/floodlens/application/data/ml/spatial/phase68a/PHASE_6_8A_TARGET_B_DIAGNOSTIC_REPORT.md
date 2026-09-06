# Phase 6.8A — Target B observational transition diagnostic

**Status:** FORECASTABILITY AUDIT. Not a training run. Not a VALIDATED claim. No invented 24–168 h GFM maps.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**AOI GBDT:** VALIDATED status **unchanged** (separate registry, scalar AOI task).

**Solver:** `src/floodlens/numerical/**` was not modified.

**GFM dataset version (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Experiment id:** `phase6.8a-target-b-transition-v1`

**Decision:** **B** — TARGET B IS FEASIBLE BUT FORCING IS INSUFFICIENT

This phase does not train GBDT, RF, logistic, CNN, U-Net, transformer, or LSTM models.

---

## 1. Target B definition

Primary target: **NEWLY_FLOODED** pixels between consecutive GFM scenes of the same independent event and same AOI.

```
t0 = earlier.valid_at     # GFM SAR clock of scene k
t1 = later.valid_at       # GFM SAR clock of scene k+1
delta_t = t1 - t0         # measured observation interval; not 24/48/72 h
```

On pixels valid in **both** maps:

| Earlier | Later | Class |
| --- | --- | --- |
| DRY | FLOODED | NEWLY_FLOODED (primary) |
| FLOODED | DRY | RECEDING |
| FLOODED | FLOODED | PERSISTENT_FLOOD |
| DRY | DRY | PERSISTENT_DRY |
| any UNKNOWN | any | UNKNOWN |

Do not infer a transition when either endpoint is unknown. Original GFM masks are preserved. Secondary diagnostics: RECEDING, PERSISTENT_FLOOD, FLOOD_AREA_CHANGE, NET_FLOOD_CHANGE. None of these were trained on.

**SHORTER HORIZON NOT SUPPORTED BY CURRENT GFM LABEL TEMPORAL RESOLUTION.** Δt is reported as measured hours/days. A pair with Δt = 8 days is an 8-day pair, not a 72 h label.

## 2. Consecutive-scene pairing methodology

1. Use frozen Track A samples (`build_spatial_samples_v2`), event_id from the 45-day cluster (`EVENT_GAP_DAYS = 45`).
2. Group by `(event_id, city_id)`. Sort by `valid_at`.
3. Form adjacent pairs `(S_i, S_{i+1})` only. Do not pair `S_i` with `S_{i+2}`.
4. Do not pair scenes from different `event_id`, even if calendar dates are close.
5. Do not pair different AOIs. Maps are not co-registered across cities.
6. Inherit the frozen event-level split. Do not create pixel-i.i.d. splits.

Independent events in the cube: **15**. Observed transition pairs: **183**. Eligible (gates B1–B5): **183**.

## 3. Number of event pairs

| Quantity | Value |
| --- | --- |
| Independent events | 15 |
| Maps | 277 |
| (event, AOI) sequences | 94 |
| Observed transition pairs | 183 |
| Eligible pairs (B1–B5) | 183 |
| Train / val / test pairs | 50 / 76 / 57 |

Ten pairs from one flood are **one** independent event.

## 4. Number of independent events

**15** meteorological episodes (45-day rule unchanged). Events with at least one pair: **14**. Events with maps but no consecutive same-AOI pair: `evt:2016-01-19`.

## 5. Delta-t distribution

The horizon is the measured scene gap. It is not recoded to a product hour.

| Statistic | Hours | Days |
| --- | --- | --- |
| min | 84.13 | 3.51 |
| q25 | 288.00 | 12.00 |
| median | 288.00 | 12.00 |
| mean | 345.05 | 14.38 |
| q75 | 288.00 | 12.00 |
| max | 1152.00 | 48.00 |

| Bucket | Pairs |
| --- | --- |
| 0-2 days | 0 |
| 2-4 days | 2 |
| 4-6 days | 3 |
| 6-8 days | 0 |
| 8-12 days | 16 |
| 12+ days | 162 |

## 6. Unknown-mask statistics

UNKNOWN=255 is never scored as dry. A transition is UNKNOWN if either endpoint is unknown.

| Quantity | Value |
| --- | --- |
| Mean unknown transition fraction | 0.386 |
| Mean jointly valid fraction | 0.614 |
| Mean unknown fraction at t0 maps | 0.369 |
| Mean unknown fraction at t1 maps | 0.361 |

## 7. New-flood statistics

| Quantity | Value |
| --- | --- |
| Mean newly flooded fraction (joint pixels) | 0.028 |
| Median newly flooded fraction | 0.003 |
| Pairs with ≥1 newly flooded pixel | 131 |
| Mean n_newly_flooded | 87.5 |

## 8. Recession statistics

| Quantity | Value |
| --- | --- |
| Mean receding fraction | 0.030 |
| Median receding fraction | 0.002 |
| Pairs with ≥1 receding pixel | 127 |

## 9. Persistence statistics

| Quantity | Value |
| --- | --- |
| Mean IoU(t0, t1) jointly valid | 0.256 |
| Median IoU(t0, t1) | 0.144 |
| Mean persistent-flood fraction | 0.030 |
| Mean turnover (new + recede) / joint | 0.058 |

High IoU with long Δt is genuine haor inundation memory. Target B does **not** use the 192 h back-offset, so the nearest previous scene is the earlier map by construction.

## 10. Rainfall completeness

Required window for the **observed** transition is `(t0, t1]`. Missing hours are counted; they are **not** interpolated.

Lattice coverage: `2016-06-01` … `2024-08-31` hourly ERA5-Land / Open-Meteo (`REANALYSIS`).

| Class | Pairs |
| --- | --- |
| FORCING_COMPLETE | 175 |
| FORCING_PARTIAL | 0 |
| FORCING_MISSING | 8 |
| Complete fraction | 0.956 |

Observational completeness is **not** forecast-available forcing. Rain in `(t0, t1]` is **POST-T0 OBSERVATION**. Using it as a t0 feature would be leakage.

## 11. Feature availability

| Input | Status | Kind | Causal at t0? |
| --- | --- | --- | --- |
| Rainfall history before t0 (lattice 72 h) | see pair JSON | PRE-T0 AVAILABLE INPUT | yes, if complete |
| Rainfall during (t0, t1] | observational audit | POST-T0 OBSERVATION | **no** |
| Elevation / slope | AVAILABLE when present on earlier sample | static | yes |
| River distance / mask | AVAILABLE when present | static | yes |
| River discharge | UNAVAILABLE at Target B t0 | cube Q is 192 h-aligned | no (not re-fetched) |
| River level | UNAVAILABLE | — | no |
| Prior flood map | AVAILABLE (earlier GFM scene) | PRE-T0 | yes (state at t0) |
| Later flood map | TARGET | observation at t1 | no |

## 12. Event-level summaries

See `event_summaries.json`. Pair counts are nested under events; events remain the independent unit.

- `evt:2015-07-11`: 8 pairs, 5 AOIs, split=train, median Δt h=576.0, mean IoU=0.362, mean new-flood=0.008
- `evt:2016-06-30`: 2 pairs, 1 AOIs, split=train, median Δt h=576.0, mean IoU=0.200, mean new-flood=0.005
- `evt:2017-04-12`: 21 pairs, 7 AOIs, split=train, median Δt h=288.0, mean IoU=0.639, mean new-flood=0.034
- `evt:2017-07-31`: 9 pairs, 7 AOIs, split=train, median Δt h=288.0, mean IoU=0.122, mean new-flood=0.031
- `evt:2018-01-13`: 5 pairs, 5 AOIs, split=train, median Δt h=288.0, mean IoU=0.431, mean new-flood=0.000
- `evt:2018-06-06`: 5 pairs, 5 AOIs, split=train, median Δt h=288.0, mean IoU=0.272, mean new-flood=0.073
- `evt:2019-01-10`: 9 pairs, 7 AOIs, split=val, median Δt h=288.0, mean IoU=0.440, mean new-flood=0.000
- `evt:2019-06-15`: 10 pairs, 2 AOIs, split=val, median Δt h=288.0, mean IoU=0.094, mean new-flood=0.014
- `evt:2020-01-15`: 7 pairs, 7 AOIs, split=val, median Δt h=288.0, mean IoU=0.070, mean new-flood=0.000
- `evt:2020-06-07`: 18 pairs, 7 AOIs, split=val, median Δt h=504.0, mean IoU=0.179, mean new-flood=0.043
- `evt:2021-06-02`: 32 pairs, 7 AOIs, split=val, median Δt h=288.0, mean IoU=0.128, mean new-flood=0.013
- `evt:2022-05-16`: 10 pairs, 5 AOIs, split=test, median Δt h=576.0, mean IoU=0.190, mean new-flood=0.149
- `evt:2023-06-16`: 25 pairs, 5 AOIs, split=test, median Δt h=288.0, mean IoU=0.209, mean new-flood=0.029
- `evt:2024-06-22`: 22 pairs, 7 AOIs, split=test, median Δt h=288.0, mean IoU=0.309, mean new-flood=0.006

## 13. Geographic summaries

- `dhaka_ne`: 28 pairs / 12 events, mean IoU=0.215, mean new-flood=0.009
- `dhaka_nw`: 28 pairs / 12 events, mean IoU=0.265, mean new-flood=0.009
- `dhaka_se`: 18 pairs / 8 events, mean IoU=0.073, mean new-flood=0.004
- `dhaka_sw`: 20 pairs / 9 events, mean IoU=0.339, mean new-flood=0.010
- `kishoreganj`: 29 pairs / 12 events, mean IoU=0.329, mean new-flood=0.048
- `netrokona`: 30 pairs / 12 events, mean IoU=0.269, mean new-flood=0.039
- `sunamganj`: 30 pairs / 12 events, mean IoU=0.229, mean new-flood=0.060
- `sylhet`: 0 pairs (maps exist; no consecutive same-AOI scene pair)

## 14. Temporal summaries

- 2015: 8 pairs / 1 events, mean turnover=0.025
- 2016: 2 pairs / 1 events, mean turnover=0.005
- 2017: 30 pairs / 2 events, mean turnover=0.039
- 2018: 10 pairs / 2 events, mean turnover=0.048
- 2019: 19 pairs / 2 events, mean turnover=0.014
- 2020: 25 pairs / 2 events, mean turnover=0.071
- 2021: 32 pairs / 1 events, mean turnover=0.025
- 2022: 10 pairs / 1 events, mean turnover=0.310
- 2023: 25 pairs / 1 events, mean turnover=0.055
- 2024: 22 pairs / 1 events, mean turnover=0.064

By flood mechanism:

- `haor_monsoon_inundation`: 65 pairs / 7 events, mean IoU=0.222, mean turnover=0.085
- `haor_premonsoon_flash`: 31 pairs / 2 events, mean IoU=0.478, mean turnover=0.128
- `monsoon_riverine`: 66 pairs / 9 events, mean IoU=0.176, mean turnover=0.015
- `winter_or_early`: 21 pairs / 3 events, mean IoU=0.302, mean turnover=0.006

By Δt bucket (IoU vs change):

- 12+ days: n=162, mean IoU=0.260, mean new-flood=0.031
- 2-4 days: n=2, mean IoU=0.198, mean new-flood=0.003
- 4-6 days: n=3, mean IoU=0.495, mean new-flood=0.015
- 8-12 days: n=16, mean IoU=0.177, mean new-flood=0.002

## 15. Causal-input limitations

A forecast issued at t0 may use only information at or before t0.

- Pre-t0 lattice rain coverage (pair mean): **0.956**.
- In-horizon observational rain coverage (pair mean): **0.956**.
- Forecast-available in-horizon rain (NWP in cube): **False**.
- Pearson new-flood fraction vs pre-t0 rain sum: **0.378**.
- Pearson new-flood fraction vs in-horizon rain sum (association only): **0.234**.

In-horizon rain is tabulated as a diagnostic association. It is not a model feature.

## 16. Gate B1–B7

| Gate | Result | Rule |
| --- | --- | --- |
| B1 | PASS | valid earlier/later pair (same AOI, later after earlier, maps exist) |
| B2 | PASS | same real-world event_id; calendar proximity is not sufficient |
| B3 | PASS | jointly valid transition mask (unknown never inferred) |
| B4 | PASS | no target leakage; in-horizon rain is POST-T0 OBSERVATION |
| B5 | PASS | forcing completeness recorded (COMPLETE/PARTIAL/MISSING) |
| B6 | PASS | transition signal: ≥20 pairs with new-flood or recession, mean turnover ≥0.01, ≥5 events; pixel count alone is not enough |
| B7 | PASS | ≥8 independent events represented by pairs (not pair count) |

Class: **FORECASTABILITY AUDIT**. Not DIAGNOSTICALLY PROMISING / VALIDATED. Official Gate B still requires 20 GFM events.

## 17. Comparison against the previous 192 h formulation

| | A@192 h (Track A cube) | Target B |
| --- | --- | --- |
| t0 | `valid_at − 192 h` (SAR-slaved) | earlier scene `valid_at` |
| Horizon | always 192 h | measured Δt |
| Label | occurrence snapshot at later SAR time | NEWLY_FLOODED on jointly valid pixels |
| Persistence feature | previous scene with `valid_at < t0` (nearest scene often illegal if revisit < 8 d) | earlier map **is** the state at t0 |
| Rain in the gap | withheld (correct for a forecast; fatal for rain-driven inundation) | observed for diagnostics; **not** a causal feature |
| 6–72 h product | UNSUPPORTED | still UNSUPPORTED |

Phase 6.7: GBDT copied persistence on occurrence@192 h. Target B attacks that copy-last-map objective. It does not create a 24 h GFM map.

## 18. Whether Target B is scientifically more promising

Target B is an honest change label: mean jointly-valid IoU(t0,t1)=0.256, mean turnover=0.058, 131 eligible pairs show new inundation. That is more interpretable than occurrence@192 h, which Phase 6.7 showed is dominated by persistence/climatology. It is **not** automatically a better *forecast*: in-horizon rain is POST-T0 OBSERVATION (forecast-available NWP in the cube: False; observational completeness 0.956). Letter E is withheld: 6–72 h spatial maps remain unsupported, official event n is 15, and replacing Track A as a product target requires forecast-kind forcing, not a prettier diagnostic.

## 19. What remains missing

- FORECAST-kind rain / NWP in `(t0, t1]` if Target B is ever trained as a forecast.
- River discharge and wetness aligned to Target B t0 (not the 192 h issue time).
- Official Gate B (20 independent GFM events) still FAIL at 15.
- 6–72 h spatial API maps remain UNSUPPORTED.
- Depth change remains UNSUPPORTED (no GFM depth).

## 20. Exact next-step recommendation

Keep Target B as the observational change diagnostic. Do not train yet. Next authorized step, if any: add FORECAST-kind (NWP) rain for `(t0, t1]` as an explicit forcing layer, or a no-training study of whether pre-t0 rain + state at t0 can rank new-flood pixels. Do not invent 24 h GFM maps. Do not enable `/api/v1/forecast/ai-spatial`.

---

TARGET B STATUS: TARGET B IS FEASIBLE BUT FORCING IS INSUFFICIENT

SPATIAL AI: NOT_VALIDATED

SPATIAL API: UNAVAILABLE

MODEL TRAINING: NOT AUTHORIZED

TRACK A: DIAGNOSTIC ONLY

TRACK B: SEPARATE HISTORICAL BENCHMARK

TRACK C: NOT YET IMPLEMENTED

SOLVER MODIFIED: NO

END.
