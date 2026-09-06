# Phase 6.5A — Dataset expansion and quality report

**Status:** DATASET QUALITY REPORT. Not a VALIDATED claim. Not a training run.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**Recommendation:** **DATASET STILL INSUFFICIENT — DO NOT TRAIN.**

**Solver:** `src/floodlens/numerical/**` was not modified.

---

## 1. What was implemented

Phase 6.5A implemented the dataset-expansion and dataset-quality portion of `docs/PHASE_6_5_DATASET_EXPANSION_PLAN.md` (Decision E, Target A).

- Formal flood-event records (`event_id`, start/peak/end, region, source, provenance, quality).
- Deterministic 45-day meteorological clustering with `basin_id` metadata. Same monsoon across AOIs is one event.
- Event-level train/val/test manifests (no pixel-i.i.d.; no event in two splits).
- Local GFM indexing to `processed_v2` (64×64) on Equi7 tiles `E039N021T3` and `E039N024T3`, AOI-valid ≥5% filter, unknown=255 preserved.
- Resumable acquisition (skip existing GeoTIFFs; skip existing AOI `npz`; failed downloads recorded).
- Spatial feature cube: ERA5-Land rainfall lattice cube (hourly t−72 h … t0, hour-aligned, no future rain), Open-Meteo elevation lattice + slope, OSM river distance/mask, height-above-river where both DEM and river mask exist, lagged GFM persistence.
- GLO-30 window path via `FLOODLENS_DEM_PATH` (unset here → UNAVAILABLE, not synthetic).
- Per-channel catalog (name, units, source, resolution, missing policy, SPATIAL vs TEMPORAL-ONLY vs CONSTANT vs MISSING).
- Provenance envelopes extended from the existing application contract.
- Gates A–F machine-evaluated (PASS/FAIL/PENDING + reasons). Gates G–H pending (no training). Gate J FAIL (physics not comparable).
- `scripts/phase65a_expand.py` / `evaluate_phase65a()` do not fit GBDT, RF, U-Net, or call `mark_spatial_validated`.

## 2. Dataset sources actually acquired

| Source | Status | Notes |
| --- | --- | --- |
| Copernicus GFM `ensemble_flood_extent` | **Acquired (local index)** | 99 local GeoTIFFs (95× `E039N021T3`, 4× `E039N024T3`). 42 scenes kept after AOI-valid ≥5%. Neighbor-tile files existed but produced **no** AOI with ≥5% valid pixels. |
| Open-Meteo archive / ERA5-Land precip lattice | **Acquired** | 3×3 points × 8 AOIs, hourly 2016-06-01 … 2024-08-31, kind **REANALYSIS**, CC BY 4.0. |
| Open-Meteo elevation lattice | **Acquired** | 17×17 per AOI, SRTM/GLO family. Not GLO-30 microtopography. |
| OSM waterways (Overpass) | **Acquired (partial)** | Real geometries for 7/8 AOIs. Netrokona returned 0 vertices. |
| Point Open-Meteo precip + GloFAS Q (`ml/real`) | **Already on disk** | Used as TEMPORAL-ONLY Q lookback / point-rain fallback. |
| Copernicus GLO-30 (`FLOODLENS_DEM_PATH`) | **UNAVAILABLE** | Env unset. Not substituted with synthetic DEM. |
| HydroRIVERS clip (`FLOODLENS_HYDRORIVERS_PATH`) | **UNAVAILABLE** | OSM used instead where vertices exist. |
| IMERG, BWDB gauges, Giezendanner, GFD | **Not acquired** | Marked unavailable; not fabricated. |

No DEMO/SIMULATED maps entered `processed_v2`. `make_synthetic_sample_v2` is now `label_kind=SIMULATED` and is skipped by the real builder.

## 3. Number of independent events

**8 independent meteorological events** (45-day gap, basin-shared `event_id`):

`evt:2016-06-30`, `evt:2018-01-13`, `evt:2018-06-06`, `evt:2019-06-15`, `evt:2020-06-07`, `evt:2021-06-02`, `evt:2022-05-16`, `evt:2023-06-16`.

This is **one more episode than the previous ~7-event set** (2016 monsoon recovered). Extra AOIs (Dhaka subtiles, Kishoreganj, Netrokona) add tiles of the **same** monsoons, not new independent floods. Floor for Gate B / Gate 0 remains **20**. **Not met.**

42 unique scene days; 155 city-tiles. Those are not 42 or 155 events.

## 4. Geographic coverage

Seven AOIs with valid GFM (valid flood+dry > 0). **Sylhet is absent** (valid fraction stayed below 5%; neighbor Equi7 `E039N024T3` did not yield an AOI-valid clip). Coverage is not fabricated for empty regions.

