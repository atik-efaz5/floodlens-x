# Phase 6.5 — Spatial dataset expansion and forecasting formulation audit

**Status:** PLAN DOCUMENT. Not an implementation. Not a VALIDATED claim. Not a training run.

**Decision: E — Reformulate + expand dataset.**

Keep **Target A** (binary GFM occurrence at t0+192 h). Reformulate event definition, rainfall cube, DEM/river spatiality, unknown/permanent-water protocol, and Gates A–J. Expand GFM years and Equi7 tiles until independent meteorological events meet the floor. Stop CNN training and catalog VALIDATED until those gates pass.

This document does not modify `src/floodlens/numerical/**`, does not invent 6–72 h labels, and does not promote spatial AI.

---

## 1. Executive summary

Phase 5.5 measured a leakage-safe proof-of-concept, not a product: **7 independent 45-day events**, two regions (Dhaka, Sunamganj), ~60% unknown pixels, broadcast rain and Q, no DEM, pixel GBDT IoU 0.231 beating persistence 0.128 and Tiny U-Net 0.026, geographic holdout IoU 0, conformal coverage 0.69 vs a 0.80 target. Public catalog stayed **NOT_TRAINED**. Physics vs spatial AI stayed **COMPARISON NOT YET COMPARABLE**.

Phase 6 rebuilt the **formulation** (64×64 tensors, channel audit, Open-Meteo lattice, elevation lattice, river distance, Gates 0/1/2, GBDT-first). It did not train a new U-Net. `phase6_eval.json` records **0 v2 samples** because `gfm/processed_v2/` was never built. Gate 0 failed. That failure is honest.

The scientific bottleneck is **independent events and spatial forcing**, not architecture. A Transformer will not invent SAR coverage or 24 h GFM maps.

**Primary target remains GFM OBSERVED binary occurrence at t0+192 h.** Product 6/12/24/48/72 h stay UNAVAILABLE. Expand GFM (years + AOI-valid tiles), add real spatial rain/DEM/rivers, enforce hydrologic event IDs, keep pixel GBDT as the bar.

**NO IMPLEMENTATION IN THIS PHASE.** Later agent-mode work starts at §30.

---

## 2. Current-state audit

### 2.1 Dependency map

| Component | Path | Purpose | Limitations | Verdict |
| --- | --- | --- | --- | --- |
| Labels | `src/floodlens/ml/spatial/labels.py` | τ=0.25; 255 never dry | Permanent water not a separate class | **Reuse; do not weaken** |
| GFM STAC | `src/floodlens/ml/spatial/acquire_gfm.py` | Public STAC + local index | Tile `E039N021T3` only; neighbor tiles rejected; 200 MB cap; STAC geometry is the tile not the swath | **Reuse; expand tiles/years** |
| Equi7 | `src/floodlens/ml/spatial/equi7.py` | Lon/lat → product-tile pixels | ~1 km spherical aeqd error | **Untouched** |
| v1 builder | `builder.build_spatial_samples` | 32×32, 3 cities, point rain | Broadcast features | **Keep for Phase 5.5 checkpoint** |
| v2 builder | `builder.build_spatial_samples_v2` | 64×64, 8 AOIs | Needs `processed_v2` + caches | **Reuse after acquire** |
| AOIs | `src/floodlens/ml/spatial/aois_v2.py` | Haor + floodplain + Dhaka subtiles | Not the product catalog | **Reuse** |
| Product cities | `city_data.py` | Dhaka, Sunamganj, Sylhet | Exactly three | **Untouched** |
| Rain lattice | `precip_lattice.py` | 3×3 Open-Meteo archive IDW | ERA5-Land ~11 km; cache often missing | **Reuse then cube/IMERG** |
| Point rain | `real_dataset.py`, `ingest.py` | Hourly AOI point | TEMPORAL-ONLY | **Reuse as fallback** |
| DEM plan | `dem_plan.py` | Fail-closed `FLOODLENS_DEM_PATH` | Unset in this extract | **Reuse** |
| Elevation lattice | `elevation_lattice.py` | Open-Meteo 17×17 | Not GLO-30 microtopography | **Reuse until GLO-30 window** |
| Rivers | `river_features.py` | HydroRIVERS or OSM distance | OSM is geometry substitute | **Reuse** |
| Channel audit | `channel_audit.py` | SPATIAL vs TEMPORAL-ONLY vs CONSTANT | CNN refused if &lt;4 spatial | **Reuse** |
| Events | `events.py` | 45-day `event_id` | 7 events &lt; 20 | **Reuse; add basin_id** |
| Splits / leakage | `splits.py`, `leakage.py` | Temporal + geographic; no pixel-i.i.d. | Sylhet often unlabeled | **Reuse** |
| Gates 0/1/2 | `gates.py` | Fail-closed train/VALIDATE | Empty v2 → Gate 0 fail | **Keep; map to A–J** |
| Baselines | `baselines.py` | Persistence, rain, logistic, GBDT, RF bag, conv-smooth | GBDT is the bar | **Reuse** |
| Train | `train.py` | Baselines only; no U-Net | `mark_spatial_trained` not VALIDATED | **Reuse** |
| Phase 5.5 eval | `phase55.py` | Honest U-Net/GBDT/uncertainty report | Never VALIDATED | **Reference** |
| Phase 6 eval | `phase6.py` | Audit + gates; never `mark_spatial_validated` | 0 v2 samples | **Reuse** |
| U-Net | `unet.py` | Tiny numpy CNN | Broadcast channels; not Phase 6 primary | **Untouched until Gate 1** |
| Inference | `inference.py` | Maps only if VALIDATED + unet | Always UNAVAILABLE today | **Untouched (fail-closed)** |
| Spatial registry | `registry_spatial.py` | Separate from AOI GBDT | Internal TRAINED, public NOT_TRAINED | **Untouched** |
| Compare | `ml/compare.py` | NOT COMPARABLE | Must stay | **Untouched** |
| Solver | `src/floodlens/numerical/**` | Validated SWE kernel | Not a 192 h inundation model | **Untouched** |
| Synthetic v2 | `make_synthetic_sample_v2` | Pipeline tests | `label_kind=OBSERVED` + `synthetic=True` | **Refactor later** |

