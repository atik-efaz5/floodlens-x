# Phase 6.5B — Independent flood-event expansion report

**Status:** DATASET QUALITY ASSESSMENT. Not a VALIDATED claim. Not a training run.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**Official recommendation:** **DATASET STILL INSUFFICIENT — DO NOT TRAIN**

**Solver:** `src/floodlens/numerical/**` was not modified.

**Dataset version:** `phase6.5-gfm-spatial-v2.1` (material expansion vs 6.5A `v2`; prior `index.json` snapshotted as `index_phase65a.json`).

Machine-readable inventory: `src/floodlens/application/data/ml/spatial/event_inventory/event_candidates.csv`

---

## A. Current baseline (Phase 6.5A)

| Metric | 6.5A |
| --- | --- |
| Independent events | 8 |
| Scenes | 42 |
| Regions with valid GFM | 7 (Sylhet absent) |
| Tiles / samples | 155 |
| Unknown pixels | ≈37% |
| Spatial channels | 9 |
| Constant channels | 1 |
| Missing channels | 0 |
| Gate A | PASS |
| Gate B | FAIL (8 < 20) |
| Gate C | PASS |
| Gate D | PASS |
| Gate E | PASS |
| Gate F | PASS (holdout IoU PENDING) |
| Gate I | PASS |
| Gate J | FAIL |
| Spatial AI | NOT_VALIDATED |

Event definition (unchanged): global **45-day** date clustering. Same monsoon across Dhaka / haor AOIs is **one** `event_id`. Tiles and scenes are not events. Synthetic events are not counted.

---

## B. New candidate events discovered

Target clusters searched on Copernicus GFM STAC (covering-orbit preference ~12:04 / ~23:55; empty 11:56 / 23:47 swaths skipped when a covering file was already local):

| candidate_id | window | STAC features | new downloads / attempts | outcome |
| --- | --- | --- | --- | --- |
| cand:2017-04 | 2017-04-12 … 2017-05-20 | 82 | 8 | AOI-valid → `evt:2017-04-12` |
| cand:2017-08 | 2017-07-31 … 2017-08-25 | 58 | 8 | AOI-valid → `evt:2017-07-31` |
| cand:2024-07 | 2024-06-20 … 2024-08-15 | 89 | 8 | AOI-valid → `evt:2024-06-22` |
| cand:2025-07 | 2025-06-20 … 2025-08-15 | 100 | 8 | GFM AOI-valid `evt:2025-07-11`; **not in feature cube** (rain lattice ends 2024-08-31; 19 tiles dropped) |
| cand:2015-07 | 2015-07-01 … 2015-08-20 | 47 | 6 | AOI-valid → `evt:2015-07-11` (point-rain fallback; lattice does not cover 2015) |
| cand:2016-01 | 2016-01-10 … 2016-02-05 | 20 | 3 | AOI-valid → `evt:2016-01-19` |
| cand:2019-01 | 2019-01-10 … 2019-02-05 | 57 | 8 | AOI-valid → `evt:2019-01-10` |
| cand:2020-01 | 2020-01-10 … 2020-02-05 | 57 | 8 | AOI-valid → `evt:2020-01-15` |

Raw GeoTIFF count after acquire: **154** local product-tile files. Index kept **81** AOI-valid scenes (was 42). Duplicate scene IDs: **none**.

No fabricated rainfall, DEM, discharge, or flood extents. No second label source was merged into headline GFM metrics.

---

## C. New accepted events

**Feature-cube independent events (Gate B / training-eligible): 15** (was 8).

New relative to 6.5A:

| event_id | season | mechanism | rain lattice | notes |
| --- | --- | --- | --- | --- |
| `evt:2015-07-11` | monsoon | riverine / haor | no (before 2016-06-01) | Point-rain fallback; Sylhet present on 2015-07-11 |
| `evt:2016-01-19` | winter | winter_or_early | no (before lattice start) | 8 flood pixels only |
| `evt:2017-04-12` | premonsoon | haor_premonsoon_flash | yes | Distinct from 2017 monsoon (gap > 45 d) |
| `evt:2017-07-31` | monsoon | monsoon_riverine | yes | Covering orbits replaced empty 2017 local files |
| `evt:2019-01-10` | winter | winter_or_early | yes | 30 flood pixels |
| `evt:2020-01-15` | winter | winter_or_early | yes | 34 flood pixels |
| `evt:2024-06-22` | monsoon | monsoon_riverine | yes | |