| region_id | events | scenes | flood px | dry px | unknown px | unknown fraction | dates |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_ne | 7 | 24 | 182 | 14,685 | 83,437 | 0.849 | 2018-01-13 … 2023-08-15 |
| dhaka_nw | 7 | 24 | 418 | 34,561 | 63,325 | 0.644 | 2018-01-13 … 2023-08-15 |
| dhaka_se | 6 | 15 | 174 | 35,694 | 25,572 | 0.416 | 2018-01-15 … 2022-05-18 |
| dhaka_sw | 7 | 18 | 868 | 49,883 | 22,977 | 0.312 | 2016-06-30 … 2022-05-18 |
| kishoreganj | 7 | 24 | 7,412 | 90,892 | 0 | 0.000 | 2018-01-13 … 2023-08-15 |
| netrokona | 7 | 25 | 7,729 | 91,981 | 2,690 | 0.026 | 2018-01-13 … 2023-08-15 |
| sunamganj | 7 | 25 | 5,889 | 59,376 | 37,135 | 0.363 | 2018-01-13 … 2023-08-15 |

Product catalog remains Dhaka / Sunamganj / Sylhet (three cities). Extra AOIs are training/eval geography only.

## 5. Temporal coverage

GFM labels: **2016-06-30 … 2023-08-15** (42 scene dates). Rain lattice lookback: hourly **2016-06-01 … 2024-08-31**. Issue time = `valid_at − 192 h`. No future rainfall in the input window.

## 6. Spatial resolution

- Native GFM: Equi7 AS020M **20 m**.
- Working tensor: **64×64** on EPSG:4326 AOI bounds (cell size ~0.5–1 km depending on AOI; documented in per-AOI grid spec).
- Rain lattice: ERA5-Land family **~11 km**, IDW onto the working grid.
- Elevation lattice: 17×17 per AOI, bilinear to 64×64. Not 30 m GLO-30.

## 7. Temporal resolution

- Labels: GFM scene slot, **192 h** (not daily 6–72 h). 6/12/24/48/72 h maps were **not invented**.
- Rain cube: **hourly** t−72 … t0 (hour-floored). Derived 24 h / 72 h accumulations and 24 h intensity from that cube.
- Q: daily t−7 … t−1 (GloFAS, MODELLED, TEMPORAL-ONLY).
- DEM / rivers: static.

## 8. Feature cube composition

Dataset version: `phase6.5-gfm-spatial-v2`.

| Channel | Class (audit) | Units | Source |
| --- | --- | --- | --- |
| precip_24h | SPATIAL | mm | ERA5-Land lattice IDW |
| precip_72h | SPATIAL | mm | ERA5-Land lattice IDW |
| precip_intensity_24h | SPATIAL | mm/h | max hourly in 24 h lookback, IDW |
| dem | SPATIAL | m | Open-Meteo elevation lattice |
| slope | SPATIAL | m / cell | gradient of elevation |
| river_distance | SPATIAL | degrees | OSM waterways (HydroRIVERS UNAVAILABLE) |
| height_above_river | SPATIAL | m | elev − min(elev on river mask) |
| persistence | SPATIAL | class | previous completed GFM scene |
| persistence_valid | SPATIAL | 0/1 | finite persistence mask |
| log1p_q | TEMPORAL-ONLY | log1p m³/s | GloFAS |
| month_sin / month_cos | TEMPORAL-ONLY | — | calendar |
| precip_is_aoi_point | CONSTANT | flag | 0 on lattice samples |

**Channel counts:** 13 channels; **9 spatially varying**; 3 TEMPORAL-ONLY; 1 CONSTANT; **0 MISSING** on the evaluated corpus.

Per-sample fields include `t0`, `input_start`, `input_end`, `target_time`, `rainfall_source`, `rainfall_status=REANALYSIS`. Spatially constant broadcasts are not claimed as spatial channels.

## 9. Label statistics

Target A: GFM OBSERVED binary occurrence, τ=0.25, horizon 192 h.

| Quantity | Count |
| --- | --- |
| Independent events | 8 |
| Scenes kept | 42 |
| Regions with valid GFM | 7 |
| Tiles / samples | 155 |
| Flood pixels (class 1) | 22,672 |
| Dry pixels (class 0) | 377,072 |
| Unknown pixels (255) | 235,136 |
| Valid pixels | 399,744 |
| Flood fraction among valid | 0.0567 |

Unknown was never recoded as dry.

## 10. Unknown / missing statistics

Unknown fraction **37.0%** overall (was ~60% on the v1 32×32 two-city set). Highly variable by AOI: Kishoreganj ~0 unknown; Dhaka NE ~85% unknown. Native 255 is nodata/exclusion (swath, layover, product exclusion), **not optical cloud**.

UNAVAILABLE (not imputed): GLO-30, HydroRIVERS, BWDB stage, IMERG, Sylhet GFM, Netrokona OSM rivers, neighbor-tile AOI-valid labels.

## 11. Event split statistics

Scheme: event-level temporal (split of `event_start`). Pixel-i.i.d. forbidden. Leaks empty.