### 2.2 Constants

`GRID_SIZE=32`, `GRID_SIZE_V2=64`, `HORIZON_HOURS=192`, `EVENT_GAP_DAYS=45`, `GATE0_MIN_EVENTS=20`, `GATE0_MIN_REGIONS=3`, `GATE1_MIN_TRAIN_EVENTS=10`, `MIN_SPATIAL_CHANNELS=4`, `FLOOD_FRACTION_TAU=0.25`, `UNKNOWN=255`, `TILE_ID=E039N021T3`, `GEO_TEST_AOIS={sunamganj, sylhet, netrokona}`.

AOI_IDS_V2: sunamganj, sylhet, kishoreganj, netrokona, dhaka_sw, dhaka_se, dhaka_nw, dhaka_ne. Product catalog remains three cities.

### 2.3 Provenance / status (do not weaken)

Label kinds: OBSERVED (GFM), DERIVED (Giezendanner, unused), MODELLED (GloFAS Q / AOI GBDT). API `data_status`: REAL, SIMULATED, DEMO, STALE, UNAVAILABLE, PARTIAL. Spatial public status is VALIDATED only if the spatial registry says VALIDATED; TRAINED is hidden. `POST /api/v1/forecast/ai-spatial` is UNAVAILABLE until then.

---

## 3. Why the current spatial dataset is insufficient

1. **Seven independent events.** 39 unique days and 63 city-tiles are not 39 floods. Train is two 2018 episodes. Event-level mean/std is noise around 0.
2. **Geography.** Dhaka + Sunamganj. Sylhet valid fraction &lt; 5% (unknown, not dry). Extra AOIs on the same Equi7 tile add spatial diversity, not new monsoons.
3. **~60% unknown.** STAC item geometry is the Equi7 tile, not the SAR swath. Native 255 is nodata/exclusion (orbit gap, layover, exclusion mask). **Not optical cloud.** Masking is correct. Recoding unknown as dry would fabricate dry land.
4. **Horizon vs forcing.** Target is GFM at t0+192 h; rain is 24/72 h antecedent. An 8-day SAR occurrence is weakly tied to yesterday’s point rain.
5. **Rain spatiality.** v1 broadcasts one AOI point. v2 3×3 ERA5-Land is real sampling but ~11 km. Sunamganj (~30 km) may still have ~1–3 distinct rain cells.
6. **No DEM on v1.** Flood location in haor/floodplain is first-order topographic. v2 Open-Meteo elevation lattice is real but not GLO-30 microtopography.
7. **River as scalar Q** until distance-to-river exists. Meghna/Surma geometry is not in the v1 tensor.
8. **Pixels ≠ events.** 32×32×63 correlated cells are not i.i.d. samples. Pixel-i.i.d. splits are forbidden and must stay forbidden.
9. **v2 not materialized.** Gate 0 in `phase6_eval.json` failed on empty `processed_v2` (`independent_events`, `regions`, `spatial_channels`, `dem_present`, `precip_lattice`, `label_observed`). Even after acquire, event count is still expected below 20 on the current local TIFFs.
10. **U-Net failure is secondary.** Six of eight v1 channels were spatially constant. GBDT using i, j and persistence won. Conformal on that predictor is unusable (coverage 0.69, rank corr −0.04), not a root cause of IoU.

---

## 4. Candidate real datasets

Assessed for a Bangladesh 192 h **forecast** task (t0 features → later observed map). Licenses as documented in existing data cards; no fabricated coverage counts.

### 4.1 Satellite flood extent (labels)

**Copernicus GFM `ensemble_flood_extent`.** CEMS/EODC. Public STAC `https://stac.eodc.eu/api/v1` collection GFM. License STAC **proprietary**; Copernicus attribution. Native 20 m Equi7 S1 ensemble. Classes 0/1/255. Horizon: 192 h YES; 6–72 h NO. Already in-repo. **Primary label. Expand.**

**OPERA DSWx-S1 / raw Sentinel-1.** Same revisit class as GFM. Do not train a second S1 classifier to duplicate GFM in v2.

