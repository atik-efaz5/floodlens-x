# Phase 6.5C — Multi-source historical flood-event expansion and label-compatibility study

**Status:** EVENT REGISTRY AND COMPATIBILITY STUDY. Not a VALIDATED claim. Not a training run.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**GFM dataset version (unchanged):** `phase6.5-gfm-spatial-v2.1`

**This registry version:** `phase6.5-multisource-event-v1` (event registry only; does not overwrite GFM tensors)

**Official recommendation:** **DATASET STILL INSUFFICIENT FOR TRAINING — DO NOT TRAIN**

**Decision (section 19):** **B. GFM + SECOND SOURCE FOR EVENT DISCOVERY ONLY**

**Solver:** `src/floodlens/numerical/**` was not modified.

Machine-readable outputs:

- `src/floodlens/application/data/ml/spatial/event_inventory/multisource_event_registry.csv`
- `src/floodlens/application/data/ml/spatial/event_inventory/source_compatibility_matrix.csv`
- `src/floodlens/application/data/ml/spatial/phase65c_eval.json`

---

## 1. Sources investigated

| ID | Dataset | Provider | Type | Resolution | Time | Bangladesh | Label kind |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GFM | `ensemble_flood_extent` | CEMS / EODC | S1 SAR ensemble scene | 20 m | 2015–present, ~6–12 d | yes | **OBSERVED** |
| BD 2001–2022 | Bangladesh Inundation History (Giezendanner et al. 2023, DOI 10.25739/2edm-jh03) | CyVerse / Univ. Arizona | CNN–LSTM fusion of S1 fractions onto MODIS 8-day | 500 m | 2001–2022, 985 GeoTIFFs | most of BD | **DERIVED** |
| GFD | Global Flood Database v1 | Cloud to Street / DFO | MODIS event-maximum water | 250 m | 2000–2018, 913 events globally | 28 intersecting BD | **OBSERVED** (event-max) |
| DFO | Global Active Archive (BD wiki) | Dartmouth Flood Observatory | news/gov/RS **catalog** | n/a (no pixels) | 1985–present (115 BD rows; this study uses 56 from 2000+) | yes | **INVENTORY** |
| OPERA DSWx-S1 | — | NASA | S1 inundation | ~30 m | recent | yes | OBSERVED, duplicate revisit class |
| VIIRS/MODIS NRT | — | NASA | optical NRT | ~375 m | daily-ish | yes | OBSERVED, clouds |
| EMSR | Rapid Mapping | Copernicus | activation polygons | vector | activations | **0 BD rows** (Phase 4) | OBSERVED if present |
| WorldFloods / Sen1Floods11 | — | various | mapping chips | ~10 m | mixed | not these AOIs | often NC |

Default state for every non-GFM source: **SEPARATE OBSERVATION FAMILY**. No pixels were merged.

---

## 2. Sources actually accessible

| Source | What was obtained | What was not |
| --- | --- | --- |
| GFM | Existing v2.1 cube (15 independent events, 76 scenes) | — |
| GFD | Public QC catalog: 28 Bangladesh-intersecting events (IDs, dates, cause, severity). **No rasters.** | Event-max GeoTIFFs / GEE ImageCollection (CC BY-NC; not ingested) |
| DFO | Public Bangladesh event table, 2000–2022 subset (56 rows) | Inundation polygons as training labels |
| Giezendanner | Paper + DOI + CyVerse path documented | **Rasters not downloaded** |

---

## 3. Sources rejected (for acquisition or unified labels)

| Source | Why |
| --- | --- |
| Giezendanner rasters | Anonymous CyVerse GET still redirects to `unblockme.cyverse.org`. Stopped (rule 17 / Phase 6.5 stop-if-unreliable). Also DERIVED, 8-day, 500 m, not an event inventory. Training stack used FABDEM (CC BY-NC-SA). |
| GFD rasters | CC BY-NC; event-maximum optical water; not a 192 h GFM target. Metadata used for discovery only. Population exposure **not** used as labels. |
| OPERA / VIIRS NRT | Duplicate S1 class or optical/cloud incompatibility. |
| EMSR | No Bangladesh activations in the public list already audited. |
| WorldFloods | Wrong task / NC. |
| Nigeria•Bangladesh DFO 1642 | Not geographically useful. |

---

## 4. Licensing results

| Source | License | Product-safe? | This study |
| --- | --- | --- | --- |
| GFM | STAC proprietary; Copernicus attribution | operational path already in use | primary labels |
| Giezendanner | CyVerse curated; code MIT; FABDEM NC-SA in inputs | **not** for a commercial product | not acquired |
| GFD | **CC BY-NC 4.0** | **no** | metadata citation only |
| DFO catalog | public listing; no restriction specified on the wiki table | catalog yes; pixels n/a | discovery metadata |
| ERA5-Land rain / OSM / Open-Meteo DEM | CC BY 4.0 / ODbL | yes | cube features (unchanged) |

---

## 5. Event matching methodology

Unchanged **45-day** gap (`EVENT_GAP_DAYS = 45`).