GFM-indexed but **not** in the processed feature cube:

| event_id | reason |
| --- | --- |
| `evt:2025-07-11` | Rain lattice window is 2016-06-01 … 2024-08-31. Samples without precip lookback were dropped (`dropped=19`). Not fabricated. |

---

## D. Rejected candidates + reasons

Every `cand:*` row in the inventory is `accepted=False` with `already_in_index` after the corresponding `evt:*` was kept. That is duplicate-candidate bookkeeping, not a silent drop of a new flood.

Winter GFM scenes with flood pixels were **not** rejected by the pixel filter. They remain a **quality caveat** (see J): flood counts are 8–34 pixels and may be residual / permanent water rather than a monsoon pulse. They are still independent under the 45-day rule and were not recoded to dry.

No STAC window in this run returned a hard licensing block. Empty 2017/2024 files already on disk were skipped (`skipped_existing`); covering orbits were downloaded instead.

---

## E. Independent-event count

**15 independent meteorological events** in `processed_v2` samples (45-day clustering).

81 GFM scenes and 277 city-tiles are **not** 81 or 277 events.

Minimum target **20**: **not met**. Preferred 30–40 / strong 50+: **not claimed**.

---

## F. Events by year

| year | n events |
| --- | ---: |
| 2015 | 1 |
| 2016 | 2 |
| 2017 | 2 |
| 2018 | 2 |
| 2019 | 2 |
| 2020 | 2 |
| 2021 | 1 |
| 2022 | 1 |
| 2023 | 1 |
| 2024 | 1 |

2025 monsoon is GFM-observed but excluded from the feature cube (no rainfall lookback).

---

## G. Events by region

| region | n events | years |
| --- | ---: | --- |
| sunamganj | 14 | 2015–2024 |
| kishoreganj | 14 | 2015–2024 |
| netrokona | 14 | 2015–2024 |
| dhaka_ne | 13 | 2015, 2017–2024 |
| dhaka_nw | 13 | 2015, 2017–2024 |
| dhaka_se | 12 | 2016–2022, 2024 |
| dhaka_sw | 12 | 2016–2022, 2024 |
| sylhet | 2 | 2015, 2016 |

A region appearing in many tiles of the **same** monsoon is still one event. Geographic diversity is **not** event independence.

Sylhet now has two AOI-valid scenes (see K / §11). Two events do not establish Sylhet generalization.

---

## H. Events by flood mechanism

Mechanism is tagged from calendar month + basin profile. It is metadata, not a second event key.

| mechanism | n events (sample-level tags; events may span basins) |
| --- | ---: |
| central_floodplain_riverine | 10 |
| haor_monsoon_inundation | 9 |
| haor_meghna_floodplain | 9 |
| winter_or_early | 4 |
| haor_premonsoon_flash | 2 |

Haor vs central floodplain on the same dates remain **one** event.

---

## I. GFM coverage

- Source: Copernicus GFM `ensemble_flood_extent`, Equi7 AS020M, STAC `https://stac.eodc.eu/api/v1`.
- Product tile: `E039N021T3` (neighbor `E039N024T3` still yields no AOI-valid clips).
- Index: 154 local TIFFs → **81 kept**, remainder `AOI nodata (unknown, not dry)`.
- Working grid: 64×64, unknown=255 preserved.
- Acquisition: resumable (skip existing files, skip existing `npz`), covering-orbit preference, checksum fingerprint, failed downloads recorded, no synthetic fallback.

### Sylhet (section 11)

Failure mode on the 6.5A probe scene `20180606T120436`: **scene footprint mismatch**.

- AOI box (91.50, 24.40, 92.30, 25.20) has **all 4 corners on `E039N021T3`**, 0 on `E039N024T3`.
- Probe valid_frac: Sunamganj ≈ 0.67, Sylhet ≈ 0.0012 (below 5%).
- Not caused by the 5% threshold, projection, unknown-as-dry recoding, or an undersized box. Enlarging the AOI would not move Sylhet city into the Sunamganj swath.

Orbit-specific exceptions (not a reason to enlarge the box): **2 kept Sylhet scenes** — `20150711T115614`, `20160119T115610`. Most Sunamganj-covering orbits still miss Sylhet city.

---

## J. Unknown-label distribution