**VIIRS / MODIS NRT flood.** Optical, daily-ish, cloud-heavy. Could tag 24 h on clear pixels; unknown rate would explode. Not the first target.

**Global Flood Database (MODIS).** ~913 events, 2000–2018, 250 m event-max, CC BY-NC. Not a t0→t+h forecast label. Optional climatology later; not product-safe.

**WorldFloods / Sen1Floods11.** Same-time mapping, often NC, huge. Not a forecast task for these AOIs.

**EMSR.** Phase 4 found 0 Bangladesh rows in the public list. Do not wait.

**Giezendanner Bangladesh inundation.** CyVerse DOI 10.25739/2edm-jh03. DERIVED 8-day ~500 m, 2001–2022, most of BD. Probe redirected/blocked; **not downloaded**. Optional Track D later; never mix with GFM in one metric table; never call OBSERVED.

**GloFAS Rapid Flood Mapping.** MODELLED ~90 m, 15-day RP inundation lookup. Phase 7 comparison candidate, not training labels.

### 4.2 Precipitation

**Open-Meteo archive / ERA5-Land.** ~11 km hourly, CC BY 4.0, already in stack. First source for a lattice cube.

**Open-Meteo Historical Forecast / IFS.** Lead-aware; ops / 2022+ overlap. Keep kind FORECAST separate from REANALYSIS.

**NASA IMERG V07.** 0.1°, 30 min. Upgrade if lattice within-tile variance is still ~0 on Sunamganj. Earthdata.

**CHIRPS.** 0.05° daily, historical only, no forecast.

**Radar.** Sparse BD coverage; out of scope.

### 4.3 Terrain and rivers

**Copernicus GLO-30.** ~30 m. Prefer. Window via `terrain_service.get_window` + `FLOODLENS_DEM_PATH`. Never a national mosaic.

**SRTM 1-arc-second.** Fallback.

**FABDEM.** CC BY-NC-SA — **not for a product**.

**HydroRIVERS v1.** Free scientific/commercial. Distance + mask. `FLOODLENS_HYDRORIVERS_PATH`.

**OSM waterways.** ODbL. Substitute until HydroRIVERS clip exists.

**GloFAS Q.** MODELLED cell discharge, 7-day lookback. TEMPORAL-ONLY scalar. Acceptable if river distance is present.

**BWDB gauges.** Only if a public licensed series is actually obtained; otherwise UNAVAILABLE. Do not fabricate.

### 4.4 Other

Land cover / soil moisture: optional later features with license cards. Historical administrative flood lists: event discovery metadata, not pixel labels. Satellite altimetry: sparse; not a 64×64 label.

---

## 5. Dataset ranking matrix

Headline **labels** for the 192 h forecast task (best first):

1. GFM ensemble extent — OBSERVED, 20 m, public STAC, 192 h compatible. **Expand.**
2. OPERA DSWx-S1 / raw S1 — same revisit; do not duplicate GFM.
3. Giezendanner — DERIVED, 8-day, BD-wide; climatology/permanent-water later, not headline.
4. VIIRS/MODIS NRT — weak 24 h, clouds.
5. GFD / WorldFloods / EMSR — wrong task, NC, or no BD rows.
6. GloFAS Rapid Flood Mapping — MODELLED comparison, not labels.

Headline **features**:

1. Open-Meteo ERA5-Land lattice (then IMERG if variance ~0)
2. GLO-30 windows (not synthetic, not FABDEM)
3. HydroRIVERS distance + mask (OSM until clip exists)
4. GloFAS Q 7-day scalar
5. Lagged GFM persistence (previous completed scene only)

---

## 6. Recommended dataset strategy

**OPTION E:** Keep GFM as the OBSERVED 192 h occurrence label. Reformulate events, rain cube, DEM/rivers, unknown protocol, and gates. Expand GFM until independent events meet the floor.

How to expand (later implementation, not this document-writing phase):

- Index **all** AOI-valid local `*E039N021T3.tif` at 64×64 (`index_local_v2`) for AOI_IDS_V2.
- Revisit neighbor tiles (e.g. `E039N024T3`) with an **AOI-valid ≥5%** filter, not a STAC-hit filter. Phase 5 rejected the neighbor because STAC hits were empty swaths; some haor/Sylhet coverage may still exist.
- Add years that currently have raw files but failed the 21-day STAC subsample (already recovered for v1 via `index_local_raw`).
- Do not add 2-day orbit twins as extra events.
- Product catalog stays three cities; extra AOIs are training/eval only.
- Run `scripts/phase6_acquire.py` then `scripts/phase6_evaluate.py` so Gate 0 is measured on real v2 tensors.
- If after expansion independent events remain &lt;20: **stop CNN**. Report inventory. Do not VALIDATED.

Do not mix Giezendanner or GFD into the headline metric table. Multi-source **features** are in scope; multi-source **labels** are not.

---

## 7. Flood event definition

An event is a **meteorological/hydrological pulse**, not a GeoTIFF.

