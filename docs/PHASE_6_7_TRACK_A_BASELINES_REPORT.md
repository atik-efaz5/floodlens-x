# Phase 6.7 — Track A diagnostic baselines

**Status:** DIAGNOSTIC BASELINE STUDY. Not a VALIDATED claim. Not a production model.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**AOI GBDT:** VALIDATED status **unchanged** (separate registry, scalar AOI task).

**Solver:** `src/floodlens/numerical/**` was not modified.

**Dataset version:** `phase6.5-gfm-spatial-v2.1`

**Experiment id:** `phase6.7-track-a-baselines-v1`

**Config hash:** `10d44c4acfabf414cc7eabc8daee2e73bd3198dffb598f82275b32a3408495df`

**Diagnostic classification:** **MIXED**

Machine-readable artifacts: `src/floodlens/application/data/ml/spatial/phase67/` and `src/floodlens/application/data/ml/spatial/phase67_eval.json`.

---

## 1. Objective

Determine whether the frozen 15-event GFM Track A cube contains causal predictive signal beyond persistence, climatology, and a rainfall threshold — before any CNN/U-Net or Track C transfer work.

This phase trains only diagnostic baselines. It does not promote spatial AI, does not enable the spatial API, and does not change official Gates A–J.

The scientific question is not “did a pooled-pixel metric move.” It is: **does any causal learned baseline consistently beat persistence on event-macro metrics across multiple held-out events, without leakage or unknown-mask artifacts?**

---

## 2. Frozen dataset definition

| Field | Value |
| --- | --- |
| Dataset version | `phase6.5-gfm-spatial-v2.1` |
| Independent events | **15** |
| Maps / AOI tiles | **277** (train 90 / val 111 / test 76) |
| Train events (7) | `evt:2015-07-11`, `2016-01-19`, `2016-06-30`, `2017-04-12`, `2017-07-31`, `2018-01-13`, `2018-06-06` |
| Val events (5) | `evt:2019-01-10`, `2019-06-15`, `2020-01-15`, `2020-06-07`, `2021-06-02` |
| Test events (3) | `evt:2022-05-16`, `2023-06-16`, `2024-06-22` |
| Regions | dhaka_ne/nw/se/sw, kishoreganj, netrokona, sunamganj, sylhet |
| Target | binary occurrence at **t0 + 192 h**; τ = 0.25; unknown = 255 |
| Label kind | OBSERVED (Copernicus GFM `ensemble_flood_extent`) |
| Valid pixels (all maps) | 730,577 (flood 48,174; dry 682,403) |
| Unknown fraction | **0.356** |
| Flood prevalence among valid | 0.066 |

The split matches the frozen `splits_v2/splits.json` manifest. Pixel-i.i.d. splitting is forbidden.

---

## 3. Label vs working-grid resolution

| Quantity | Value |
| --- | --- |
| Observation / label native resolution | **20 m** Equi7 Asia AS020M (`E039N021T3`) |
| Working tensor | **64×64** on AOI geographic bounds |
| Working cell size | Sunamganj ≈ **473 m**; Dhaka subtiles ≈ **636–637 m**; Kishoreganj ≈ **792 m**; Netrokona ≈ **789 m**; Sylhet ≈ **1263 m** |

The working grid is **not** a 20 m CNN grid. Metrics in this report are on the working tensor. Do not describe 64×64 outputs as native GFM resolution.

---

## 4. Event splits

Scheme: **event-temporal** (`assign_event_level_splits`). Train event-start &lt; 2019-01-01; val &lt; 2022-01-01; test = 2022 named holdout + later years.

Same `event_id` does not appear in two splits (Gate 6.7B). Geographic holdout is a **separate** evaluation and is **not** a replacement for this split.

Official test n = 3 events is not statistically useful on its own. Val+test (**8 events**) is the diagnostic held-out window. Both are reported.

---

## 5. Feature inventory

Eighteen causal pixel columns known at t0 (no rain after t0; persistence `valid_at < t0`):

`antecedent_24h`, `antecedent_72h`, `precip_24h_local`, `precip_72h_local`, `precip_6h`, `log1p_q`, `month_sin`, `month_cos`, `persistence`, `persistence_valid`, `row_norm`, `col_norm`, `dem`, `slope`, `river_distance`, `precip_is_aoi_point`, `q_is_glofas_cell`, `precip_mean_6h`

