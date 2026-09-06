# PHASE 7.4 — Scenario Simulation + Digital Twin Workspace

**Date:** 2026-09-03  
**Scope:** Dedicated Simulation/Scenario workspace on the Phase 7.0–7.3 command center, using the existing jobs/artifacts/physics adapter.  
**Not in scope:** SWE solver changes, river-boundary coupling, spatial AI, model training, fabricated rainfall/population/impact numbers.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |
| `river_level_applied_to_solver` | **false** |

---

## 1. Scenario workspace

- Dedicated **Simulation** view (Emergency / Researcher / Admin).
- Layout: top = name / region / baseline / status; left = scenario controls; center = map; right = summary + history; bottom = comparison / impact / provenance.
- Existing Explore, River, and Impact workspaces remain intact.
- Legacy `ScenarioPresets` / local SWE `/api` runner remain in `App.jsx` (hidden while the Simulation workspace is open).

## 2. Supported controls

| Control | Status | Semantics |
|---|---|---|
| `rainfall_multiplier` | **SUPPORTED** | `effective_mps = base_rate_mps × rainfall_multiplier` in `run_physics` |
| Presets | +10 / +20 / +30 / +50 / +100% and baseline ×1.0 | Stored as explicit multipliers (e.g. 1.30) |

A +30% run is successful only when `rainfall_rate_applied_mps == rainfall_rate_base_mps * 1.3`.

## 3. Unsupported controls

| Control | Status | Notes |
|---|---|---|
| `river_level_delta_m` | **PARTIAL** | Stored on the scenario record. **NOT CURRENTLY APPLIED TO SWE SOLVER.** UI: Solver coupling: NOT APPLIED. |
| Upstream discharge | NOT_IMPLEMENTED | No discharge boundary coupling |
| Drainage degradation | NOT_IMPLEMENTED | No drainage model |
| Land-use change | NOT_IMPLEMENTED | No roughness scenario |
| Terrain modification | NOT_IMPLEMENTED | DEM edits are not a control |
| Dam release | NOT_IMPLEMENTED | No reservoir forcing |

Do not treat stored river-level values as simulated depth change.

## 4. Job lifecycle

- `POST /api/v1/scenarios` queues `kind=scenario` and runs via `BackgroundTasks` → `run_job`.
- States: **QUEUED / RUNNING / COMPLETED / FAILED**.
- Public job view includes `job_id`, `scenario` name, `baseline_id`, region, model, timestamps, duration, status, artifact references, and `error` on failure.
- Backend `progress` is a lifecycle marker (0 / 0.1 / 1.0), **not** a solver percent. The UI does not display invented “75% complete”.

## 5. Artifact architecture

- Depth rasters stay in the artifact store (`put_depth_artifact`). Job JSON holds `artifact_id`, metrics, and provenance only.
- Overlay: `GET /api/v1/artifacts/{id}/overlay.png`.
- Difference rasters are a separate artifact (`kind=depth_difference`), not inline arrays.

## 6. Baseline vs scenario

- Baseline payload: region/AOI, available forcing, adapter initial state, model/method, dataset, timestamp, configuration, assumptions. Missing inputs stay UNAVAILABLE.
- Compare API (`POST /api/v1/scenarios/compare` and workspace `compare`) returns BASELINE / SCENARIO / DELTA.
- Deltas are `None` if either side lacks a metric. Missing values are not coerced to 0.
- Population exposure remains `null` / UNAVAILABLE.

## 7. Difference maps

- `GET /api/v1/scenarios/difference?baseline_job=&scenario_job=`
- Requires two compatible depth rasters (same shape). Otherwise UNAVAILABLE / NOT_COMPUTED.
- Metrics: newly flooded cells, reduced flood cells, mean/max absolute delta (0.05 m wet threshold).
- Visualization: absolute **SCENARIO − BASELINE**, diverging overlay. No interpolation of missing frames.

## 8. Timeline

- Only `available_times` from the physics job (simulation seconds).
- 6 / 12 / 24 / 48 / 72 h meteorological states are not manufactured.
- Expansion / recession / depth change use actual artifacts only.

## 9. Impact integration

- After completion, `GET /api/v1/impact?job_id=` reuses Phase 7.3.
- Infrastructure (roads, hospitals, schools, bridges, shelters) can be computed from the scenario raster.
- **POPULATION EXPOSURE: UNAVAILABLE.**

## 10. Risk comparison

- P, E, and S stay separate (`risk_from_physics`).
- P from flood fraction; S from max depth; E is the city prior (not population).
- Population is not substituted for E. Missing components stay UNAVAILABLE / NOT_COMPUTED.