| Field | Definition |
| --- | --- |
| Start | First GFM scene (or documented gauge rise) after ≥45 days gap in the basin cluster |
| Peak | Scene with maximum valid flood fraction in the cluster (metadata; not a second event) |
| End | Last scene before the next 45-day gap |
| Geographic footprint | Union of AOIs with valid_frac ≥ 5% in that cluster |
| Event ID | Existing `evt:{cluster_start_date}` in `events.py` |
| Basin ID | New metadata so Dhaka + Sunamganj + Kishoreganj of the same monsoon stay **one** event |
| Trigger | 72 h lattice rain and/or GloFAS Q anomaly in lookback — metadata, not a second label |

Two city tiles on the same flood = one event. Orbit twins two days apart = one event. Intra-monsoon 12-day revisits = one event. That 45-day rule is conservative on purpose: loosening it would inflate “events” without adding independent weather.

---

## 8. Event deduplication

Prevent leakage from:

- Adjacent dates of the same flood
- Same-event satellite scenes
- Overlapping Dhaka subtiles
- Overlapping temporal windows
- Nearby districts in the same monsoon system
- Pixel-i.i.d. splits

Enforcement already partly exists (`assign_event_ids`, `same_event_in_train_and_test`, `forbid_pixel_iid`, lagged persistence). Add basin-level `event_id` so subtiles cannot split one pulse across train and test.

---

## 9. Spatial / temporal split design

| Split | Rule | Role |
| --- | --- | --- |
| Event holdout | No `event_id` in two of {train, val, test} | **Primary scientific test** |
| Temporal | Train issue &lt; 2019-01-01; val &lt; 2022-01-01; test 2022+ and named NE holdout 2022-05-09…2022-06-21 | Chronology |
| Geographic | `GEO_TEST_AOIS` = sunamganj, sylhet, netrokona unseen in geographic-train | Second table; v1 IoU was 0 — must not collapse |

Report event-level mean / median / std IoU (and AUPRC) plus worst event. Do not headline pixel count or accuracy.

---

## 10. Recommended target formulation

Evaluated formulations:

| ID | Formulation | Labels exist? | Verdict |
| --- | --- | --- | --- |
| A | Binary flood occurrence per pixel | GFM 0/1/255 | **PRIMARY** |
| B | Probability of occurrence | Model output, not a label | Secondary as **output** |
| C | Flood depth per pixel | No observed depth | No |
| D | Depth conditional on flood | No | No |
| E | Multi-task probability + depth | No depth | No |
| F | Future extent segmentation | Same as A on a grid | Same as A |
| G | t+6…t+72 evolution | No observed maps; do not interpolate GFM | No |

**Primary: A.** Binary GFM occurrence, τ=0.25, unknown=255. Reliably observable, measurable (IoU/Dice/AUPRC), matches the product’s spatial question: where is water at the next S1 scene.

**Secondary: B as model output** (calibrated P(flood)), not a second label source.

Not C–E: no observed depth. Not G: 6/12/24/48/72 h stay UNAVAILABLE until a daily observed map source is acquired (not invented).

192 h is a **scene slot** (issue = valid_at − 192 h), not a claim that yesterday’s rain caused an 8-day SAR map. Extra 48/120 h accumulations are **features only**.

---

## 11. Label protocol

1. Read native GFM uint8: 0 dry, 1 flood, 255 nodata/exclusion.
2. Clip to AOI Equi7 window; drop scene if valid fraction &lt; 5%.
3. Block-reduce to 64×64; coarse cell is flood iff **valid** flood fraction ≥ τ=0.25.
4. Remaining 255 stays unknown in loss and metrics. Never dry.
5. `valid_at` = GFM scene datetime. `issue_time` = valid_at − 192 h.
6. Features use times **&lt; t0** only. Same-time SAR is the label, not an input.
7. Persistence = previous completed map with valid_at &lt; t0; unknown where previous was 255.
8. τ=0.25 stays unless a **pre-registered** sensitivity (0.15 / 0.35) is reported in a separate table.
9. Optional quality channel: valid_frac. Do not impute Sylhet.

---

## 12. Unknown / cloud / permanent-water handling

GFM is SAR. Unknown is **not** optical cloud. 255 means nodata or exclusion (swath miss, layover, algorithm exclusion, including some permanent-water exclusion in the product).

- Score only finite `y_binary` pixels.
- Do not recode 255 as dry.
- Do not invent a JRC permanent-water mask as the dry class.
- If exclusion already encodes permanent water as 255, leave it unknown.
- Scene drop if valid_frac &lt; 5%.
- Document unknown fraction per scene (`scene_quality_table`).

Pre-event dry state = persistence only. Flood duration cannot be inferred from 8-day snapshots.

---

## 13. Rainfall data strategy

Build a cube **rainfall(x, y, t)** rather than a spatially broadcast scalar whenever scientifically possible.