Rain is ERA5-Land / Open-Meteo lattice IDW onto the working grid. GloFAS Q is a MODELLED tile scalar. 6/12/24/48/72 h spatial labels are not used.

---

## 6. Baseline definitions

| Baseline | Inputs | Notes |
| --- | --- | --- |
| Persistence | last completed GFM before t0 | missing persistence → 0 |
| Climatology | train AOI × month flood frequency | **AOI-aware**; not a stacked multi-AOI 64×64 |
| Rain threshold | causal 24 h rain map | candidates {10, 25, 50, 75} mm plus train 70th percentile; **chosen = 10 mm** by train event-macro IoU |
| Logistic | 18 causal pixel features | class-weighted |
| Pixel GBDT | 18 causal pixel features | existing numpy GBDT, 20 trees, seed 0; treated as a **new** Track A experiment |
| Conv-smooth | 3×3 mean of persistence | neighborhood baseline, **not** a CNN |
| GBDT no-persistence | 16 features (persistence dropped) | fair beat-persistence probe |

A GBDT that **includes** the persistence map is not a fair “beats persistence” test. Gate 6.7F uses **GBDT no-persistence**.

---

## 7. Leakage controls

| Check | Result |
| --- | --- |
| `assert_no_spatial_leakage` | PASS (0 problems) |
| Unknown never scored as dry | PASS |
| Persistence lagged (`valid_at < t0`) | PASS |
| FORECAST rain in lookback | none |
| Event leak train/val/test | none |
| 6–72 h labels | unused |
| Split lock vs `splits_v2` | PASS |

---

## 8. Unknown-mask handling

GFM 255 remains unknown. Metrics use finite / non-255 pixels only. Unknown is never converted to dry, flooded, or probability zero. Every event row below reports `n_valid_pixels`, `n_flood`, and `unknown_fraction`.

---

## 9. Overall metrics

Headline ranking is **event-macro IoU**. Micro-IoU pools every valid pixel and lets large maps dominate.

AUROC is recorded in the JSON but is **not** a headline (rare flood class).

### Test split (3 events)

| Model | Event-macro IoU | Micro IoU | Event-macro Dice | Event-macro AUPRC | Recall | Precision | Event-macro Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| climatology | **0.295** | 0.315 | 0.443 | 0.316 | 0.459 | 0.459 | 0.111 |
| persistence | 0.174 | 0.185 | 0.292 | 0.243 | 0.297 | 0.290 | 0.166 |
| pixel_gbdt (all features) | 0.174 | 0.185 | 0.292 | 0.243 | 0.297 | 0.290 | 0.173 |
| pixel_logistic | 0.149 | 0.121 | 0.250 | 0.277 | 0.855 | 0.161 | 0.596 |
| rain_threshold | 0.144 | 0.108 | 0.238 | 0.259 | 0.690 | 0.162 | 0.562 |
| conv_smooth | 0.137 | 0.151 | 0.236 | 0.222 | 0.222 | 0.253 | 0.143 |
| pixel_gbdt_no_persistence | 0.111 | 0.093 | 0.178 | 0.220 | 0.197 | 0.181 | 0.213 |

GBDT **with** persistence ties persistence **exactly** on IoU/Dice/AUPRC/recall/precision at the 0.5 operating point: the learned classifier copies the lag map.

### Val+test (8 held-out events)

| Model | Event-macro IoU | Micro IoU | Event-macro AUPRC | Event-macro Brier | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| climatology | **0.162** | 0.230 | 0.188 | 0.066 | 8 |
| persistence | 0.104 | 0.165 | 0.136 | 0.087 | 8 |
| pixel_gbdt (all features) | 0.104 | 0.165 | 0.136 | 0.138 | 8 |
| rain_threshold | 0.074 | 0.079 | 0.122 | 0.395 | 8 |
| conv_smooth | 0.073 | 0.133 | 0.123 | 0.072 | 8 |
| pixel_logistic | 0.073 | 0.083 | 0.126 | 0.443 | 8 |
| pixel_gbdt_no_persistence | 0.059 | 0.066 | 0.108 | 0.188 | 8 |

Micro IoU is higher than event-macro IoU for persistence/climatology/GBDT because large monsoon maps outweigh winter residual events. That is why both averages are required.

---

## 10. Event-level metrics

### Test events