## 11. Digital twin causal chain

INPUT → RAINFALL → RUNOFF / WATER RESPONSE → RIVER / FLOOD STATE → FLOOD EXTENT → INFRASTRUCTURE IMPACT → RISK

- Rainfall / runoff / extent / risk links are labeled SIMULATED when the job applied a multiplier and produced an artifact.
- **RIVER / FLOOD STATE: NOT MODELED** (no SWE river forcing).
- Unsupported relationships are labeled NOT MODELED rather than implied causality.

## 12. AI assistant integration

- “What happens if rainfall increases by 30%?” selects `get_region`, `run_scenario`, `compare_scenarios`.
- The tool runs the existing engine (baseline ×1.0 then ×1.3) and copies `rainfall_multiplier`, applied vs base rates, depths/area if present, `river_level_applied_to_solver=false`, and `population_exposed=null`.
- The reply does not invent an unsupported textual flood prediction. Failures are reported as SIMULATION FAILED.

## 13. Provenance

Every scenario result exposes:

- input / forcing source
- scenario parameters
- model / physics model version
- timestamp
- artifact id
- simulation job id
- `river_level_applied_to_solver=false`

Physics outputs are labeled **SIMULATED**, never LIVE/REAL flood maps. Shares keep “Analysis generated at [timestamp].”

## 14. Performance

- Scenarios run as background jobs, not in the browser.
- Large rasters are artifact references.
- UI polls job status.

## 15. Accessibility

- Controls have labels, fieldsets/legends, keyboard-focusable buttons, `aria-live` status, validation/failure text, and non-color status words (QUEUED / RUNNING / COMPLETED / FAILED / UNAVAILABLE / NOT APPLIED).

## 16. Browser/E2E

Intended UI path: SEARCH DHAKA → OPEN SIMULATION → SELECT BASELINE → RAINFALL +30% → RUN → QUEUED/RUNNING → RESULT → MAP → BASELINE VS SCENARIO → IMPACT → PROVENANCE → REPORT.

Live API after uvicorn reload (`127.0.0.1:8000`):

- `GET /api/v1/scenarios/capabilities` — rainfall SUPPORTED, river PARTIAL with `river_level_applied_to_solver=false`, others NOT_IMPLEMENTED.
- Scenario without rainfall ingest — job **FAILED** (`REAL rainfall unavailable`).
- After rainfall ingest: baseline ×1.0 applied 2.5e-07 m/s; rainfall ×1.3 applied 3.25e-07 m/s (= base × 1.3); artifact overlay 200; difference map available.
- Assistant “What happens if rainfall increases by 30%?” called `get_region`, `run_scenario`, `compare_scenarios` and copied applied rates plus `river_level_applied_to_solver=False`.
- Cursor browser MCP was unavailable in this session; UI contracts are covered by `test_frontend_scenario_workspace_contracts` and `npm run build`.

## 17. Failure cases

- Missing REAL/DEMO forecast rainfall: job **FAILED**, error visible, no cosmetic depth.
- Invalid multiplier (`< 0`): HTTP 422.
- Incompatible rasters: difference UNAVAILABLE / NOT_COMPUTED.
- Solver validation failure: job FAILED with diagnostic `error`.
- General role: POST `/api/v1/scenarios` 403 (`jobs.write`).

## 18. Known physics limitations

- Short SWE burst; clock is simulation seconds.
- Uniform rainfall field × SIMPLE_RUNOFF_BASELINE, then multiplier.
- Synthetic DEM allowed only when requested; labeled.
- `river_level_delta_m` is **not** SWE forcing.
- Population grids are not ingested.
- Spatial AI remains NOT_VALIDATED / UNAVAILABLE.

## 19. Future coupling work

River-level (and discharge / drainage / land-use / terrain / dam) forcing belongs to a **separate, scientifically justified research phase**. Phase 7.4 must not set `river_level_applied_to_solver = true` to complete a UI checklist.

---

## APIs added

- `GET /api/v1/scenarios/capabilities`
- `GET /api/v1/scenarios/baseline`
- `GET /api/v1/scenarios/history`
- `GET /api/v1/scenarios/workspace`
- `GET /api/v1/scenarios/causal-chain`
- `GET /api/v1/scenarios/difference`

Existing `POST /api/v1/scenarios` and `POST /api/v1/scenarios/compare` remain. Reports accept optional `baseline_job` / `scenario_job`.

## Tests

`tests/test_phase74_scenario_digital_twin.py`: creation/validation, rainfall +30% applied-rate check, river coupling flag, job failure visibility, artifacts, compare/difference/impact/report/share, assistant tool copy, frontend contracts, spatial AI fail-closed.
