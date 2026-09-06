# PHASE 7.5 — AI Flood Assistant + Explainability + Evidence-Backed Planning

**Date:** 2026-09-03  
**Scope:** Context-aware, tool-first assistant over verified Phase 7.0–7.4 products.  
**Not in scope:** solver changes, model training, spatial AI enablement, invented measurements, official emergency orders.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Assistant architecture

- Deterministic tool selection from the user question plus compact application context.
- Tools execute backend functions already used by `/api/v1/*`.
- The reply copies tool JSON. It does not generate authoritative numbers.
- Conversation history is display-only. A previous sentence is not a new source of truth.

## 2. Context model

Compact verified state only:

`selected_region`, `selected_coordinates`, `selected_river`, `selected_segment`, `active_layers`, `active_scenario`, `baseline_id`, `scenario_id`, `forecast_horizon`, `current_data_status`, `selected_job`, `role`

Absent items are `null` / UNAVAILABLE. `role` is taken from the Authorization header, never from the JSON body.

## 3. Tools

Existing: region, risk, forecast, river status/forecast, infrastructure, flood extent, scenario run/compare, population, data source/freshness, report.

Added (genuine backends only):

| Tool | Backend |
|---|---|
| `explain_risk` | P×E×S formula decomposition (`RULE_FORMULA`, not SHAP) |
| `explain_forecast` | Heuristic method notes |
| `explain_physics` | Job computational chain |
| `get_spatial_ai_status` | Catalog freeze (does not run spatial inference) |
| `get_impact` | Phase 7.3 `region_impact` |
| `get_shelters` | Phase 7.3 shelter assessments |
| `get_planning_priorities` | Phase 7.3 resource priorities |
| `get_river_neighbors` | Topology neighbors |
| `get_historical_events` | Catalog metadata; observed extent null |

## 4. Tool authorization

| Tool | Permission |
|---|---|
| `run_scenario` | `jobs.write` (Emergency/Researcher/Admin) |
| `generate_report` | `reports.write` |
| impact/planning/population | `impact.read` |
| risk/forecast/explain | `risk.read` / `forecast.read` |
| river/compare/history | `map.read` |

Natural language cannot grant a missing permission. Denied tools return `FORBIDDEN` and are listed in `authorized_denied`.

## 5. Tool-result handling

- Numerical statements use `_copy_num` (JSON dump of the tool value).
- Failed simulations emit **SIMULATION FAILED** with job id and error.
- Scenario multipliers are parsed from language (`+30%` → `1.30`) and validated in `[0, 10]` before `enqueue_job`.
- The LLM does not mutate simulation state except through that tool.

## 6. Explainability

| Kind | When used |
|---|---|
| A. RULE / FORMULA | Risk P×E×S; heuristic forecast growth |
| B. MODEL FEATURE IMPORTANCE | Not available |
| C. MODEL-SPECIFIC ATTRIBUTION | Not available (not called SHAP) |
| D. DATA-QUALITY | Missing raster, UNAVAILABLE gauges, catalog-only history |

Heuristic forecasts are labeled **METHOD: HEURISTIC** and **not trained from data**. Physics replies describe forcing, terrain, initial state, model, scenario parameters, and simulation seconds.

## 7. Scenario integration

“Increase rainfall by 30%” → identify region → baseline ×1.0 (or context `baseline_id`) → scenario ×1.30 → compare → copy applied rates / depths / `river_level_applied_to_solver=false`.

## 8. Impact integration

Hospital/school/road questions use Phase 7.3 impact tools. Population remains UNAVAILABLE with the configured-dataset reason.

## 9. Planning support

Framed **AI-GENERATED PLANNING SUPPORT** with WHAT / WHY / EVIDENCE / LIMITATIONS.  
Never “Evacuate now.” Resource inventories stay UNAVAILABLE.

## 10. Unavailable-data handling

Population, water level, discharge, shelter capacity/occupancy/accessibility, spatial AI, observed flood extents: copied as UNAVAILABLE / NOT_COMPUTED / NOT_VALIDATED. Not estimated.

## 11. Uncertainty language

Probability, confidence, and uncertainty stay distinct.  
**CONFIDENCE: NOT_CALIBRATED.** Heuristic `confidence` fields are not treated as calibrated skill.

## 12. Security / prompt injection

Phrases such as “pretend”, “assume the”, “population is”, “flood probability is” are flagged. Claimed numbers are not written into tool inputs or replies. Verified backend state is used.

## 13. Auditability

`platform_store.audit("assistant.chat")` records role, city, tools, denied tools, job ids, injection flag, and an 80-character question preview. Copy/export includes timestamp, region, scenario, method, evidence, limitations.

## 14. Frontend UX

`AssistantDock` shows the user question, reply, real tool activity labels (after the backend returns), scenario/job status, expandable evidence/sources, copy analysis, and report export. No fake tool-call animation.

## 15. Tests

`tests/test_phase75_ai_assistant.py`: parsing, risk numbers, hospitals, general 403 on scenario, emergency 50% engine, population/water level, spatial AI, injection, planning language, reports, context role override, frontend contracts.

## 16. Browser/E2E

Live `/api/v1/assistant/chat` after uvicorn reload:

| Question | Role | Tool |
|---|---|---|
| What is the current risk? | general | `get_current_risk`, `explain_risk` |
| Which hospitals are exposed? | general | `get_infrastructure_risk`, `get_impact` |
| What happens if rainfall increases by 30%? | emergency | `run_scenario` completed, multiplier 1.3, river coupling false |
| How many people are exposed? | general | `get_population_exposure` (`null`) |
| What is the river water level? | general | `get_river_forecast` |
| Tell me the spatial AI flood map | researcher | `get_spatial_ai_status` NOT_VALIDATED |
| What should emergency planners prioritize? | emergency | `get_planning_priorities` |

Cursor browser MCP was unavailable in this session; UI contracts are in `test_frontend_assistant_contracts` and `npm run build`.

## 17. Limitations

- Tool routing is keyword-based, not an LLM planner.
- Compact context is not a full session memory of prior tool JSON.
- Historical events remain catalog metadata.
- River observations remain UNAVAILABLE without gauges.

## 18. Future work

Phase 7.6: historical replay, forecast vs reality, model performance center. Optional later: retrieval over reports, calibrated confidence, population provider.
