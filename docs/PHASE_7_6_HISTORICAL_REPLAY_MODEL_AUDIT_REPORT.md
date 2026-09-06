# PHASE 7.6 — Historical Flood Replay + Forecast vs Reality + Model Performance Center

**Date:** 2026-09-03  
**Scope:** Observation + audit workspace over GFM event metadata, Target-B transition pairs, the existing model registry, and genuine platform artifacts.  
**Not in scope:** fabricated historical forecasts, invented flood maps or timestamps, solver changes, model training, spatial AI enablement.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Event catalog

- `GET /api/v1/history/events` merges:
  - **GFM** `gfm_events_v21.json` (16 indexed events). `name` is null; the UI label is `event_id` (e.g. `evt:2015-07-11`). Human-readable names are not invented.
  - **EMSR / holdout** rows from `historical_events_from_catalog()`. Published activation names are retained. `observed_flood_extent` remains null; polygons were not downloaded.
- Catalog fields: `event_id`, `name`/`label`, `start`, `peak`, `end`, `regions`, `flood_mechanism`, `observation_source`, `n_observations`, `data_status`.
- Filters: year, region, flood mechanism, source, model, status.
- Legacy `GET /api/v1/historical-events` is unchanged (catalog-only, extents null).

## 2. Replay system

- Dedicated **History** workspace: left catalog / model-performance tab, center Explore map (infrastructure context, no invented flood overlay), right event summary, bottom timeline + comparison.
- Lazy loading: event-level metadata first. GeoTIFFs are not bulk-loaded. Overlay is marked `overlay_available` only when the indexed file exists on disk.

## 3. Observation timeline

- Timestamps come from processed GFM scene `datetime` values and Target-B pair `t0`/`t1`.
- T-72h / T-48h / T-24h slots are not invented.
- Each displayed observation is labeled **OBSERVED** with source, timestamp, resolution, dataset version.
- Unknown GFM pixels (code 255) are never scored as dry.

## 4. Prediction artifact discovery

- `GET /api/v1/history/events/{id}/predictions` lists:
  - Platform jobs whose city overlaps the event regions, with semantic type from job `kind`.
  - AOI GBDT (`MODELLED_AOI_PROBABILITY`) — not a flood map.
  - Spatial AI (`EXPERIMENT`, status NOT_VALIDATED) — no operational map artifact.
- A raster is not treated as a forecast. Scenario and simulation jobs keep their types.

## 5. Compatibility rules

Before forecast-vs-reality, the engine checks: same event, same target definition, paired timestamp, compatible grid shape, compatible resolution (mismatch is labeled, not silently resampled), compatible flood threshold, compatible units, and forecast semantics (scenario/simulation/AOI/spatial-experiment are not FORECAST).

Failure: `COMPARISON: NOT_COMPARABLE` with reasons. Missing prediction: `UNAVAILABLE`.

## 6. Forecast vs reality

- Enabled only when a genuine FORECAST flood-map artifact is compatible with an observation.
- For current GFM events this workspace has **no issued historical flood-map forecasts**, so comparison is UNAVAILABLE / NOT_COMPARABLE.
- The comparison engine (`compare_binary_maps`) is tested with in-memory arrays: IoU, Dice/F1, precision, recall, Brier on jointly valid pixels. MAE/RMSE stay null for binary maps.
- Depth comparison: **UNAVAILABLE**. Observed GFM is binary extent; observed depth is not derived from flood extent.

## 7. Spatial error maps

- On compatible binary maps: TP, FP (false alarm), FN (missed flood), TN; unknown remains unknown.
- Difference is not called “error” unless semantics are compatible.
- Arrays stay out of JSON.

## 8. Timing error

- Without prediction timestamps: `UNAVAILABLE`.
- With sparse SAR scenes: status `COMPUTED_AT_SCENE_RESOLUTION`. Onset is the first available timestamp; sub-scene onset is not inferred. Lead/peak errors stay null unless both series exist.

## 9. Model performance center

- `GET /api/v1/models/performance` and the History / Research **Model performance** views.
- Headline metrics are named (AUPRC, Brier, CSI/F1) with dataset, split, horizon, and target. No “94% accurate”.
- AOI GBDT: validated **AOI flood-occurrence probability (MODELLED GloFAS Q exceedance)**, not a spatial flood map.
- Spatial AI: **STATUS: NOT_VALIDATED**. `metrics: null`.
- Small / zero-prevalence splits: **STATISTICAL POWER LIMITED**.

## 10. Model registry

- Existing registry records only (`registry.json`, spatial registry). No fictional versions.
- Each entry exposes model_id, version, task, training dataset, training/run id, status, validation status, limitations.
- Public spatial catalog status remains `NOT_TRAINED` until VALIDATED; scientific status is NOT_VALIDATED.

## 11. Uncertainty

- Displayed only as `calibrated` / `not calibrated` / `unavailable`.
- Metric scores are not converted into confidence values.
- Heuristic and GBDT products: not calibrated.

## 12. Assistant integration

| Question | Tool |
|---|---|
| What happened during this flood? | `get_historical_event` (+ catalog) |
| How well did the model perform? | `get_model_performance` |
| Compare prediction and reality. | `compare_forecast_vs_reality` |
| What was the biggest error? | `get_error_analysis` (only if comparable) |

If comparison is unavailable, the tool returns the reason. Results are not invented. Context includes `selected_event_id`.

## 13. Report integration

- `POST /api/v1/history/events/{event_id}/report` and `POST /api/v1/reports?event_id=`.
- Body includes event, timeline, observations, available predictions (with semantic type), comparison status, model information, limitations, provenance.
- **Forecast accuracy is omitted** when no compatible prediction exists (`forecast_accuracy: null`).

## 14. Provenance

- History payloads use `envelope()` (`PARTIAL` / `UNAVAILABLE`, never LIVE).
- Observation vs scenario vs simulation vs forecast remain distinct.
- DEMO/SIMULATED jobs are not converted to REAL.

## 15. Tests

`tests/test_phase76_historical_replay.py` covers catalog, event selection, actual timestamps, unknown-mask preservation, semantic types, compatibility, grid mismatch, metric calculation, spatial classes, timing error, model registry, unavailable comparison, scenario≠forecast, provenance, assistant tools.

Critical cases:

- Observation only → replay works, forecast comparison UNAVAILABLE.
- Compatible prediction + observation arrays → comparison works.
- Incompatible maps → NOT_COMPARABLE.
- Scenario job kind → never FORECAST.

## 16. Browser / E2E

Browser MCP was not used as a live automation host for this phase. API E2E via TestClient covers OPEN HISTORY (catalog) → SELECT EVENT → timeline timestamps → observation metadata → model performance → forecast vs reality UNAVAILABLE → historical report. Live curl against uvicorn is run after restart when the server is up.

## 17. Limitations

- GFM GeoTIFF overlays are typically UNAVAILABLE in this workspace (index metadata + Target-B pair metrics only).
- No retrospective flood-map forecast artifacts exist for GFM events; forecast-vs-reality is therefore unavailable, not fabricated.
- Physics/scenario jobs overlapping a city are inspectable as SIMULATION/SCENARIO, not historical forecasts.
- AOI GBDT cannot be compared to GFM binary extent (different target).
- Target B remains PARTIALLY FEASIBLE (NEWLY_FLOODED over measured scene gaps).
- Spatial AI remains NOT_VALIDATED; spatial API UNAVAILABLE.
- EMSR catalog events have no downloaded polygons.

---

**Solver modified:** NO  
**Next phase:** PHASE 7.7 — ALERTS + SAVED LOCATIONS + REPORTS + SHARING