Overall (feature cube): **unknown = 35.6%** (404,015 / 1,134,592 labeled cells; flood 48,174; dry 682,403). Slightly below 6.5A’s ≈37% because new haor scenes are cleaner, not because unknown was recoded as dry.

### By region (GFM index)

| region | unknown fraction | exclude_label_quality (≥0.80) |
| --- | ---: | --- |
| dhaka_ne | 0.837 | **yes** |
| dhaka_nw | 0.629 | no |
| dhaka_se | 0.422 | no |
| sunamganj | 0.328 | no |
| dhaka_sw | 0.261 | no |
| netrokona | 0.038 | no |
| kishoreganj | 0.031 | no |
| sylhet | 0.028 | no (n=2 scenes) |

`dhaka_ne` remains too unknown for reliable local training signal. Unknown stays 255.

### By event (worst)

| event_id | unknown fraction | flood px |
| --- | ---: | ---: |
| `evt:2016-06-30` | **0.887** | 7 |
| `evt:2020-06-07` | 0.400 | 4497 |
| `evt:2016-01-19` | 0.397 | 8 |
| other events | 0.19–0.38 | — |

**Worst event unknown: 88.7%** (`evt:2016-06-30`, Dhaka SW only). Suggested exclude for label quality; not recoded.

Winter events (`2016-01`, `2019-01`, `2020-01`) have almost no flood pixels. They inflate the independent-event count under the 45-day rule but are weak hydrological floods.

Full by-scene/tile table: `event_inventory/unknown_diagnostics.json`.

---

## K. Rainfall availability

| coverage | status |
| --- | --- |
| ERA5-Land / Open-Meteo lattice 2016-06-01 … 2024-08-31 | **available** (REANALYSIS, spatially varying) |
| 2015 monsoon | lattice **unavailable**; point-rain fallback (TEMPORAL-ONLY for those tiles) |
| 2016 January | lattice **unavailable** (before START) |
| 2025 monsoon | lattice **unavailable**; samples dropped |
| Future rain in lookback | **none** (Gate D PASS) |

Absence of lattice is explicit. It was not filled with synthetic rain.

---

## L. DEM availability

Open-Meteo elevation lattice + slope: **available** for all AOIs in the cube. Copernicus GLO-30 (`FLOODLENS_DEM_PATH`) remains **UNAVAILABLE** (not substituted).

---

## M. River availability

OSM waterway distance/mask: **available** for 7/8 AOIs. Netrokona OSM still has 0 vertices (distance map degrades; not fabricated). GloFAS Q lookback remains **MODELLED** / cell proxy — absence of observed discharge is explicit and did not by itself reject events.

---

## N. Prospective split statistics

Event-level temporal split (not pixel i.i.d.). No event in two splits. Duplicate-event detection: **clean**.

| split | n events | event_ids |
| --- | ---: | --- |
| TRAIN | **7** | `2015-07-11`, `2016-01-19`, `2016-06-30`, `2017-04-12`, `2017-07-31`, `2018-01-13`, `2018-06-06` |
| VAL | **5** | `2019-01-10`, `2019-06-15`, `2020-01-15`, `2020-06-07`, `2021-06-02` |
| TEST | **3** | `2022-05-16`, `2023-06-16`, `2024-06-22` |

Train holds the plurality (7/15). This is **not** a split that parks most events in val/test. Test includes a temporal challenge (2022 named holdout + 2023 + 2024). Geographic holdout regions remain sunamganj / sylhet / netrokona (eval geography, not a second event key).

**Do not train on this split.** It is a prospective quality report only.

---

## O. Gate B result

**Official Gate B: FAIL** (`events=15 < 20`). Official floor **unchanged** at 20.

Reported extras (not a silent definition change):

- total independent events: 15
- train / val / test: 7 / 5 / 3
- events per year / region: see F, G
- minimum events in any split: **3**
- duplicate-event detection: **clean**

Research recommendation (documented separately): FAIL <20, PROVISIONAL 20–29, PASS ≥30 with split diversity. **Research = FAIL.**

---

## P. Gate F result

**Official Gate F: PASS** (≥3 AOIs with valid GFM; now **8** valid regions including two Sylhet scenes).

Extras (Gate F is not “number of regions” alone):