| Event | Model | IoU | Dice | Prec | Rec | AUPRC | Brier | Valid | Flood | Unknown |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| evt:2022-05-16 | persistence | 0.159 | 0.274 | 0.292 | 0.258 | 0.347 | 0.291 | 44160 | 9402 | 0.366 |
| evt:2022-05-16 | climatology | **0.454** | 0.625 | 0.611 | 0.639 | 0.434 | 0.156 | 44160 | 9402 | 0.366 |
| evt:2022-05-16 | rain_threshold | 0.281 | 0.438 | 0.329 | 0.656 | 0.524 | 0.358 | 44160 | 9402 | 0.366 |
| evt:2022-05-16 | gbdt (all) | 0.159 | 0.274 | 0.292 | 0.258 | 0.347 | 0.228 | 44160 | 9402 | 0.366 |
| evt:2022-05-16 | gbdt no-pers | **0.289** | 0.448 | 0.478 | 0.422 | 0.507 | 0.209 | 44160 | 9402 | 0.366 |
| evt:2023-06-16 | persistence | 0.103 | 0.187 | 0.164 | 0.217 | 0.088 | 0.080 | 76661 | 3255 | 0.376 |
| evt:2023-06-16 | climatology | **0.247** | 0.397 | 0.329 | 0.499 | 0.225 | 0.064 | 76661 | 3255 | 0.376 |
| evt:2023-06-16 | gbdt no-pers | 0.019 | 0.037 | 0.022 | 0.104 | 0.049 | 0.211 | 76661 | 3255 | 0.376 |
| evt:2024-06-22 | persistence | **0.261** | 0.414 | 0.413 | 0.415 | 0.293 | 0.126 | 75023 | 8062 | 0.368 |
| evt:2024-06-22 | climatology | 0.183 | 0.309 | 0.438 | 0.238 | 0.290 | 0.114 | 75023 | 8062 | 0.368 |
| evt:2024-06-22 | gbdt no-pers | 0.026 | 0.050 | 0.042 | 0.064 | 0.104 | 0.218 | 75023 | 8062 | 0.368 |

Test events have **no Sylhet maps**. Unknown ≈ 37% on every test event.

### Validation events

| Event | Flood px | Unknown | Persist IoU | Clim IoU | GBDT-all IoU | GBDT-no-pers IoU | Rain IoU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| evt:2019-01-10 | 30 | 0.344 | 0.015 | 0.040 | 0.015 | 0.000 | 0.000 |
| evt:2019-06-15 | 1465 | 0.250 | 0.010 | 0.070 | 0.010 | 0.022 | 0.049 |
| evt:2020-01-15 | 34 | 0.352 | 0.005 | 0.041 | 0.005 | 0.000 | 0.000 |
| evt:2020-06-07 | 4497 | 0.400 | 0.199 | 0.211 | 0.199 | 0.097 | 0.091 |
| evt:2021-06-02 | 1844 | 0.367 | 0.079 | 0.050 | 0.079 | 0.018 | 0.019 |

Winter events `2019-01-10` and `2020-01-15` have 30 and 34 flood pixels. They are residual-water GFM clusters, not independent monsoon floods of comparable magnitude. They crush event-macro scores for every model.

---

## 11. Geographic metrics

**GEOGRAPHIC GENERALIZATION TEST: INSUFFICIENT DATA**

Strict event-exclusive holdout (all tiles of an event in geo-test AOIs `sunamganj` / `sylhet` / `netrokona`, none in Dhaka/Kishoreganj):

| Set | Events |
| --- | --- |
| Train-only (Dhaka/Kishoreganj exclusively) | `evt:2016-06-30` only |
| Test-only (haor exclusively) | **none** |
| Mixed (both sides) | 14 of 15 events |

A city-level geographic split therefore **leaks the same `event_id` into both sides**. The existing AOI holdout was still run as specified (90 geo-test maps, 14 event ids) and **must not** be read as geographic generalization:

| Model | Event-macro IoU (city-level geo-test) | Micro IoU |
| --- | ---: | ---: |
| persistence | 0.127 | 0.279 |
| pixel_gbdt | 0.112 | 0.195 |

GBDT does not beat persistence on that leaky split either.

Sylhet is absent from the official test events. Two GFM Sylhet scenes in the cube do **not** establish Sylhet skill.

---

## 12. Temporal metrics

Official future-year test = 2022–2024 (3 events). Performance is not dominated by a single year, but n = 3 cannot support a temporal-generalization claim.

Val+test GBDT-with-persistence event-macro IoU by year (copies persistence): 2019 0.012; 2020 0.102; 2021 0.079; 2022 0.159; 2023 0.103; 2024 0.261.