1. Cluster dates within each source.
2. Two records match if their `[start, end]` windows overlap after a 45-day pad.
3. Same monsoon across regions is one event.
4. GFD is a QC subset of DFO IDs: same DFO ID ⇒ same real-world event, two observation families.
5. A GFM cluster and a DFO/GFD cluster that overlap are **one event, two sources**, not two independent floods.
6. Quality filters for secondary sources: Bangladesh-useful country; centroid in-country unless the polygon is a large transboundary monsoon (≥100,000 km²); reject tiny unconfirmed extents; reject winter residual clusters.

No new event is created merely because a second map exists.

---

## 6. GFM event count

**15** cube-eligible independent events (official Gate B inventory).

**16** GFM-indexed including `evt:2025-07-11` (AOI-valid, not cube-eligible: rain lattice ends 2024-08-31).

---

## 7. Secondary-source event count

After 45-day clustering and quality filters (not raw row counts):

| Source | Accepted clusters | Notes |
| --- | --- | --- |
| GFD | 18 | from 28 BD-intersecting QC rows |
| DFO 2000+ | 31 | from 56 catalog rows |
| Giezendanner | 0 | no event inventory; rasters blocked |

These are **not** added to 15.

---

## 8. Cross-source overlaps

| Pair | Overlap |
| --- | --- |
| GFD clusters matching a GFM event | 3 |
| DFO clusters matching a GFM event | 10 |
| GFD ∩ DFO | same DFO IDs (GFD ⊂ DFO 2000–2018 mapped subset) |

Example: 2017 monsoon GFM `evt:2017-07-31` = DFO 4508 = GFD `dfo:4508`. One flood, three source IDs.

---

## 9. Net independent-event count

| Accounting | N |
| --- | ---: |
| Current GFM-only (cube) | **15** |
| Additional unique real-world events (DFO/GFD, quality-ok, not overlapping GFM) | **21** |
| Combined independent events (registry) | **36** |
| Cube-eligible (GFM feature cube) | **15** |

Do not read 15+28+56. Combined = unique `event_id` after matching.

Unique secondary IDs: `2000-05-27`, `2001-06-05`, `2002-04-18`, `2003-06-11`, `2004-04-14`, `2004-06-20`, `2005-05-25`, `2005-10-03`, `2006-05-31`, `2007-06-11`, `2008-06-20`, `2008-08-30`, `2009-04-20`, `2009-07-03`, `2010-03-27`, `2010-07-01`, `2010-09-09`, `2011-07-21`, `2012-06-24`, `2013-05-14`, `2014-07-13`.

Almost all unique events are **pre-GFM (before 2015)**. They cannot become GFM 20 m training samples without fabricating GFM.

---

## 10. Events by year (combined registry)

2000:1, 2001:1, 2002:1, 2003:1, 2004:2, 2005:2, 2006:1, 2007:1, 2008:2, 2009:2, 2010:3, 2011:1, 2012:1, 2013:1, 2014:1, 2015:1, 2016:2, 2017:2, 2018:2, 2019:2, 2020:2, 2021:1, 2022:1, 2023:1, 2024:1.

Pre-2015 years are discovery-only. GFM years remain as in Phase 6.5B.

---

## 11. Events by region

GFM cube regions (unchanged): sunamganj, kishoreganj, netrokona, four Dhaka subtiles, Sylhet (2 events).

Secondary unique events are tagged `region=bangladesh` at national catalog scale. That is **not** geographic generalization of the 64×64 AOI tensors. DFO/GFD polygons are affected-area estimates, not AOI clips.

---

## 12. Events by mechanism (combined unique IDs)

| mechanism | n |
| --- | ---: |
| monsoon_riverine | 14 |
| haor_monsoon_inundation | 8 |
| haor_premonsoon_flash | 8 |
| winter_or_early | 4 |
| unspecified (e.g. March 2010) | 2 |

Secondary tropical cyclones (Sidr 2007, Amphan 2020, Mahasen 2013) are compound-flood catalogs. Under the 45-day rule Sidr clusters with the 2007 monsoon (Oct 15 → Nov 15). That is conservative independence, not a claim that cyclone and monsoon are physically identical.

---

## 13. Event quality distribution (accepted source-rows)

| quality | n rows |
| --- | ---: |
| monsoon_riverine | 34 |
| ok (mostly GFM) | 15 |
| haor_premonsoon | 8 |
| tropical_cyclone_or_compound | 4 |
| weak_residual_water (GFM winters) | 3 |
| high_unknown (`evt:2016-06-30`) | 1 |

Rejected: Nigeria listing (6 overlapping catalog rows after clustering bookkeeping), centroid outside Bangladesh (2016-04-20 GFD/DFO), tiny unconfirmed extent, CyVerse blocked.

GFM winter clusters remain in the **official 15** (already accepted in 6.5B). They are flagged `weak_residual_water` and are not a template for adding more winters from DFO.

---

## 14. Cube-eligible count

**15.** Official feature cube is GFM-only.