- Lookback: hourly t−72 h … t0 (issue floor hour).
- Lattice: ≥3×3 lat/lon per AOI; `precip_is_aoi_point=false` only if ≥4 distinct points fall in the AOI.
- Source 1: Open-Meteo archive / ERA5-Land (CC BY 4.0). Kind **REANALYSIS**.
- Derived maps: 24 h and 72 h accumulations (optional 48/120 h) from the cube, not from a second download.
- Completeness: drop sample if cube completeness &lt; 50% (align with existing 80% point-lookback on the scalar path).
- **No future rain in training features** unless the task explicitly uses an NWP forecast as an input, stored as FORECAST, never as OBSERVED/REANALYSIS.
- If within-tile rain variance is still ~0 on Sunamganj after the lattice: **IMERG V07** next (not CHIRPS-first, not fabricated radar).
- Operational serving later must not silently swap ERA5 at t+h for “observed” rain.

---

## 14. DEM strategy

Fail-closed. No synthetic DEM in evaluation.

- Prefer Copernicus GLO-30 window via `FLOODLENS_DEM_PATH` + `terrain_service.get_window` (AOI bounds, never a national mosaic).
- Fallback: Open-Meteo elevation lattice (SRTM/GLO family) already implemented — real samples, coarse.
- SRTM 1-arc-second if GLO-30 unavailable.
- Not FABDEM (NC-SA).
- Features: elevation; slope from local gradient; height above nearest river from the river layer (HAND-like **without** a from-scratch global D8).
- Static per tile. Train-only local z-score; no test fit.
- If DEM missing: `dem_present=false`; Gate C / Gate 0 fail; do not train CNN.

---

## 15. River / hydrology strategy

| Feature | Kind | Obtainable for BD AOIs? |
| --- | --- | --- |
| Distance-to-river | OBSERVED geometry (HydroRIVERS or OSM) | Yes |
| Binary river mask | Derived from distance | Yes |
| GloFAS Q 7-day | MODELLED | Yes (3 proxy cells) |
| Channel width / Strahler order | HydroRIVERS attributes if clip present | Maybe |
| Upstream area | HydroRIVERS if present | Maybe |
| BWDB water level | OBSERVED | Only if a licensed public series is acquired; else UNAVAILABLE |
| Rasterized Q field / GNN | — | Defer until D+mask exist and GBDT is measured |

Do not fabricate discharge or stage. Scalar Q as TEMPORAL-ONLY is acceptable **if** distance-to-river is present.

Flood mechanisms are not equivalent: haor monsoon inundation, central floodplain riverine, urban pluvial, coastal/tidal/compound. One BD floodplain/haor model is defensible **inside** that family. Coastal and flash-flood domains need a later hierarchical split, not a silent global CNN.

---

## 16. Feature-cube design

A channel is **SPATIAL** only if neighboring pixels can meaningfully differ (`channel_audit.py`).

| Channel | Class on v1 | Required for CNN? |
| --- | --- | --- |
| precip 24/72 broadcast | TEMPORAL-ONLY | No — replace with lattice/cube |
| log1p Q | TEMPORAL-ONLY | Optional scalar |
| month sin/cos | TEMPORAL-ONLY | Optional |
| precip_is_aoi_point | CONSTANT (v1 always 1) | Flag only |
| persistence | SPATIAL | Yes |
| persistence_valid | SPATIAL | Yes |
| DEM elev | MISSING on v1 | Yes |
| slope / HAND-like | MISSING | Yes (one of slope/HAND) |
| river_distance | MISSING on v1 | Yes |
| rain lattice/cube | MISSING on v1 | Yes (non-broadcast) |

**Minimum CNN-justifying set:** ≥4 of {persistence, elev, slope or HAND, river distance, non-broadcast rain} with within-tile variance. Refuse CNN otherwise.

Per-sample fields: EVENT_ID, REGION_ID, issue_time, valid_at, horizon_hours=192, bounds, CRS EPSG:4326, resolution_m, dataset_version, label_kind=OBSERVED, rain cube or maps, DEM, slope, river_distance, persistence, Q lookback, masks, provenance.

Alignment: GFM native Equi7 20 m → AOI window → block-reduce 64×64 (mode/fraction; nodata stays unknown). Rain/DEM/rivers sampled on the same EPSG:4326 AOI grid. No hidden upsample of GFM to look sharp. Train-only normalization.

---

## 17. Dataset schema (canonical objects)

Documentation schema for a later implementation. Not created in this phase.

**FloodEvent.** event_id, basin_id, start, peak_scene_id, end, footprint bounds, trigger rain/Q metadata, n_scenes, quality flags.

**FloodScene.** scene_id, datetime, Equi7 tile, href, checksum, valid_frac by AOI, label_kind=OBSERVED, source=GFM.

**SpatialTile.** region_id, bounds, nx, ny, CRS, resolution_m, dataset_version.

**MeteorologicalWindow.** issue_time, lookback hours, source, kind (REANALYSIS|FORECAST), completeness, lattice_n, precip_is_aoi_point.

**HydrologicalWindow.** Q lookback 7 d, proxy city, kind=MODELLED, completeness.

**FloodLabel.** y_flood, y_flood_frac, tau, unknown=255, valid_at, horizon_hours.

**FeatureCube.** arrays or npz keys; no ndarrays in JSON metadata.

**SampleManifest.** sample_id, event_id, region_id, split, paths, hashes.