| Split | Events | Samples |
| --- | --- | --- |
| train | `evt:2016-06-30`, `evt:2018-01-13`, `evt:2018-06-06` (3) | 27 |
| validation | `evt:2019-06-15`, `evt:2020-06-07`, `evt:2021-06-02` (3) | 81 |
| test | `evt:2022-05-16`, `evt:2023-06-16` (2) | 47 |

Geographic holdout regions (manifest only; IoU not computed — no training): train = Dhaka subtiles + Kishoreganj; test = Sunamganj + Netrokona. Sylhet still has no valid labels.

Samples per event: 3, 12, 12, 17, 25, 39, 17, 30 (same pulse, many AOI tiles).

## 12. Provenance verification

GFM scenes store source, STAC/local href, datetime, Equi7 tile, checksum (`bytes` + sha256 of file ends), license proprietary, Copernicus attribution, `label_kind=OBSERVED`, processing version `phase6.5-gfm-spatial-v2`. Rain/elevation/rivers caches record source, kind, license. Sample extras include alignment (CRS EPSG:4326, 64×64, Equi7 window + block-reduce, rain hours strictly &lt; t0). Tests assert provenance completeness helpers and that synthetic maps cannot pass Gate A as REAL.

## 13. Licensing status

| Dataset | License / terms | Used as |
| --- | --- | --- |
| GFM ensemble extent | STAC proprietary; Copernicus attribution | OBSERVED labels (raw gitignored) |
| Open-Meteo archive / elevation | CC BY 4.0 | REANALYSIS rain, OBSERVED elevation lattice |
| OSM waterways | ODbL | River geometry substitute |
| GloFAS Q via Open-Meteo | MODELLED | TEMPORAL-ONLY scalar |
| GLO-30 / HydroRIVERS / FABDEM / IMERG | Not loaded | GLO-30/HydroRIVERS UNAVAILABLE; FABDEM not used |

Do not claim CC-BY for GFM. Do not redistribute raw GFM.

## 14. Gate A–F results

| Gate | Name | Status | Reasons |
| --- | --- | --- | --- |
| A | Dataset validity | **PASS** | processed_v2 exists; OBSERVED only; unknown never dry; no synthetic in REAL path |
| B | Event independence | **FAIL** | `events=8 < 20` |
| C | Spatial feature sufficiency | **PASS** | 9 SPATIAL channels; DEM present (lattice); lattice rain on majority |
| D | Temporal causality | **PASS** | Features &lt; t0; no FORECAST in lookback |
| E | Label quality | **PASS** | kept scenes valid_frac ≥5%; 255 unknown; no mixed label table |
| F | Geographic diversity | **PASS** | 7 AOIs with valid GFM. Geographic-holdout **IoU PENDING** (no training) |
| G | Baseline competitiveness | **PENDING** | no model training in 6.5A |
| H | Uncertainty calibration | **PENDING** | no model training in 6.5A |
| I | Reproducibility | **PASS** | split manifests + dataset_version written |
| J | Physics comparability | **FAIL** | COMPARISON NOT YET COMPARABLE |

Mapped Gate 0: **FAIL** (`independent_events` only after rain-cube alignment).

## 15. What remains unavailable

- Independent-event floor (≥20). Additional years/basins/sensors required; more AOIs on one Equi7 tile will not get there.
- Sylhet GFM (≥5% valid). Neighbor tile `E039N024T3` indexed; **0** AOI-valid scenes.
- Copernicus GLO-30 window (`FLOODLENS_DEM_PATH` unset).
- HydroRIVERS clip; Netrokona OSM rivers (0 vertices).
- IMERG (only if lattice variance collapses; on this extract 24 h rain **is** spatially varying).
- BWDB water level / discharge gauges.
- Giezendanner / GFD / 6–72 h observed maps.
- STAC download of additional years in this run (local 99 GeoTIFFs were indexed; optional `--download-gfm` not required for `processed_v2`).

## 16. Why the dataset is or is not sufficient for training

**Not sufficient for model training or catalog VALIDATED.**

Gate B fails: 8 independent events, 3 train events. Pixel count (155×64×64) is still eight floods. Geographic expansion is real (7 regions vs 2) and spatial channels are now genuine, but the scientific bottleneck named in the Phase 6.5 plan — **independent meteorological events** — is not resolved.

A U-Net/CNN/GBDT run on this extract would overfit episode identity. Do not train.

## 17. Exact next scientific step

1. **Expand independent events**, not AOI subtiles: additional GFM years/seasons and/or additional Equi7 tiles that actually contain AOI-valid haor/Sylhet swaths; do not loosen the 45-day rule to inflate counts.
2. Re-run Gates A–F only. If Gate B still fails: stop again.
3. Only after ≥20 events: a **separately approved** Phase 6.6 diagnostic of pixel GBDT vs persistence on the frozen event splits. No U-Net until Gate G. No VALIDATED until Gate 2 / A–J.

---

processed_v2 path: `src/floodlens/application/data/ml/spatial/gfm/processed_v2/` (gitignored working tensors + `index.json`, `events.json`, `coverage.json`, `sample_manifest.json`, `feature_catalog.json`, `gates_af.json`).