By mechanism (same GBDT, event-macro IoU): winter_or_early **0.010** (n=2); haor monsoon / monsoon riverine 0.135 (n=6, overlapping tags); haor premonsoon flash 0.159 (n=1, `evt:2022-05-16`).

Winter residual water is a **mechanism failure**, not hidden in the aggregate if event-macro is used. Micro-IoU would hide it.

---

## 13. Ablation results

GBDT retrained on train events only; scored on val+test. Groups A–E **exclude** persistence.

| Ablation | Features | Event-macro IoU | Micro IoU |
| --- | ---: | ---: | ---: |
| A rainfall only | 6 | 0.053 | 0.054 |
| B terrain only | 2 | 0.067 | 0.064 |
| C river / spatial static | 3 | 0.074 | 0.074 |
| D rainfall + terrain | 8 | 0.063 | 0.067 |
| E rainfall + terrain + river | 11 | 0.063 | 0.067 |
| F all (includes persistence) | 18 | 0.104 | 0.165 |

Without persistence, static river/location columns are the least-bad feature group and still well below persistence (0.104 event-macro). Adding rainfall to terrain does not help at this n. **F equals persistence** because persistence is in the feature set.

---

## 14. Feature importance

**Association / predictive contribution ≠ physical causality.**

GBDT permutation importance on val events (Δ event-macro Brier after shuffling one column): only **`persistence`** moved Brier (Δ ≈ +0.004). All other columns shuffled to **exactly zero** change. That matches the operating-point collapse: the 20-tree GBDT is a persistence copy.

Logistic coefficients (unstandardized; magnitude is not comparable across units): largest |coef| are `dem` (−15.1), `month_sin` (+12.5), `persistence` (+9.6), `log1p_q` (+6.3). Logistic **over-predicts flood** (high recall, low precision, Brier ≈ 0.44–0.63) and is not competitive.

---

## 15. Calibration

Phase 5.5 conformal coverage ≈ 0.69 is **not** reused.

| Split | Model | ECE (10 bins) | Brier | Status |
| --- | --- | ---: | ---: | --- |
| val+test | pixel_gbdt | 0.284 | — | **NOT CALIBRATED** |
| test | pixel_gbdt | 0.260 | — | **NOT CALIBRATED** |

Probabilities are not a confidence product. Do not present them as calibrated uncertainty.

---

## 16. Bootstrap / uncertainty

Unit of resampling = **event**, not pixel. 1000 draws, seed 0.

| Comparison (val+test, n=8) | Mean Δ IoU (model − persistence) | 95% event bootstrap CI |
| --- | ---: | --- |
| climatology | +0.058 | [−0.012, +0.133] |
| GBDT no-persistence | −0.045 | [−0.110, +0.016] |
| GBDT all features | 0.000 | [0.000, 0.000] (exact tie) |

Test-only (n=3) GBDT no-persistence ΔIoU = −0.063, CI [−0.235, +0.130]. The interval is wide because there are three events. **Neither climatology nor learned GBDT has a CI that excludes zero.**

---

## 17. Failure analysis

| Pattern | Events / observation |
| --- | --- |
| Best persistence (test) | `evt:2024-06-22` IoU 0.261 |
| Worst persistence (test) | `evt:2023-06-16` IoU 0.103 |
| Best climatology (test) | `evt:2022-05-16` IoU 0.454 |
| Almost no flood | `evt:2019-01-10` (30 px), `evt:2020-01-15` (34 px) |
| Persistence copies GBDT | all 8 val+test events at threshold 0.5 |
| Rain helps vs persistence | `evt:2022-05-16`, `evt:2019-06-15` |
| GBDT no-pers beats persistence | `evt:2019-06-15`, `evt:2022-05-16` (2 of 8) |
| Unknown | ~35–38% on held-out monsoon events; not recoded |

Interpretation of failures:

- **Label quality:** winter GFM residual water is the wrong target for a monsoon forecast claim.
- **Rainfall mismatch:** 10 mm threshold raises recall and destroys precision except on the 2022 premonsoon.
- **Temporal mismatch:** 192 h GFM slot vs 8-day persistence lag; stale SAR still beats rain/terrain GBDT on most monsoons.
- **Mechanism:** premonsoon (`2022-05-16`) is the only test event where rain and no-persistence GBDT beat persistence.
- **Resolution:** working cells are 0.5–1.3 km; ERA5-Land rain is coarser still.
- **Insufficient feature signal:** ablations A–E never approach persistence.