**SplitAssignment.** event_id → train|val|test; geographic flag.

**EvaluationRecord.** experiment_id, dataset_version, metrics (no accuracy headline), gates.

**ProvenanceRecord.** source, version, timestamp, transform, checksum, data_status, label_kind.

---

## 18. Minimum event counts

Independent **events**, not pixels.

| Tier | Independent events | Notes |
| --- | --- | --- |
| Minimum viable | ≥20 (≥10 train, ≥3 val, ≥5 test); ≥3 AOIs with ≥5% valid GFM | Gate 0 / GBDT freeze |
| Good | 25–40 BD-basin pulses; ≥5 regions | Attempt event-level mean/std |
| Strong | 50–80; geographic holdout not 0 | CNN may be considered if channels pass |
| Research-grade | 100+ and/or extra basins after BD gates | Not required to start expansion |

CNN / U-Net / ConvLSTM / Transformer: not before **Good** and ≥4 spatial channels and GBDT &gt; persistence. Millions of pixels from 7 events remain 7 events.

---

## 19. Baseline ladder

Same event-aware splits. Accuracy is not reported.

| Level | Model | Inputs | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| L0 | Spatial persistence | Lagged GFM | Strong autocorrelation | Misses new inundation |
| L0 | Cell climatology | Month + cell | Seasonality | No event dynamics |
| L1 | Rain threshold map | Lattice 24 h | Interpretable | Ignores terrain/rivers |
| L1 | Logistic | Rain + river distance + DEM | Linear, leak-safe | Weak interactions |
| L2 | Pixel GBDT | i, j, persistence, rain, elev, slope, river, Q, month | **Primary bar**; mixed spatial+scalar | Not a map prior |
| L2 | Pixel RF-style | Same | Variance reduction | Same |
| L2 | 3×3 conv-smooth | Persistence | Morphological baseline (beat U-Net on v1) | No forcing |
| — | Physics SWE burst | Solver seconds | Hydrodynamics | **Not comparable** (Gate J) |
| — | Hybrid | — | Later | After Gate J |

A deep model must beat **pixel GBDT** on event holdout, not beat a missing baseline.

---

## 20. Model promotion gates

Map onto existing Gate 0/1/2.

| Gate | Name | Pass / fail (measurable) |
| --- | --- | --- |
| A | Dataset validity | v2 index exists; OBSERVED labels only in headline; nodata never dry; unknown fraction documented |
| B | Event independence | ≥20 events (45-day + basin_id); no event in two of train/val/test |
| C | Spatial feature sufficiency | ≥4 SPATIAL channels; DEM present not synthetic; lattice rain on majority of tiles |
| D | Temporal causality | Features &lt; t0; persistence valid_at &lt; t0; REANALYSIS vs FORECAST not mixed |
| E | Label quality | valid_frac≥5% per kept scene; τ documented; no mixed OBSERVED/DERIVED table |
| F | Geographic diversity | ≥3 AOIs with ≥5% valid GFM; geographic holdout table exists and IoU not collapsed to 0 |
| G | Baseline competitiveness | Pixel GBDT test IoU &gt; persistence on event holdout; ≥10 train events (Gate 1) |
| H | Uncertainty calibration | Empirical coverage reported; no a priori 80% claim; rank corr &gt; 0.1 or omit/UNCALIBRATED |
| I | Reproducibility | dataset_version, split manifest, experiment ID, seeds, eval script, cards without fake metrics |
| J | Physics comparability | Same AOI, grid, 192 h clock, threshold, forcing **or** explicit NOT COMPARABLE. Today: **fail** (keep statement) |

**VALIDATED** only if A–J and existing Gate 2 pass on pre-registered splits. If A–C fail: expand data; do not tune U-Net.

Ladder: L0 → L1 → L2 (first production-grade candidate = GBDT/RF) → L3 CNN only after G and C → L4 spatiotemporal only if n_events and sequence justify it → L5 hybrid after J → L6 foundation models. No skip.

---

## 21. Uncertainty strategy

Phase 5.5 split conformal: target 0.80, empirical ~0.69, interval width ~1, uncertainty–error rank correlation ~−0.04. **Not confidence.**

Until Gate H: **omit** q10/q90 from the API, or mark UNCALIBRATED. Do not ship current maps as “confidence.”

After ≥3 val events not used in test: split conformal **measured** on test events; pixel reliability diagram; rank correlation must be &gt; 0.1 to call uncertainty informative. Event-level dependence means pixel coverage overstates effective sample size — report event-block coverage too.

---

## 22. Physics-vs-AI comparability protocol

Keep `COMPARISON NOT YET COMPARABLE` in `src/floodlens/ml/compare.py`.

Today: spatial AI = 8-day GFM occurrence on a coarse AOI grid; physics = sub-second SWE burst on ~16×16 cells. Different clock, grid, forcing, and quantity.

A valid later comparison (Phase 7+, not this phase) requires all of:

