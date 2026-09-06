# Phase 6.8 — Forecastability and target reformulation

**Status:** DESIGN DOCUMENT. Not a training run. Not a VALIDATED claim. No invented 24–168 h GFM maps.

**Catalog:** Spatial AI remains **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` remains **UNAVAILABLE**.

**AOI GBDT:** VALIDATED status **unchanged** (separate registry, scalar AOI task).

**Solver:** `src/floodlens/numerical/**` is not modified by this design.

**GFM dataset version (unchanged):** `phase6.5-gfm-spatial-v2.1`

**Event registry version (unchanged):** `phase6.5-multisource-event-v1`

**Phase 6.7 classification (unchanged):** MIXED

**This phase does not train a model, does not acquire rasters, and does not change the frozen Track A cube.**

---

## Recommendation (letter)

**E — COMBINATION OF C AND D** (reformulate the spatial target **and** treat missing in-horizon forcing as a first-class gap).

| Letter | Meaning | Chosen? |
| --- | --- | --- |
| A | Keep 192 h + expand events | No. More events will not create 24 h labels or put rain into `(t0, valid_at]`. |
| B | Shorten horizon | No. See statement below. |
| C | Reformulate target | **Yes** (primary: consecutive-scene new inundation). |
| D | Add temporal/hydrological inputs first | **Yes** as a gap for any retained 192 h snapshot forecast (FORECAST-kind rain in the 8-day window, not recoded as OBSERVED). |
| E | Combination of B/C/D | **Yes: C+D, not B.** |
| F | Stop spatial forecasting with current data | No. GFM still supports an honest 8-day SAR-slot snapshot and an inter-scene change diagnostic. Stop claiming **6–72 h spatial maps**. |

**SHORTER HORIZON NOT SUPPORTED BY CURRENT GFM LABEL TEMPORAL RESOLUTION.**

**Primary target going forward: TARGET B** (newly flooded area between consecutive GFM scenes on jointly valid pixels). Frozen Track A occurrence@192 h remains a documented diagnostic cube. Do not delete it. Do not retrain it in this phase.

Do not train a U-Net, CNN, transformer, or hybrid model.

---

## Naming

| Label | Meaning here |
| --- | --- |
| Phase 6.5C **B** | GFM + second source for event discovery only |
| Phase 6.6 **Track C** | Cross-resolution *experiment protocol*, not a model |
| Phase 6.6 architecture **B** | Separate native-resolution stores + shared event registry |
| This document **TARGET B** | Newly flooded pixels between consecutive GFM scenes |
| This document letter **E** | Reformulate target + forcing-gap (not “shorten to 24 h”) |

---

## 1. Current forecast definition (traced)

Traced in `src/floodlens/ml/spatial/builder.py`:

```text
valid_at = parse_ts(scene["datetime"])          # GFM SAR acquisition clock
issue    = valid_at - timedelta(hours=HORIZON_HOURS)  # HORIZON_HOURS = 192
```

`HORIZON_HOURS = 192` is defined in `src/floodlens/ml/spatial/schema.py` as the **8-day GFM scene slot**, not 6/12/24 h. Leakage (`src/floodlens/ml/spatial/leakage.py`) fails if `|hours(valid_at − issue) − horizon| > 1`.

| Field | Exact value |
| --- | --- |
| `target_time` / `valid_at` | GFM `ensemble_flood_extent` scene datetime |
| `t0` / `issue_time` | `valid_at − 192 h` **by construction** |
| `forecast_horizon` | 192 h (`sample.horizon_hours`) |
| `input_end` | t0. Precip hours `h = 1, 2, …` are `t0 − h`. Exclusive of t0 and of `(t0, valid_at]`. |
| `input_start` | Lattice: t0 − **72 h** (`precip_maps_at_issue` in `precip_lattice.py`). AOI hourly vector: t0 − **24 h** (`LOOKBACK_HOURS` in `src/floodlens/ml/schema.py`). |
| `target_window` | **That one scene.** Working-cell flood if valid flood fraction ≥ τ = 0.25. Unknown = 255, never dry. |
| Persistence | Previous **same-AOI** GFM map with `persistence_valid_at < t0` (`builder.py`; `assert_persistence_is_lagged`). |

FORECAST-kind rain is forbidden in lookback. GloFAS Q is daily `t−7 … t−1` at t0 (MODELLED scalar). Splits are event-level (`splits_v2/splits.json`: 7 / 5 / 3).

### What “192 h” is

| Option | Verdict |
| --- | --- |
| A. Exactly 192 hours after t0 | **Yes.** Clock delta is exact by construction. |
| B. Event-max over a window | **No.** That is GFD, not GFM. |
| C. Weekly composite | **No.** That is Giezendanner Track B. |
| D. Offset relative to satellite acquisition | **Yes.** t0 is **not** an independent meteorological issue time. It is an 8-day back-offset glued onto whatever Sentinel-1 overpass exists. |

**192 h = A and D together.** It is an 8-day **SAR-slot snapshot**, not a 24 h nowcast and not a weekly mosaic.

### Forecast vs observation

A GFM map at time T is a valid **observation**.

A model at T+H is a **forecast** only if features stop strictly before T+H. For H = 192 that rule is implemented. The product still has no observed map at T+24, T+48, … T+168.

Rain in `(t0, valid_at]` is withheld. That is correct for a forecast and **fatal** for rain-driven haor inundation: the water that appears on the SAR scene often fell **after** t0. Phase 6.7 rainfall-only being the weakest ablation is the expected symptom, not a mystery.

This is **not** mere event-state reconstruction (the label is not an event-max). It **is** a dated snapshot forecast whose meteorological issue time is slaved to the satellite, 8 days early. Operational 6–72 h spatial maps remain **UNSUPPORTED**.

---

## 2. Temporal-label audit

Events are 45-day clusters (`EVENT_GAP_DAYS` in `events.py`). `event_start` / `event_peak` / `event_end` come from scene dates and flood-pixel peak, not from a hydrograph.

GFM timestamps are scene `datetime` strings in `processed_v2/index.json` / `events.json`. Rain lattice covers **2016-06-01 … 2024-08-31** (`precip_lattice.py`). 2015 events use point-rain fallback. `evt:2025-07-11` is GFM-indexed and **not cube-eligible**.

Persistence legality (current t0 rule):

- If revisit **&lt; 8 days**, the immediately previous scene has `valid_at > t0` and **cannot** be persistence. Example: `evt:2022-05-16` scenes 16 May and 18 May (Δ ≈ 2.5 d). For the 18 May target, t0 ≈ 10 May, so 16 May is **after** t0. Persistence skips the nearest observation.
- If revisit **&gt; 8 days**, persistence **is** the previous scene. Example: `evt:2023-06-16` cluster ≈ 12 d (16, 28 Jun, 10, 22 Jul, 3, 15 Aug). Persistence is ~4 days before t0 and ~12 days before the target.

A true shorter-horizon **GFM** target does not exist: there is no second observed map at t0+24 h, t0+48 h, etc. Consecutive pairs support a **different** task whose horizon is the actual Δt, not a product hour.

Test-event scene clocks (from `processed_v2/events.json`):

| Event | Scenes (UTC date in scene id) | Typical Δ |
| --- | --- | --- |
| `evt:2022-05-16` | 16 May, 18 May, 28 May, 3 Jul | ~2.5 d, ~10 d, ~36 d |
| `evt:2023-06-16` | 16, 28 Jun; 10, 22 Jul; 3, 15 Aug | ~12 d |
| `evt:2024-06-22` | 22 Jun, 24 Jun, 4, 16, 28 Jul, 9 Aug, 11 Aug | ~2.5 d then ~12 d |

---

## 3. Horizon-support matrix

Reusing the same GFM raster as a “24 h label” is forbidden (`invented_subdaily_label` in `leakage.py`).

| Horizon | Classification | Reason |
| --- | --- | --- |
| 24 h | **UNSUPPORTED** | No GFM observation at t0+24. |
| 48 h | **UNSUPPORTED** | Same. |
| 72 h | **UNSUPPORTED** | Same. |
| 96 h | **UNSUPPORTED** | Same. |
| 120 h | **UNSUPPORTED** | Same. |
| 144 h | **UNSUPPORTED** | Same. |
| 168 h | **UNSUPPORTED** | Same. |
| 192 h | **SUPPORTED** as 8-day SAR-slot snapshot | Clock and leakage already match. **Misaligned** with FLOODLENS 6–72 h API. |
| Variable Δt = actual scene gap | **PARTIALLY SUPPORTED** as a **different** task | Consecutive pairs exist. Horizon is not a fixed product hour. |

**SHORTER HORIZON NOT SUPPORTED BY CURRENT GFM LABEL TEMPORAL RESOLUTION.**

FLOODLENS-X should **not** prioritize 24/48/72 h spatial GFM maps. It may keep 192 h as a research snapshot task and add a consecutive-scene change task whose H equals measured Δt (often ~6–12 d, sometimes ~2 d orbit twins or 30 d+ gaps).

---

## 4. Persistence analysis design

Phase 6.7: GBDT **with** persistence ties persistence IoU exactly at threshold 0.5 (copies the lag map). GBDT without persistence loses on 6/8 held-out events. Climatology is strongest on point estimates.

**Why persistence can look strong**

1. **Real inundation memory.** Haor/monsoon water can remain for weeks. Consecutive-scene IoU can be high for physical reasons.
2. **Target-definition artifact.** t0 = valid_at − 192 h can **forbid** the nearest previous scene as a feature (revisit &lt; 8 d) or force a **12-day-old** map as “current state” (revisit &gt; 8 d). The model is not always seeing “the last map before the flood.”
3. **Seasonal location prior.** AOI×month climatology beating persistence on test (`evt:2022-05-16` climatology IoU 0.454 vs persistence 0.159) shows “this cell floods in May” can outperform a stale or skipped lag map.

Both (1) and (2) can be true. They must be separated with **observed sequences only** (no training, no future features).

### Protocol (not run in this documentation phase)

For each Track A event, per AOI, consecutive scenes k → k+1:

- Δt hours; whether scene k is **legal persistence** for scene k+1 under current t0 = valid_at − 192 h
- Flood-area persistence; newly flooded / receded fractions
- IoU(k, k+1) on **jointly valid** pixels (255 never dry)
- Unknown overlap
- Centroid of flood pixels only if n_flood is large

**A vs B:** high IoU(k, k+1) with long Δt → genuine persistence. GBDT copying persistence **and** a high fraction of samples whose nearest scene is after t0 → 192 h back-offset artifact.

Do not put scene k+1 rain or the target map into features. Rain in `(valid_at_k, valid_at_{k+1}]` may be tabulated as a **diagnostic association** only.

---

## 5. Candidate target comparison

| ID | Target | Label availability | Usefulness | Forecastability | Leakage | Baseline difficulty | FLOODLENS-X | Compatibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Flood state at exact T+H | Only H=192 with GFM | Aligns with current cube | 8-day snapshot; rain in gap withheld | Low if current gates hold | Hard vs persistence/climatology (6.7) | Not 6–72 h | Current Track A |
| **B** | **Newly flooded between consecutive GFM scenes** | **Yes, from existing maps** | Attacks “copy last map” | Horizon = Δt, not 24 h | Rain **between** scenes is future unless FORECAST-kind | Persistence of *change* should be near zero if defined as new flood | Medium-range inundation change, still not 24 h | Uses frozen GFM pairs; no new rasters |
| C | Expansion probability | Same pairs (soft B) | Ranking/calibration | Same as B | Same | Secondary | Research | Same |
| D | Persistence probability | Same pairs | Easy; may clone 6.7 | Low leakage | Too easy | Diagnostic only | Same |
| E | Flood-depth change | **No** GFM depth | Physics-adjacent | n/a | n/a | **UNSUPPORTED** | Solver still incomparable (Gate J) |
| F | Multi-horizon | Requires invented maps | Product-shaped | n/a | High | **UNSUPPORTED** | Forbidden |
| G | Event-peak extent | GFM no; GFD NC event-max | Climatology of max | Not dated T+H | Structural | Track B-max RESEARCH-ONLY | Do not merge into Track A |

**Primary: TARGET B.** Frozen **A@192h** stays as the Phase 6.7 diagnostic cube. TARGET C is a secondary metric on the same pairs. TARGET D is a control (should be easy). E/F unsupported. G stays off the GFM training path.

If TARGET B is ever trained (later phase, separate approval): t0 must be scene k (or immediately after it). Rain between k and k+1 is **not** OBSERVED lookback. NWP in that window would be FORECAST-kind, same rule as Phase 4 AOI GBDT.

---

## 6. Feature availability

| Input | Status | Notes |
| --- | --- | --- |
| rainfall[x,y,t] | **PARTIAL** | 3×3 ERA5-Land / Open-Meteo lattice ~11 km; 2016-06-01 … 2024-08-31; hourly **before t0** only |
| Antecedent 24/72 h, 24 h intensity | **AVAILABLE** | Ends at t0 |
| Rain accumulation / intensity after t0 | **UNAVAILABLE** on purpose | OBSERVED leak if used; NWP would be FORECAST-kind (not in spatial cube) |
| Terrain, slope | **AVAILABLE** | Static |
| River distance, mask, height-above-river | **AVAILABLE** | HydroRIVERS or OSM; static |
| River discharge | **PARTIAL** | GloFAS Q, tile scalar, 7 daily values before t0, MODELLED |
| River **level** | **UNAVAILABLE** | Do not synthesize |
| Soil moisture | **UNAVAILABLE** | Do not synthesize |
| Land cover | **UNAVAILABLE** | Do not synthesize |
| Flow accumulation / upstream routing | **UNAVAILABLE** | Do not synthesize |
| Prior flood state | **PARTIAL** | Lagged GFM; may not be the nearest scene |

Do not add synthetic substitutes.

### Temporal history (source frequency only)

| Window | Spatial rain lattice before t0 | Q | GFM state |
| --- | --- | --- | --- |
| 6 / 12 / 24 h | Supported (hourly) | no | no |
| 48 / 72 h | Supported in 72 h maps / cube | no | no |
| 7 d | Not a dense spatial cube | **PARTIAL** (scalar) | no |
| 14 d | **UNSUPPORTED** (do not interpolate) | no | only if a previous scene happens to fall there |

Minimum history to *represent* antecedent rain is already 24–72 h **before t0**. That does **not** represent rain that builds the flood **during** the 8-day SAR offset. Hydrological buildup and recession at 6–72 h **product** scales are not observed as GFM maps.

### State representation (not implemented)

| Recipe | 6.7 evidence |
| --- | --- |
| Current weather only | Weakest ablation (rainfall-only event-macro IoU 0.053 on val+test) |
| Weather + antecedent + flood state | GBDT-all **is** this; it copied persistence |
| Weather + antecedent + flood state + hydrology | Q is already a scalar; adding more scalars will not create 24 h labels |

Persistence is strong **despite** an explicit lagged flood channel. The gap is **in-horizon rain/hydrology** and/or a **change** target, not “forgot to pass the last map.”

---

## 7. Would more events solve it?

Do not conclude “need 50 more events” as the primary action.

| Rank | Blocker | Code |
| ---: | --- | --- |
| 1 | Label temporal resolution: no 24–168 h GFM maps; 192 h is an 8-day SAR offset | **E** |
| 2 | Insufficient temporal forcing in the forecast window (causal rain often after t0) | **C** |
| 3 | Wrong target for the 6–72 h product (occurrence@192 h ≈ persist/climatology) | **B** |
| 4 | Thin hydrological state (scalar Q; no wetness/routing) | **D** |
| 5 | Too few events (15; test 3) | **A** |

**A is real and secondary.** Official Gate B still FAIL (15 &lt; 20). Expanding **winter residual** clusters will not create daily labels or in-gap rain. Expanding monsoons helps power for TARGET B / A@192h diagnostics, not 24 h GFM forecasts.

---

## 8. Forecastability test (no training)

Question: *Is the future GFM state distinguishable from persistence using causal information available at the chosen t0?*

Diagnostics (later phase, not this file’s implementation):

1. Scene-gap and persistence-legality table for all 15 events.
2. Turnover / IoU(k, k+1) on jointly valid pixels (val and test AOIs).
3. Association: rain **before t0** vs rain **in (t0, valid_at]** vs flood-area change. Rain-in-gap is **not** a model feature.
4. Distance-to-river vs newly flooded pixels on consecutive pairs.
5. Event-conditioned correlation of flood fraction(k) vs flood fraction(k+1).

These are not Gate G training metrics. No GBDT retune. No CNN.

If (3) shows flood change tracks **in-gap** rain and not pre-t0 rain, TARGET A@192h is forecastable in principle **only** with FORECAST-kind rain in the window (or it is the wrong target). If (2) shows high IoU(k, k+1), TARGET B is the honest residual.

---

## 9. Track B implication

Classify Track B as a **HISTORICAL EVENT BENCHMARK**, not a 192 h GFM forecast twin.

| Source | Timing | Forecast role |
| --- | --- | --- |
| Giezendanner 500 m 8-day fraction | Composite window | Hindcast of **next composite** only if t0 is before composite start; else leakage. Not GFM 192 h. **UNAVAILABLE** rasters. |
| GFD 250 m event-max | Whole DFO date range | Dated map at t0+H: **UNSUPPORTED**. Optional NC event-max task. |
| DFO catalog | News/gov dates | Discovery only; no pixels. |

If Giezendanner is ever acquired: keep native 500 m; never upsample to GFM 20 m / 64×64 as truth. Architecture remains Phase 6.6 **B** (shared registry, separate stores).

---

## 10. Track C implication

**DELAY (outcome B).** Do not design a multi-resolution net.

Transfer of coarse history onto GFM occurrence@192 h would mix incompatible targets (snapshot vs 8-day composite vs event-max) and inherit the rain-gap. Track C stays a protocol after Track A has an honest change task or an 8-day snapshot **with** documented FORECAST forcing. Pairs remain C/D not A (Phase 6.5C). n = 15 still cannot separate transfer from event identity.

**A Track C remains promising** — not at this target. **C reject** — too strong; the registry architecture stays. **D permanently separate stores** — already the 6.6 decision; unchanged.

---

## 11. Scientific decision tree

```text
IF A@192h clock is valid AND 6–72 h product alignment is required
  → A@192h is product-invalid; do not keep it as the only spatial goal.

IF causal features for A@192h omit rain in (t0, valid_at]
  → expanding events is the wrong next move; forcing gap or target change first.

IF persistence dominates because inundation is stable AND/OR nearest scene is illegal at t0
  → investigate TARGET B (change / new inundation) on consecutive scenes.

IF a fixed 24–168 h GFM map is required
  → UNSUPPORTED; do not invent rasters.

IF no defensible GFM forecast exists at any horizon
  → false: 8-day snapshot and Δt-change remain defensible research tasks.
  → true for 6–72 h spatial maps: stop claiming them.
```

---

## 12. Proposed experiments (later; not this PR)

| # | Experiment | Training? |
| --- | --- | --- |
| 1 | Persistence-legality + scene-gap table (15 events) | No |
| 2 | IoU / new-flood / recede on consecutive pairs | No |
| 3 | Pre-t0 rain vs in-gap rain vs area change (association) | No |
| 4 | River-distance vs new-flood pixels | No |
| 5 | TARGET B diagnostic baselines (persistence-of-zero-change, climatology of expansion) | Only if separately approved; still not VALIDATED |

No U-Net. Optional later module: `src/floodlens/ml/spatial/phase68.py` + `scripts/phase68_forecastability.py`. **Not created in this phase** (doc-only, same as 6.6).

---

## 13. Proposed gates (not VALIDATED)

| Gate | Rule |
| --- | --- |
| 6.8A | Horizon honesty: 24–168 h UNSUPPORTED; no invented rasters |
| 6.8B | Persistence legality: report fraction of samples whose nearest previous scene is after t0 |
| 6.8C | Change-target feasibility: enough consecutive pairs with jointly valid pixels |
| 6.8D | Forcing gap: document rain-in-window vs rain-before-t0 (diagnostic) |
| 6.8E | Track B labeled historical, not GFM-192 h forecast, unless a causal 8-day composite task is defined |

Class: **FORECASTABILITY AUDIT**. Not DIAGNOSTICALLY PROMISING. Not VALIDATED. Official Gates A–J unchanged (B still FAIL on 15 events; J still NOT COMPARABLE).

---

## 14. Recommended feature state

For **retained A@192h diagnostics:** keep the frozen 18 causal columns; do not add in-gap OBSERVED rain.

For **TARGET B (next diagnostic):** scene k as explicit current state; rain and Q **strictly before t0 = valid_at_k** (or immediately after k, still before k+1); static terrain/rivers. In-gap rain only as FORECAST-kind if a later phase introduces NWP, never as lookback OBSERVED.

Do not implement that cube in this phase.

---

## 15. Files

**This phase creates:** `docs/PHASE_6_8_FORECASTABILITY_DESIGN.md` only.

**Do not change:** solver, APIs, `processed_v2` tensors, frozen splits, spatial registry VALIDATED flags, AOI GBDT VALIDATED, training scripts, Phase 6.7 artifacts.

**Later (separate approval):** persistence/turnover diagnostics; TARGET B label construction from existing GFM pairs; optional FORECAST-kind rain study. Still no CNN.

---

## 16. Limitations

- Consecutive-scene Δt is not a 24 h product horizon.
- TARGET B still cannot power `/forecast/ai-spatial` at 6–72 h.
- Unknown ~36% will shrink jointly valid pixels for change maps.
- Orbit twins (~2 d) and long gaps (~36 d) must be stratified, not pooled.
- Climatology win in 6.7 is a location prior, not an 8-day event forecast.
- Giezendanner remains UNAVAILABLE; GFD NC.

---

## Final decision

RECOMMENDED LETTER:
E (reformulate to TARGET B + treat in-horizon forcing as a gap; do not shorten GFM to 24 h)

PRIMARY TARGET:
TARGET B — newly flooded area between consecutive GFM scenes (horizon = measured Δt)

RETAINED DIAGNOSTIC:
Track A occurrence at t0+192 h (frozen cube; not deleted; not retrained here)

SHORTER HORIZON:
NOT SUPPORTED BY CURRENT GFM LABEL TEMPORAL RESOLUTION

MORE EVENTS:
SECONDARY BLOCKER (official Gate B still 20; does not fix 24 h or rain-after-t0)

TRACK B:
SEPARATE HISTORICAL BENCHMARK (not a 192 h GFM forecast twin)

TRACK C:
DELAY until Track A target is honest (change task or 8-day snapshot with documented FORECAST forcing)

MODEL TRAINING:
NOT AUTHORIZED

SPATIAL AI:
NOT_VALIDATED

SPATIAL API:
UNAVAILABLE

TRACK A:
DIAGNOSTIC ONLY

TRACK C:
NOT YET IMPLEMENTED

SOLVER MODIFIED:
NO

NEXT PHASE:
No-training persistence-legality and consecutive-scene turnover diagnostics (separate approval). Do not train a U-Net. Do not invent 24 h GFM maps.

END.