---

## 18. Persistence comparison

**Does any causal learned baseline consistently beat persistence?** **No.**

| Probe | Result |
| --- | --- |
| GBDT **with** persistence | Ties persistence on IoU (copies the lag map) |
| GBDT **without** persistence | Loses on 6/8 held-out events; mean ΔIoU −0.045; CI includes 0 |
| Logistic | High recall, poor precision; event-macro IoU below persistence |
| Rain threshold | Helps 2022-05-16; fails 2023/2024 |
| Conv-smooth | Worse than raw persistence |
| Climatology (not a learned sequential model) | Highest event-macro IoU; beats persistence on 6/8 events; **CI still includes 0** |

Climatology is a **seasonal location prior**, not a 192 h event forecast. It is a valid causal baseline. Its test win (`2022-05-16` IoU 0.454) shows that “where flooding usually occurs in this month on this AOI” can outperform last week’s SAR when the lag map is a poor nowcast. It does **not** justify a production spatial model.

---

## 19. Scientific interpretation

**Classification: MIXED.**

Why not DIAGNOSTICALLY PROMISING: learned models do not improve event-macro IoU over persistence across multiple events; calibration is NOT CALIBRATED; geographic holdout is INSUFFICIENT DATA; official test n = 3.

Why not WEAK / “data too weak to compare”: the comparison **was** run; persistence vs climatology vs GBDT is measurable; two premonsoon-like events show rain/no-persistence signal; climatology is consistently better than a coin-flip, even if the bootstrap CI includes zero.

Why MIXED rather than “learned baselines clearly beat persistence”: they do not. The only model that ranks above persistence is monthly AOI climatology, and even that is not significant at 95% event-bootstrap.

Track A contains **some** spatial structure (seasonal inundation footprint). It does **not** currently contain a learned 192 h forecast signal that survives a fair persistence test.

---

## 20. Limitations

- Official Gate B still FAIL (15 &lt; 20 independent GFM events).
- Test split has 3 events; bootstrap intervals are wide.
- Winter GFM clusters have near-zero flood pixels and should not be averaged away — and also should not be treated as monsoon skill.
- ~36% unknown GFM pixels.
- Working grid is ~0.5–1.3 km, not 20 m.
- Geographic holdout is AOI-based; 14/15 events straddle both sides.
- Rain is ERA5-Land / Open-Meteo lattice, coarse on haor AOIs.
- 192 h is not a 6–72 h forecast.
- GBDT used 20 trees and an 8,000-pixel subsample (seed 0). This is a diagnostic, not HPO.
- Logistic coefficients are unstandardized.

---

## 21. Recommendation for next phase

Do **not** promote spatial AI. Do **not** enable `POST /api/v1/forecast/ai-spatial`. Do **not** train a U-Net.

1. Keep pixel GBDT as the learned bar; it has not beaten persistence.
2. Treat AOI×month climatology as the strongest *simple* baseline to beat, with the caveat that it is a location prior.
3. Expand independent **monsoon** GFM events (not more winter residuals) if the next goal is Gate B / Gate G.
4. If diagnostics continue, drop or separately stratum winter clusters when reporting monsoon skill — without changing the official 15-event inventory unless a later inventory revision is approved.
5. Track B/C remain blocked (no rasters; multi-resolution model not justified).
6. Recalibration is pointless until a model produces non-degenerate probabilities.

---

## Gate 6.7A–G

These gates do **not** define VALIDATED.

| Gate | Name | Result |
| --- | --- | --- |
| 6.7A | Baseline reproducibility | **PASS** (frozen 7/5/3, config hash above, seed 0) |
| 6.7B | No leakage | **PASS** |
| 6.7C | Metric integrity | **PASS** (valid pixels only; micro + event-macro) |
| 6.7D | Event-level evaluation | **PASS** |
| 6.7E | Feature-signal diagnosis | **PASS** (ablations A–F) |
| 6.7F | Baseline competitiveness | **MIXED** (climatology &gt; persistence on point estimate; learned GBDT does not beat persistence; 2/8 no-pers wins; CI includes 0) |
| 6.7G | Generalization evidence | **FAIL / INSUFFICIENT DATA** |

**Overall diagnostic class:** MIXED

---

SPATIAL AI:
NOT_VALIDATED

SPATIAL API:
UNAVAILABLE

MODEL TRAINING:
DIAGNOSTIC BASELINES ONLY

SOLVER MODIFIED:
NO

END.