- Common AOI and **64×64** (or documented shared) grid
- Common target time **192 h** (or both produce depth at the same meteorological hour)
- Common flood threshold on the same mask (unknown excluded)
- Common initial state and forcing **or** an explicit MODELLED product (GloFAS Rapid Flood Mapping ~90 m, 15-day) evaluated on that grid
- Metrics: IoU, Dice, precision, recall, AUPRC, Brier on masked pixels; depth MAE/RMSE only if both produce depth
- No ranking claim from solver-seconds vs meteorological hours

Until then: `comparable_to_physics=false` everywhere.

---

## 23. Data provenance

Chain: SOURCE → DOWNLOAD → RAW ARTIFACT (checksum) → PREPROCESSING → ALIGNED DATA → LABEL → SAMPLE → TRAIN/VAL/TEST → MODEL → PREDICTION → UI.

Each stage keeps source, timestamp, version, transformation, checksum where appropriate, missing-data flags, `label_kind`, and `data_status`. GFM raw TIFFs stay gitignored. JSON holds metadata only (no ndarrays). Simulated/demo rain must not enter training labels. `make_synthetic_sample_v2` should not use `label_kind=OBSERVED` in a later refactor (tests-only hazard).

---

## 24. Licensing

| Dataset | License / terms | Research | Hackathon | Product |
| --- | --- | --- | --- | --- |
| GFM ensemble extent | STAC proprietary; Copernicus attribution; public STAC used here | Yes with attribution | Yes as currently accessed | Check redistribution; raw already gitignored |
| Open-Meteo archive | CC BY 4.0 | Yes | Yes | Yes with attribution |
| GLO-30 | Check Copernicus DEM terms before redistribution | Yes | Yes if terms allow | Window only; no mosaic publish without check |
| HydroRIVERS v1 | Free scientific/commercial | Yes | Yes | Yes |
| OSM waterways | ODbL | Yes | Yes | Share-alike if distributed |
| FABDEM | CC BY-NC-SA | Research-only | Caution | **No** |
| GFD / WorldFloods | Often NC | Research-only | Caution | **No** |
| Giezendanner | Open path documented by authors; DERIVED | Optional later | Do not call OBSERVED | Not as OBSERVED labels |
| IMERG | US government work / Earthdata | Yes with account | Yes | Check TOS |

Do not copy/store data if the license forbids redistribution. Do not claim CC-BY for GFM.

---

## 25. Storage format

Keep the current research stack: GeoTIFF raw (gitignored), compressed `npz` working tensors, `index.json` manifests. GFM assets are already cloud-optimized GeoTIFF on the provider side.

Do **not** migrate to Zarr/NetCDF/Parquet in Phase 6.5. Lattice JSON stays gitignored (`precip_lattice.json`, `elevation_lattice.json`, `rivers_osm.json`, `processed_v2/`). Cap remains well under 8 GB (plan ceiling ~200–500 MB GFM extra).

---

## 26. Reproducibility

- Dataset version string: `phase6.5-gfm-spatial-v2` when a later extract is frozen (v2 code today is `phase6-gfm-spatial-v2`).
- Deterministic preprocess; train-only stats.
- Split manifest of event_id → split.
- Experiment IDs as existing spatial run hashes.
- Seeds for GBDT pixel subsample (already `default_rng(0)`).
- Eval command: `python scripts/phase6_evaluate.py` (never VALIDATED).
- Data card [SPATIAL_FLOOD_DATASET_V2.md](data_cards/SPATIAL_FLOOD_DATASET_V2.md) and model card [SPATIAL_AI_FLOOD_V2.md](model_cards/SPATIAL_AI_FLOOD_V2.md) — **no fake metrics**.
- Same dataset_version + config must reproduce the same experiment.

---

## 27. API impact (future; not this phase)

Do not change routes in this phase.

- `POST /api/v1/forecast/ai-spatial` stays UNAVAILABLE until Gate 2 / VALIDATED.
- `POST /api/v1/forecast/ai` remains the AOI GloFAS **MODELLED** track (already VALIDATED); do not conflate with spatial maps.
- Later taxonomy (documentation only): VALIDATED, EXPERIMENTAL, NOT_VALIDATED, UNAVAILABLE, INSUFFICIENT_DATA.
- Do not serve uncalibrated conformal as confidence.
- 6/12/24/48/72 h remain UNAVAILABLE for spatial.
- `GET /api/v1/research/compare` keeps `comparable_to_physics: false`.

---

## 28. Frontend impact (future; not this phase)

Do not redesign the UI now.

Later implications: overlay only after VALIDATED; status text for NOT_VALIDATED / INSUFFICIENT_DATA; horizon 192 h vs UNAVAILABLE 6–72 h; uncertainty omitted or UNCALIBRATED; provenance badges; coverage of which AOIs have GFM; never “AI Powered”; never imply operational trust for an experimental research model. `ModelStatusPanel.jsx` already notes Gate 2.

---

## 29. Testing strategy (future code; this phase adds existence check only)

Must keep passing: Phase 5 spatial (`GRID_SIZE=32`), Phase 5.5 events, Phase 6 formulation gates, 3-city catalog, spatial API UNAVAILABLE, `mark_spatial_validated` absent from `phase6.py` / `train.py`, nodata never dry, no pixel-i.i.d.

