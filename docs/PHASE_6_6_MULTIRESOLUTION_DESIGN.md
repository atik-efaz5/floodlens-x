# Phase 6.6 — Multi-resolution flood dataset and forecastability design

**Status:** DESIGN DOCUMENT. Not an implementation. Not a training run. Not a VALIDATED claim.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**AOI GBDT:** VALIDATED status **unchanged** (separate registry, separate task).

**Solver:** `src/floodlens/numerical/**` is not modified by this design.

**GFM dataset version (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Event registry version (unchanged):** `phase6.5-multisource-event-v1`

**This phase does not train a model and does not acquire rasters.**

---

## Naming (read first)

Three different “B / C” labels are in use. They are not the same decision.

| Label | Meaning |
| --- | --- |
| Phase 6.5C decision **B** | GFM + second source for **event discovery only**. No pixel merge. |
| Phase 6.6 **Track C** | A **research framework** (experiment sequence), not a unified model. |
| This document’s architecture recommendation **B** | Separate native-resolution benchmarks **plus** a shared event registry. |

Phase 6.5C compatibility pair codes remain: **A** = unified training labels, **B** = auxiliary eval track, **C** = discovery only, **D** = incompatible. No source pair is A.

---

## 1. Current checkpoint

| Quantity | Value |
| --- | --- |
| GFM-only independent events (official Gate B) | 15 |
| GFM cube-eligible / forecast-cube-eligible | 15 |
| GFM indexed including non-cube (`evt:2025-07-11`) | 16 |
| Combined real-world independent events (registry) | 36 |
| Unique historical events beyond GFM | 21 (almost all pre-2015) |
| GFD ∩ GFM matched clusters | 3 |
| DFO ∩ GFM matched clusters | 10 |
| Spatial channels | 9 |
| GFM unknown pixels | ≈35.6% (worst event ≈88.7%) |
| Official Gate B | FAIL (15 < 20) |
| Official Gate F | PASS (8 valid AOIs; Sylhet = 2 events) |
| Spatial AI | NOT_VALIDATED |
| Model training | NOT AUTHORIZED |

Do not use 36 as the number of high-resolution training examples.

---

## 2. The three tracks (datasets / benchmarks, not models)

These are **benchmark tracks**. They are not models, not APIs, and not production products.

### Track A — high-resolution GFM benchmark (PRIMARY)

| Field | Definition |
| --- | --- |
| Label source | Copernicus GFM `ensemble_flood_extent` (CEMS / EODC) |
| Observation semantics | Sentinel-1 SAR algorithm ensemble; classes 0 dry, 1 flood, 255 nodata/exclusion |
| Label kind | **OBSERVED** |
| Native spatial resolution | 20 m Equi7 Asia AS020M (`E039N021T3`) |
| Working tensor | 64×64 on AOI geographic bounds (~0.5–1 km/cell; Sunamganj ≈ 470 m). **Not a 20 m CNN grid.** Do not claim 20 m tensors. |
| Temporal resolution | S1 revisit ~6–12 days; each scene is a **192 h** slot |
| Geographic coverage | Eight AOIs: sunamganj, sylhet, kishoreganj, netrokona, dhaka_sw/se/nw/ne. Product catalog remains Dhaka / Sunamganj / Sylhet. |
| Event coverage | 15 cube-eligible independent 45-day events; 2015–2024 (2025 GFM exists without rain lattice) |
| Features | ERA5-Land / Open-Meteo precip lattice (2016-06-01 … 2024-08-31), elevation + slope, OSM river distance/mask, lagged GFM persistence, GloFAS Q lookback (MODELLED scalar) |
| Target | Binary flood **occurrence** per working cell at **t0 + 192 h** |
| Flood threshold | Working-cell flood if valid flood fraction ≥ τ = 0.25 |
| Unknown mask | 255 retained; never recoded as dry; metrics on finite / non-255 only |
| Permanent water | Not a separate class; may appear as flood or dry |
| Forecast horizon | **192 h SUPPORTED.** 6 / 12 / 24 / 48 / 72 h **UNSUPPORTED** (not interpolated). |
| Pre-event baseline | Last completed GFM map with `valid_at < t0` |
| Splits | Event-level temporal (train issue < 2019-01-01, val < 2022-01-01, test 2022+ and named holdout). Same `event_id` must not sit in two splits. Pixel-i.i.d. forbidden. Current split: 7 / 5 / 3 events. |
| Scientific purpose | The only task in the repo whose labels, horizon, and features are aligned for a spatial *forecast*. |
| Limitations | n = 15 < Gate B floor; ~36% unknown; Dhaka NE unknown ≈ 84%; three winter clusters are weak residual water; Sylhet n = 2; ERA5-Land is coarse on haor AOIs; 192 h is not a 24 h forecast. |
| Status | **READY** as a dataset; **INSUFFICIENT_DATA** / **NOT_VALIDATED** for catalog AI |

Further GFM acquisition may improve scene quality (covering orbits, 2025 rain lattice). It is **not** expected to reach 20 independent monsoons on this Equi7 tile without weakening the 45-day rule. Do not inflate Gate B with additional winter residual clusters.

**Track A event-count bands (research; official Gate B floor stays 20):**

| Band | Independent GFM events | Meaning |
| --- | ---: | --- |
| Diagnostic / baseline-only | 15 (current) | Persistence/climatology/unknown studies. Underpowered. Not VALIDATED. |
| Minimum viable to *attempt* Gate G | **20**, with ≥10 train | Official Gate B / Gate 1. Still not automatic sufficiency. |
| Research-useful | **30** | Research recommendation PASS band from 6.5B. |
| Strong | **40+** | Prefer for geographic + mechanism stratification. |

**What 15 events may be used for:** descriptive baselines, mask diagnostics, split-manifest integrity, documentation of underpower. **Not** for production spatial AI, catalog VALIDATED, or claiming Sylhet / Jamuna / Padma generalization.

### Track B — historical coarse-resolution benchmark (SECONDARY)

Do **not** automatically merge Giezendanner and GFD. They are different observation families.

| Candidate | Native label | Semantics | License | Access now | Forecast role |
| --- | --- | --- | --- | --- | --- |
| Bangladesh Inundation History (Giezendanner et al. 2023, DOI 10.25739/2edm-jh03) | 500 m, 8-day, 2001–2022 | **DERIVED** CNN–LSTM fractional inundation (S1 fractions fused onto MODIS). Not binary GFM. Training stack used FABDEM (CC BY-NC-SA). | CyVerse curated; companion code MIT | **UNAVAILABLE** (anonymous GET → captcha) | If acquired: 8-day composite **hindcast**, causal t0 only |
| Global Flood Database v1 | 250 m event-maximum + duration | **OBSERVED** MODIS event-max water; JRC permanent-water band separate; optical/cloud | **CC BY-NC 4.0** (not product-safe) | Metadata **RESEARCH-ONLY**; rasters **not ingested** | Dated map at t0+H: **UNSUPPORTED**. Optional separate event-max task (below). |
| DFO Bangladesh catalog | none | **INVENTORY** (news/gov/RS). Polygon ≠ inundation. | Public listing | **READY** | Event discovery only |

If Track B rasters are ever acquired: **keep native resolution**. Never upsample 250–500 m labels to 20 m Equi7 or to the 64×64 GFM working grid and call that GFM ground truth.

Geographic coverage of Track B would be national Bangladesh (and GFD watersheds), not the eight GFM AOI tensors. Event independence remains the 45-day rule. DFO/GFD already clustered in `multisource.py`.

Feature availability for historical events: rain lattice does not cover pre-2016-06-01; DEM/river lattices exist for the eight AOIs only and do not turn a national DFO polygon into a GFM cube. An event may be EVENT-ELIGIBLE in the registry without being CUBE-ELIGIBLE.

### Track C — cross-resolution research framework (not a model)

Track C is an **experiment protocol** over Track A and Track B. It is not a third mixed label, not a U-Net, and not an API.

It exists to answer: *can information from a coarse historical observation family improve prediction of the GFM working-grid target without leakage, upsampling fraud, or event-identity memorization?*

**MULTI-RESOLUTION MODEL: NOT YET JUSTIFIED.** Track B rasters are absent; source pairs are C/D not A; event-max and 8-day composites leak if misused as 192 h maps; n = 15 is too small to separate transfer from memorizing episode identity; GFD is NC.

---

## 3. What “forecasting” means

A historical flood map is an **observation**. It is not automatically a forecast target.

### Track A (SUPPORTED)

| Field | Value |
| --- | --- |
| t0 | `issue_time` |
| input_start | rain cube hours strictly before t0 (t−72 h … t0 exclusive of future) |
| input_end | t0 |
| target_time | t0 + 192 h = GFM `valid_at` |
| target_window | that GFM scene slot |

No FORECAST-kind rain in the lookback. Persistence `valid_at < t0`. Gate D already encodes this.

| Horizon | Classification |
| --- | --- |
| 192 h | **SUPPORTED** |
| 6 / 12 / 24 / 48 / 72 h | **UNSUPPORTED** |

### Track B — Giezendanner 8-day (WEAKLY SUPPORTED, if acquired)

| Field | Required rule |
| --- | --- |
| t0 | **Before** the 8-day composite start |
| target_time | the **next** 8-day composite |
| target_window | that 8-day period |

If t0 lies inside the composite, observations after t0 enter the label → **leakage** → mark UNSUPPORTED or redesign.

| Horizon | Classification |
| --- | --- |
| ~8-day next composite, t0 before start | **WEAKLY SUPPORTED** |
| 6 / 12 / 24 / 48 / 72 h | **UNSUPPORTED** |
| 192 h GFM slot | **UNSUPPORTED** (different sensor, derived fraction, different grid) |

### Track B — GFD event-max (UNSUPPORTED as a dated map forecast)

The GFD `flooded` band is the **maximum** water during the entire DFO date range (often weeks to months). Using it as “flood state at t0 + H” includes observations after t0.

Honest alternative (separate research task, own card, NC license): given pre-event features, predict **event-maximum inundation** (binary or fraction) at native 250 m. That is **not** Target A and must never share the GFM metric table.

| Horizon | Classification |
| --- | --- |
| Dated 192 h / daily map | **UNSUPPORTED** |
| Event-maximum extent (own task) | **WEAKLY SUPPORTED** only if t0 is strictly before `event_start` |
| 6–72 h | **UNSUPPORTED** |

### Track B — DFO catalog

No spatial target. Not a forecast benchmark.

---

## 4. Temporal causality

| Benchmark | Leakage risk | Redesign if needed |
| --- | --- | --- |
| Track A | Low if rain kind and persistence gates hold | Already enforced |
| Track B 8-day | High if t0 ∈ composite window | Force t0 < composite_start or drop the sample |
| Track B event-max | Structural: label aggregates the whole event | Do not use as t0+H map; use event-max task with t0 < event_start, or drop |

No target information may enter the feature window. Weekly / event-max datasets are the main leakage source. If leakage cannot be avoided, the task is not a forecast.

---

## 5. Cross-resolution learning options

Evaluate all; adopt none as a model in this phase.

| Option | Description | Verdict now |
| --- | --- | --- |
| A | Separate models at native resolution | **Required first** |
| B | Shared encoder + resolution-specific heads | Premature |
| C | Coarse-to-fine | Premature; upsampling artifacts |
| D | Multi-scale spatial representations | Premature |
| E | Pretrain on coarse history, fine-tune on GFM | Only after Track A/B baselines; freeze GFM **test** events out of pretrain |
| F | Multi-resolution auxiliary supervision | Only if a coarse label exists on the **same** event and is scored only on the coarse native grid |
| G | Teacher–student / distillation | Premature |
| H | Multi-scale outputs, each evaluated only at the resolution of its ground truth | The only acceptable **evaluation** rule if E/F are ever tried |

A neural architecture is not automatically justified. Pixel GBDT remains the Track A bar if/when training is separately approved.

### Can 500 m history improve GFM working-grid prediction?

Not established. Required analysis before claiming yes:

- **Label semantics:** OBSERVED SAR ensemble vs DERIVED 8-day fraction vs OBSERVED optical event-max.
- **Spatial scale:** GFM native 20 m vs working ~0.5–1 km vs 250 m vs 500 m. Working GFM cell size is *closer* to 500 m than 20 m, but **semantics still differ**.
- **Temporal mismatch:** 192 h scene vs 8-day composite vs event-max over weeks.
- **Sensor:** C-band SAR vs MODIS optical vs CNN–LSTM fusion.
- **Event distribution:** GFM 2015–2024 AOI tiles vs 2000–2014 national DFO/GFD polygons; GFM winters are residual water.
- **Geography / mechanism:** haor vs central floodplain vs cyclone/compound.
- **Domain shift + license:** GFD NC; Giezendanner DERIVED + FABDEM NC-SA inputs.

Experiments 4–5 (below) answer this **without** putting the same event in coarse pretrain and GFM test.

---

## 6. Dataset architectures (do not force a single dataset)

| Architecture | Description | Role |
| --- | --- | --- |
| 1 | Completely separate benchmark datasets | Minimum isolation |
| 2 | Shared event registry + separate labels | **Recommended start** |
| 3 | Shared feature cube + resolution-specific targets | Only if the same AOI grid is scientifically valid for both labels (it is not for national 250/500 m maps) |
| 4 | Full multi-resolution learning | Not justified |

**Safest starting architecture: 2.** Canonical `event_id` already links GFM `evt:2017-07-31` = DFO 4508 = GFD `dfo:4508` as one real-world flood with independent observation families. Labels stay in separate stores.

---

## 7. Canonical real-world event registry

Already implemented as `phase6.5-multisource-event-v1`. Do not imply identical pixels.

```
event_id  (45-day meteorological episode)
  ├── observation_family A: GFM scene set (20 m / 64×64 working)
  ├── observation_family B: Giezendanner 8-day fraction (500 m) — not acquired
  ├── observation_family C: GFD event-max (250 m) — metadata only
  └── observation_family D: DFO catalog row(s) — no pixels
```

Required fields (already present): `event_id`, `source_event_id`, `event_start/peak/end`, `observation_family`, `label_kind`, `spatial_resolution_m`, `license`, `gfm_available`, `cube_eligible`, `event_eligible`, `matched_gfm_event_id`, `provenance`.

One real-world event. Multiple observation families. **Not** identical labels.

---

## 8. Event-count re-evaluation

| Counter | N | May be used as |
| --- | ---: | --- |
| TOTAL_REAL_WORLD_EVENTS | **36** | discovery / planning |
| GFM_HIGH_RES_EVENTS | **16** | GFM observation family (indexed) |
| HIGH_RES_CUBE_ELIGIBLE_EVENTS | **15** | official Gate B / Track A |
| FORECAST_CUBE_ELIGIBLE_EVENTS | **15** | Track A 192 h only |
| HISTORICAL_COARSE_EVENTS | **21** unique IDs; **0** with rasters | Track B *potential* |
| CROSS-SOURCE_MATCHED_EVENTS | GFD∩GFM **3**; DFO∩GFM **10** | registry links, not extra training labels |

Official Gate B remains **FAIL**. Research “36 / RESEARCH-USEFUL” describes discovery coverage, not N_train.

---

## 9. Benchmark matrix

| Benchmark | Source | Resolution | Events | Forecastable? | Target | Purpose | Availability |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| Track A | GFM | 20 m native / ~0.5–1 km working | 15 | 192 h **SUPPORTED** | binary occurrence | primary spatial forecast science | **READY** (INSUFFICIENT_DATA for VALIDATED) |
| Track B-frac | Giezendanner | 500 m 8-day | 0 acquired | 8-day **WEAKLY** if causal | fraction | historical climatology / optional eval | **UNAVAILABLE** |
| Track B-max | GFD | 250 m event-max | 0 rasters | dated map **UNSUPPORTED** | event-max binary | NC research extent climatology | **RESEARCH-ONLY** metadata |
| Track B-cat | DFO | none | 31 accepted clusters | n/a | inventory | event discovery | **READY** |
| Track C | A + B | native eval only | n/a | only if A and B causal | never mixed pixels | transfer tests | **PARTIAL** (protocol only) |

---

## 10. Baselines per track

### Track A

Existing `src/floodlens/ml/spatial/baselines.py`: persistence, climatology, rain_threshold, logistic, pixel GBDT (bar), RF if justified, conv_smooth as a weak spatial smoother.

**Do not run until a separate explicit training/evaluation approval.** With 15 events, GBDT vs persistence is descriptive, not a Gate G pass (≥10 train events is necessary but 15 total with 7 train is still underpowered).

### Track B (only if rasters exist)

Persistence of the previous 8-day composite (causal), seasonal climatology, rainfall threshold, event-history (prior-year same pentad). No CNN/U-Net.

### Track C

No deep baseline until Experiments 1–2 exist. A transformer or U-Net is not a Track C prerequisite.

---

## 11. Metrics

Unknown pixels are never scored as dry.

**Track A (binary maps, imbalanced flood class):**

| Metric | Role |
| --- | --- |
| **IoU** (valid pixels only) | **PRIMARY** — matches inundation overlap and prior spatial eval |
| Dice / F1 | Secondary overlap |
| Precision / recall | Error type |
| AUPRC | Secondary ranking under imbalance |
| Brier | Probability quality if a probabilistic head exists |
| Calibration (reliability) | Required if probabilities are reported |
| AUROC | Do **not** headline (easy to look good with rare flood) |

**Track B fractional 8-day:**

| Metric | Role |
| --- | --- |
| **MAE** | **PRIMARY** |
| RMSE | Secondary |
| Correlation | Spatial pattern, not magnitude |
| Calibration | If probabilistic |

**Track B event-max binary (native 250 m only):** IoU at **250 m**. Never after upsampling to 20 m.

Do not reuse Phase 5.5 conformal coverage ≈0.69 on a new track. Recalibrate independently.

---

## 12. Geographic generalization

Regions in play: Dhaka subtiles, Sunamganj, Sylhet, Netrokona, Kishoreganj. Jamuna / Padma / Meghna / coastal appear in DFO/GFD catalogs, **not** in the GFM 64×64 cube.

| Test | Definition |
| --- | --- |
| In-region | Train and test tiles from the same `city_id` / AOI, **different events** |
| Out-of-region | Geographic holdout: sunamganj, sylhet, netrokona (`GEO_TEST_AOIS`) held out of geographic-train |

One or two Sylhet GFM scenes **do not** establish Sylhet generalization. Extra named regions in DFO do not add AOI tensors.

Report metrics **per AOI** and do not average away Dhaka-NE unknown or Sylhet absence.

---

## 13. Temporal generalization

Random event holdout is **not** the sole benchmark.

| Design | Role |
| --- | --- |
| Historical holdout years | Train later, test earlier (optional stress) |
| **Future-year holdout** | **PRIMARY** — existing split: test 2022 named holdout + 2023–2024 |
| Unseen-event holdout | Implied by event-level splits (already required) |

Pixel-i.i.d. remains forbidden.

---

## 14. Flood-mechanism generalization

Mechanisms tagged today: monsoon riverine / haor monsoon inundation, haor premonsoon flash, winter residual, tropical cyclone / compound (DFO).

**Do not combine them into a single headline number.** Maintain:

- pooled Track A IoU **and**
- stratified IoU by mechanism.

Winter GFM clusters (near-zero flood pixels) may be excluded from a *quality-filtered* diagnostic table; they remain in the official 15 until a separate inventory revision is approved. Cyclone/compound stays a **separate eval stratum**, not mixed into riverine claims.

---

## 15. Uncertainty

| Track | Design | Do not |
| --- | --- | --- |
| A | Recalibrate on Track A val events only. Conformal **or** ensemble **or** omit. If coverage cannot beat a documented null, report UNCALIBRATED. | Carry 0.69 coverage into this benchmark |
| B | Independent calibration on coarse val composites / event-max | Share conformal scores with Track A |
| C | If transfer is tried, recalibrate **after** transfer on GFM val | Assume pretrain improves calibration |

---

## 16. Physics comparability

**Physics vs spatial AI = NOT COMPARABLE** (Gate J FAIL) until all of the following match:

- same AOI
- same grid
- same initial state
- same forcing
- same target time
- same target definition
- same flood threshold

A future protocol may be written against the 64×64 GFM working grid and 192 h slot. **Do not implement it in this phase.** Do not compare SWE depth fields to GFM occurrence or to 250 m event-max.

---

## 17. Production vs research status

| Track | Status now |
| --- | --- |
| Track A | **INSUFFICIENT_DATA** and **NOT_VALIDATED** |
| Track B-frac | **UNAVAILABLE** |
| Track B-max | **RESEARCH-ONLY** (metadata; NC) |
| Track B-cat | inventory only, not a model track |
| Track C | **EXPERIMENTAL** (protocol) |
| `POST /api/v1/forecast/ai-spatial` | **UNAVAILABLE** until Gate 2 / catalog VALIDATED |
| `POST /api/v1/forecast/ai` | AOI GBDT **VALIDATED** (unchanged; not spatial maps) |

Vocabulary for later: PRODUCTION-CAPABLE, RESEARCH-VALIDATED, EXPERIMENTAL, NOT_VALIDATED, INSUFFICIENT_DATA, UNAVAILABLE. Do not invent PRODUCTION-CAPABLE for spatial maps in this document.

---

## 18. Data storage architecture (future)

Do not duplicate large rasters. Do not create `upsampled_20m/` as truth.

```
application/data/ml/spatial/
  event_inventory/                 # canonical registry (exists)
  gfm/processed_v2/                # Track A (exists, gitignored tensors)
  historical/                      # Track B, empty until legal acquire
    giezendanner/native_500m/
    gfd/native_250m/
    labels_500m/                   # never labeled as GFM
    labels_250m/
```

Shared metadata on every label artifact: `event_id`, `observation_family`, `source`, `source_event_id`, `native_resolution_m`, `label_kind`, `license`, `processing_version`, checksum.

Resolution-specific tensors. Common event registry. No unified training HDF5.

---

## 19. API design impact (not implemented)

Future responses for spatial routes SHOULD be able to carry:

| Field | Purpose |
| --- | --- |
| `benchmark` | `track_a_gfm` / `track_b_frac` / `track_b_max` |
| `resolution_m` | native observation or working cell size, explicitly named |
| `observation_family` | A / B / C / D |
| `target_horizon` | hours; refuse 6–72 for spatial |
| `model_status` | NOT_VALIDATED / UNAVAILABLE / … |
| `uncertainty_status` | UNCALIBRATED / omitted / calibrated-on-track |

`POST /api/v1/forecast/ai` stays the AOI GBDT scalar product. `POST /api/v1/forecast/ai-spatial` stays fail-closed UNAVAILABLE (`inference.py` / `registry_spatial.py`). Do not imply that a coarse historical map is the spatial product.

---

## 20. Frontend impact (not implemented)

If maps are ever shown:

- observed resolution ≠ forecast resolution unless identical
- source + observation family + native metres visible
- historical 250/500 m **must not** use the same legend/scale as GFM working maps
- persistent **NOT_VALIDATED** / **UNAVAILABLE** copy for spatial AI
- unknown 255 not rendered as dry land

---

## 21. Experiment matrix (later phases; not this document’s implementation)

No training in Phase 6.6.

### Experiment 1 — Track A baseline (requires separate approval)

- **Inputs:** existing v2.1 cube features < t0
- **Target:** GFM binary 64×64 at t0+192 h
- **Split:** frozen event 7 / 5 / 3; no pixel split
- **Geography:** report per AOI; geo-holdout as secondary
- **Metrics:** IoU primary (valid pixels)
- **Success:** honest numbers + underpower acknowledged
- **Failure:** IoU indistinguishable from persistence at event-mean noise — expected, still informative

### Experiment 2 — Track B baseline

- **Blocked** until rasters + causal t0 rule + license card
- Native grid only

### Experiment 3 — Track A vs Track B error characteristics

- Only on **matched** events with both maps (currently ≤3 GFD∩GFM with rasters missing)
- Too few for transfer claims; qualitative only if data appear

### Experiment 4 — Cross-resolution pretraining feasibility

- Coarse pretrain events **disjoint** from GFM test years (and from GFM val if used for model selection)
- Success: task is causal; no GFM test event in pretrain
- Failure: cannot build a causal Track B task

### Experiment 5 — Cross-resolution transfer

- Freeze Track A test events
- ΔIoU vs Experiment 1 on geo **and** temporal holdout
- Success: see §22
- Failure: see §23

### Experiment 6 — Resolution-aware model

- Only if Experiment 5 succeeds on ≥2 holdout years and is not explained by extra pixels of the **same** events

### Experiment 7 — Hybrid physics + AI

- Only after Gate J alignment protocol exists
- Not comparable today

---

## 22. Success criteria for Track C

All of the following, not a subset:

1. No target leakage (causal t0).
2. Evaluation at **native** resolution of each label.
3. Improvement over **separate-native** baselines (Experiment 1, and 2 if it exists).
4. Improvement reproduced across **multiple** held-out events **and** at least two holdout years.
5. Geographic holdout does not erase the gain.
6. Temporal holdout does not erase the gain.
7. Calibration not worse than Track A-only (or both UNCALIBRATED, honestly).
8. Gain is **not** solely extra training pixels of events already in Track A.

No numeric IoU delta is declared here. With n = 15, event-mean IoU variance is the first quantity Experiment 1 must report.

---

## 23. Failure conditions for Track C

Any of these is a **valid scientific outcome** and stops promotion to a unified model:

- Labels irreconcilable (already the 6.5C default for pixel merge).
- Resolution gap produces systematic fine-scale artifacts.
- Coarse pretrain gives no transfer benefit.
- Gains vanish on geographic or temporal holdout.
- Uncertainty becomes miscalibrated.
- Apparent gain from duplicating the same events at two resolutions.
- Multi-resolution model cannot beat native-resolution Track A baselines.

---

## 24. Recommended final architecture

**B. Separate benchmarks + shared event registry.**

Not A (registry already exists and is the right join key). Not C (transfer not yet testable). Not D (unified model unjustified). Not E as a total stop: Track A data are real and diagnostically usable; Track B acquisition stays blocked until access and causality pass.

---

## 25. Scientific gates (this design; official A–J unchanged)

| Gate | Rule |
| --- | --- |
| Official B | Still **20 GFM** independent events. 36 registry events do not pass it. |
| Official F | Still ≥3 valid GFM AOIs. Extra DFO country names do not pass it. |
| Official D | Features < t0. Event-max/8-day must obey §3–4 or they are not forecast tasks. |
| Official J | NOT COMPARABLE until alignment protocol. |
| Track B entry | Legal access + native store + causal horizon + own data card. |
| Track C entry | Experiments 1–2 (or 1 + documented B-unavailable) before 4–6. |
| Spatial API | UNAVAILABLE until catalog VALIDATED (Gate 2). |

---

## 26. Risks

- Treating 36 as N_train.
- Calling Giezendanner OBSERVED.
- Putting GFD NC rasters on a product path.
- 8-day or event-max leakage into “192 h forecast.”
- Calling 64×64 GFM “20 m ground truth.”
- Upsampling coarse labels to the GFM grid.
- Sylhet n = 2 as geographic proof.
- Running GBDT on 15 events and marking VALIDATED.
- Mixing physics depth with GFM occurrence.
- Rendering coarse historical maps as equivalent to GFM in the UI.

---

## 27. What this phase implements

This file only.

No source-code changes, no downloads, no training, no API enablement, no solver edits.

**Next phase (after separate approval):** Experiment 1 Track A **diagnostic** baselines on the frozen 15-event split — still not catalog VALIDATED, still not `ai-spatial`, still not Gate B pass. Track B importers only if CyVerse/GFD access and licenses are explicitly accepted as research-only.

---

## Final decision

RECOMMENDED TRACK:
B (separate benchmarks + shared event registry)

PRIMARY BENCHMARK:
Track A — GFM OBSERVED 192 h occurrence on the 64×64 working grid (native 20 m Equi7 resampled; 15 cube-eligible events)

SECONDARY BENCHMARK:
Track B — historical coarse observations at native 250 m (GFD event-max, NC, rasters not ingested) or 500 m (Giezendanner DERIVED 8-day, UNAVAILABLE); DFO catalog for discovery only

MULTI-RESOLUTION MODEL:
NOT YET JUSTIFIED

CURRENT HIGH-RES EVENTS:
15

CURRENT TOTAL REAL-WORLD EVENTS:
36

MODEL TRAINING:
NOT AUTHORIZED

SPATIAL AI:
NOT_VALIDATED

SOLVER MODIFIED:
NO

NEXT PHASE:
Phase 6.7 — Track A diagnostic baselines on the frozen 15-event split (separate explicit approval; no VALIDATED promotion; no spatial API; optional Track B acquisition only if access and causal 8-day task are accepted as research-only)

END.