- events per region: Sylhet has **2**; others 12–14
- years per region: Sylhet 2015–2016 only
- flood mechanism per event: see H
- train/val/test coverage: 7 / 5 / 3
- geographic holdout IoU: **PENDING** (no model)

A single (or two) Sylhet events do **not** establish geographic generalization.

---

## Q. Dataset version

`phase6.5-gfm-spatial-v2.1` because seven new independent events entered the cube.

6.5A `index.json` was copied to `processed_v2/index_phase65a.json` before overwrite. Older version was not destroyed in place without a snapshot.

---

## R. Provenance audit

Every accepted sample carries source `copernicus-gfm-ensemble-flood-extent`, retrieval datetime, checksum fingerprint, processing version `phase6.5-gfm-spatial-v2.1`, event_id, split, label_kind=OBSERVED. Scene manifest lists kept / skipped_empty / failed. Candidate CSV records STAC feature counts and attempt statuses.

Reproducibility: `scripts/phase65b_expand.py --download-gfm` is resumable (existing GeoTIFFs skipped).

---

## S. Licensing audit

| source | decision | license / use |
| --- | --- | --- |
| GFM ensemble flood extent | **A** — unified primary labels | STAC proprietary; Copernicus EMS attribution. Headline OBSERVED labels only. |
| OPERA DSWx-S1 | **D** | Same S1 revisit class; do not merge. |
| VIIRS/MODIS NRT | **D** | Optical, clouds, different flood definition. |
| Global Flood Database | **C** | Event-max climatology; CC BY-NC; discovery only. |
| Giezendanner Bangladesh | **D** | DERIVED 8-day ~500 m. Never OBSERVED. |
| GloFAS Rapid Flood Mapping | **D** | MODELLED inundation. |
| EMSR | **C** | Public list had 0 Bangladesh rows in prior audit. |
| WorldFloods / Sen1Floods11 | **D** | Wrong task / often NC. |

No incompatible source was merged into Gate B counts.

Rain lattice: Open-Meteo / ERA5-Land family, CC BY 4.0. OSM waterways: ODbL. Elevation lattice: Open-Meteo SRTM/GLO family.

---

## T. Whether further acquisition is still required

**Yes.** Fifteen events is material progress (8 → 15) and still **below the official floor of 20**.

Scientific ceiling on this Equi7 tile + 45-day rule + GFM 2015–2025:

- Monsoon/premonsoon pulses already ingested for 2015–2024 (plus 2025 labels without rain).
- Additional winter clusters (2021–2024 January) would likely add date-clusters with near-zero flood pixels — not a legitimate way to pass Gate B.
- Additional AOIs on the **same** monsoon (Jamalpur, Sirajganj, Padma on the same dates) are **not** new independent events.
- Extending the rain lattice through 2025 would add at most **one** cube-eligible event (16 total), still <20.
- A second observed source is not semantically compatible for a unified label (section S).

Further GFM years before 2015 are not in the public STAC history used here. Other Equi7 tiles for western Jamuna / coastal compound floods were **not** downloaded; even if AOI-valid, overlapping monsoon dates would collapse under the 45-day rule.

**Stop condition:** independent-event floor not reachable from this GFM tile/AOI set without loosening the event definition, fabricating labels, or mixing incompatible sources. Those options are forbidden.

---

## Gates A–J (this run)

| Gate | Status | Note |
| --- | --- | --- |
| A | PASS | OBSERVED GFM only; no synthetic in REAL |
| B | **FAIL** | 15 < 20 |
| C | PASS | 9 spatial channels; DEM + lattice majority |
| D | PASS | no future rain |
| E | PASS | unknown preserved; not recoded dry |
| F | PASS | 8 valid regions; extras reported |
| G | PENDING | no training |
| H | PENDING | no training |
| I | PASS | split manifests written |
| J | FAIL | COMPARISON NOT YET COMPARABLE |

Channel audit: spatial=9, temporal-only=4, constant=0, missing=0. No extra channels were added to inflate count. Constant went 1→0 because the expanded geography made a previously flat channel vary.

AOI tabular GBDT VALIDATED status: **unchanged**. Spatial registry not promoted.

---

## Final decision

**DATASET STILL INSUFFICIENT — DO NOT TRAIN**

Even if 20 events were reached, training would still require a separate explicit approval. This phase does not train and does not return VALIDATED.

SOLVER MODIFIED: **NO**

SPATIAL AI: **NOT_VALIDATED**