| Class | Meaning | N |
| --- | --- | ---: |
| CUBE-ELIGIBLE | GFM OBSERVED 20 m + rainfall/DEM/river pipeline | **15** |
| EVENT-ELIGIBLE, not cube | Historical DFO/GFD real-world floods without GFM 20 m labels (and usually without the 2016–2024 rain lattice) | **21** unique |
| GFM indexed, not cube | 2025 monsoon (no rain lattice) | 1 |

Pre-2016 unique events cannot use the current precip lattice (`2016-06-01` … `2024-08-31`). DEM/river lattices exist for the eight AOIs but do not turn a national DFO polygon into a 64×64 GFM label.

---

## 15. Label compatibility results

| Pair | Decision | Reason (short) |
| --- | --- | --- |
| GFM ↔ Giezendanner | **D** | DERIVED 8-day 500 m fraction vs OBSERVED 20 m SAR scene; different unknown/permanent water; FABDEM NC-SA in training; rasters inaccessible |
| GFM ↔ GFD | **C** | Event-max optical 250 m, CC BY-NC, not t0+192 h. Discovery only. Optional later **B** eval track if rasters are used under NC research rules — **not implemented** |
| Giezendanner ↔ GFD | **D** | Derived 8-day fraction vs observed event-max |
| GFM ↔ DFO | **C** | Catalog, no pixels |
| GFD ↔ DFO | **C** | GFD is DFO’s mapped subset |

No pair is **A** (unified training labels). Strategy C (harmonized intersection/union) is **not** implemented.

---

## 16. Resolution compatibility

Do not upsample 500 m or 250 m and call it 20 m truth.

| Track | Native grid | Role |
| --- | --- | --- |
| GFM-only high-resolution benchmark | 20 m Equi7 → 64×64 AOI | **Keep** |
| GFD event-max (if ever used) | 250 m | separate coarse research track |
| Giezendanner (if ever acquired) | 500 m 8-day fraction | separate historical climatology, never OBSERVED |

**Recommendation:** GFM-only 20 m as the training/eval spatial benchmark. Historical DFO/GFD events stay in the **event registry**. A coarse-resolution historical benchmark is a future optional Strategy B, not this phase.

---

## 17. Gate B result

**Official Gate B: FAIL** (`15 < 20`). Floor unchanged.

Research recommendation (registry, not a silent official change):

| combined independent events | band |
| --- | --- |
| 36 | **RESEARCH-USEFUL (30–39)** |

That band describes **real-world event discovery**, not cube-eligible training samples. Training labels remain 15 GFM events.

---

## 18. Gate F result

**Official Gate F: PASS** (unchanged from 6.5B: 8 valid GFM AOIs).

DFO/GFD “Bangladesh” tags do not add AOI diversity to the 64×64 tensors. Sylhet still has only two GFM events.

---

## 19. Provenance audit

Every registry row stores source, family, label kind, source_event_id, license, retrieval time, processing version `phase6.5-multisource-event-v1`, and matched GFM id when applicable.

GFD metadata citation: Tellman et al., Nature 2021; QC file `gfd_qcdatabase_2019_08_01.csv` (CC BY-NC). No flood rasters stored.

DFO citation: floodobservatory.colorado.edu Bangladesh listing, retrieved 2026-09-02.

Giezendanner: DOI 10.25739/2edm-jh03; access failure recorded, not fabricated.

GFM: existing v2.1 scene checksums / event records.

No SIMULATED/DEMO row is `accepted` as REAL.

---

## 20. Recommendation for the next phase

**Choose B:** keep GFM as the only training-label family. Use DFO/GFD as an **event-discovery and planning** registry (which historical floods exist, which overlap GFM, which pre-2015 events would need a *different* label family if a coarse historical track is ever approved).

Do **not** choose D (harmonized multi-source training). The 20 m vs 250 m vs 500 m, scene vs event-max vs 8-day fraction, SAR vs optical vs derived, and NC licenses are incompatible.

Do **not** choose A (stop and redesign the target) yet: GFM remains the correct 192 h OBSERVED target. The floor failure is coverage, not the target definition.

Do **not** treat 36 combined events as Gate B PASS.

If a later phase wants pre-2015 maps, the scientifically honest path is Strategy B: a **separate 500 m or 250 m historical evaluation track**, native resolution, own metrics, own license card — never mixed into the GFM headline table.

Extending GFM years/tiles further is unlikely to reach 20 independent *meteorological* events on this Equi7 tile without weakening the 45-day rule (already shown in 6.5B). Pre-2015 unique events need a non-GFM label family that this study judged **not unifiable**.

---

## Harmonization strategies (section 9)

| Strategy | Verdict |
| --- | --- |
| **A — GFM training labels + others for discovery** | **Recommended and implemented (registry only)** |
| B — separate eval tracks per family | Scientifically valid later; not implemented (no GFD/Giezendanner rasters ingested) |
| C — harmonized multi-source pixels | **Rejected** |

---

## Final decision

**B. GFM + SECOND SOURCE FOR EVENT DISCOVERY ONLY**

Training is not authorized even though the discovery registry contains 36 independent real-world events.

SOLVER MODIFIED: **NO**

SPATIAL AI: **NOT_VALIDATED**