Later tests: basin-level event dedup, neighbor-tile AOI-valid (not STAC-hit) filter, rain-cube completeness, Gate A–J fixtures, synthetic samples not OBSERVED.

This phase: assert this document exists (same pattern as other phase docs).

---

## 30. Implementation phases (after a later Agent-mode approval)

This document-writing phase stops here. A **future** implementation, in order, must not collapse into “train a U-Net”:

1. `python scripts/phase6_acquire.py --skip-features` — 64×64 index from local GFM GeoTIFFs.
2. Feature fetch: elevation lattice, rivers, precip lattice (network). Measure within-tile rain variance.
3. IMERG only if lattice variance is still ~0 on Sunamganj.
4. Adjacent Equi7 tiles with AOI-valid ≥5% (revisit `E039N024T3` as coverage).
5. Event inventory vs 20-event floor; add basin_id if subtiles split events.
6. Diagnostic GBDT/RF on v2 tensors. **No CNN. No VALIDATED.**
7. GLO-30 window if `FLOODLENS_DEM_PATH` is set; else keep fail-closed lattice.
8. HydroRIVERS clip if provided; else OSM.
9. Fix `make_synthetic_sample_v2` `label_kind` inconsistency.
10. Re-evaluate Gates 0/1/2 and A–J. If Gate 0 fails: stop.

Do not edit `src/floodlens/numerical/**`. Do not call `mark_spatial_validated`.

---

## 31. Risks

- Independent events still &lt;20 after AOI expansion on one tile (likely).
- Sylhet remains uncovered (valid_frac &lt; 5%).
- ERA5-Land too coarse on haors; IMERG still ~10 km.
- `FLOODLENS_DEM_PATH` unset; elevation lattice ≠ floodplain microtopography.
- HydroRIVERS file missing; OSM incomplete.
- STAC/license change.
- Confusing 39 scenes with 7 events.
- Synthetic v2 labeled OBSERVED leaking into a “real” corpus if someone calls the helper outside tests.
- Serving ERA5 as if it were operational NWP.

---

## 32. Explicit non-goals

- Any change under `src/floodlens/numerical/**`
- Inventing 6/12/24/48/72 h GFM labels or interpolating scenes
- Training U-Net, ConvLSTM, Transformer, or GNN in this phase
- Mixing GFM OBSERVED with Giezendanner/GFD in one metric table
- Promoting spatial catalog VALIDATED
- Ranking physics vs AI
- FABDEM, national DEM mosaic, synthetic DEM for eval
- Frontend architecture redesign
- Zarr/cloud training infrastructure
- Coastal/tidal domain as the same model without a split
- Claiming uncertainty as confidence

---

## 33. Recommended next Cursor Agent-mode prompt

**Prompt 1 (already satisfied by writing this file):** create `docs/PHASE_6_5_DATASET_EXPANSION_PLAN.md`; do not implement acquire/train.

**Prompt 2 (later dataset work, only if the user asks):**

> Execute §30.1–30.6 of `docs/PHASE_6_5_DATASET_EXPANSION_PLAN.md`. Index local GFM to 64×64 (`scripts/phase6_acquire.py`), fetch lattices if network is allowed, run `scripts/phase6_evaluate.py`, report Gate 0/1/2 honestly. Do not train a U-Net. Do not call `mark_spatial_validated`. Do not edit `src/floodlens/numerical/**`. Do not invent 6–72 h labels. Product catalog stays three cities. If independent events &lt; 20, stop after the diagnostic report.

---

## Decision block

**Choice: E — Reformulate + expand dataset.**

| Item | Recommendation |
| --- | --- |
| Independent events before attempting validation | **≥20** (prefer **25–40**) |
| Geographic regions with ≥5% valid GFM | **≥3** (prefer **5** BD floodplain/haor) |
| Working spatial resolution | **64×64** (~0.5 km Sunamganj; Dhaka subtiled). Native GFM 20 m not upsampled |
| Temporal resolution of labels | Sentinel-1 scene / **192 h** slot |
| Rain lookback | Hourly **72 h** cube/lattice |
| Forecast horizons | **192 h YES**; **6/12/24/48/72 UNAVAILABLE** |
| Minimum spatial channels before CNN | **4** (persistence, elev, slope/HAND, river distance, non-broadcast rain) |
| Primary baseline | **Pixel GBDT** |
| First production-grade model | **Pixel GBDT/RF**, not U-Net |
| VALIDATED | Gates A–J **and** existing Gate 2 on pre-registered event + geographic holdouts; uncertainty measured or omitted |

Reject A (current 7-event extract cannot identify skill). Reject C as mixed headline labels. Reject D as switching to depth or 24 h interpolation (no observations). Reject F as aborting expansion that is still possible. Promotion of CNN/VALIDATED stays stopped until gates pass.

**NO IMPLEMENTATION UNTIL USER APPROVAL** of a later Agent-mode dataset-expansion prompt. This file is the plan document only.

Physics vs spatial AI: **COMPARISON NOT YET COMPARABLE.**

**SOLVER MODIFIED: NO.** Spatial catalog: **NOT_VALIDATED.**
