# PHASE 7.0 — Command Center + Core User Experience

**Date:** 2026-09-03  
**Scope:** Product command-center UX around currently available capabilities.  
**Not in scope:** spatial AI training, enabling `POST /api/v1/forecast/ai-spatial` as a product, Target B training, numerical solver changes, GFM/event/scientific-gate edits.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Features completed

- Command-center shell: FloodLens-X header, location search, clock/freshness, DEMO role selector, view navigation.
- Primary layout: risk rail, Leaflet map, forecast/event timeline, secondary alerts / jobs / model status / data health / KPIs.
- Capability matrix with AVAILABLE / PARTIAL / DEMO / SIMULATED / UNAVAILABLE / EXPERIMENTAL language.
- Current risk as P × E × S (LOW / MODERATE / HIGH / CRITICAL), explicitly not “confidence.”
- Honest heuristic forecast hours (6/12/24/48/72) labeled DEMO; expected depth/flooded area UNAVAILABLE when null.
- Timeline of meteorological hours plus Spatial AI tile UNAVAILABLE / NOT_VALIDATED. Time-indexed flood states shown only if `/api/v1/flood-states` returns them.
- River graph selection, upstream/downstream topology, WATER LEVEL / DISCHARGE UNAVAILABLE (no invented gauges).
- OSM infrastructure bbox fetch with clustering; hospital/school/road/bridge filters.
- River network polylines from fixture/OSM segment coordinates (topology + geometry; no Q/level).
- Impact panel: POINT / LINE / POLYGON / ACCESSIBILITY status; POPULATION EXPOSURE: UNAVAILABLE.
- Provenance badges on risk, forecast, layers, jobs, alerts, reports, models.
- Model status: Spatial AI NOT_VALIDATED; Spatial API UNAVAILABLE; AOI GBDT is not an “AI flood map.”
- Role split: General / Emergency / Researcher / Admin using existing `demo.<role>` IdP.
- Recent simulations (QUEUED / RUNNING / COMPLETED / FAILED) for roles with `jobs.read`.
- Reports panel (JSON region report; population impact available=false).
- Panel states: LOADING / SUCCESS / EMPTY / ERROR / UNAVAILABLE / STALE / DEMO / SIMULATED.
- Location search: country/city/district/river/neighborhood/coordinates; autocomplete; map fly-to.
- Accessibility: skip-to-map, combobox/listbox search, aria-labels, focus-visible, live regions on error/unavailable.

## 2. Features partially available

| Capability | Status | Honest product meaning |
|---|---|---|
| Current flood map | PARTIAL | Overlay only after a completed physics/scenario job. Otherwise no current flood raster. |
| Forecast | PARTIAL | Heuristic 6–72h points are DEMO hours, not spatial flood maps. Physics baseline is a short SWE burst. |
| Flood depth | PARTIAL | Only on a completed physics artifact. |
| Infrastructure | PARTIAL | OSM points/lines when ingested (fixture fallback labeled DEMO). Per-feature depth NOT_COMPUTED until impact on a raster. |
| AI forecast (AOI) | PARTIAL | Validated AOI GBDT is a scalar AOI probability task, not a flood map. |
| Uncertainty | PARTIAL | Heuristic `confidence_kind`, not a calibrated spatial CI. |
| Historical replay | PARTIAL | Playback after a local run. EMSR extents remain null. |
| Reports | PARTIAL | JSON region reports; population impact available=false. |
| Alerts | PARTIAL | In-app evaluate only, not an operational warning service. |
| AI assistant | PARTIAL | Tool-calling; does not invent numbers. |
| Physics / scenario | SIMULATED | Short SWE burst; river-boundary coupling not enabled. |

## 3. Unavailable capabilities

| Capability | UI / API behavior |
|---|---|
| Spatial AI flood map | NOT_VALIDATED. Timeline tile UNAVAILABLE. |
| `POST /api/v1/forecast/ai-spatial` | Endpoint remains fail-closed: job result `available=false`, `data_status=UNAVAILABLE`. Not a product overlay. |
| Validated 6–72h AI inundation maps | Explicit UNAVAILABLE copy. |
| River water level | WATER LEVEL: UNAVAILABLE |
| River discharge | DISCHARGE: UNAVAILABLE |
| Population exposure | POPULATION EXPOSURE: UNAVAILABLE (never 0 as a stand-in) |
| Terrain DEM in browser | Catalog may have metadata; no DEM raster is loaded. TERRAIN: UNAVAILABLE or “metadata only.” |
| Rainfall overlay | Toggle disabled when observations are UNAVAILABLE. No fake heatmap. |
| Jobs for General | jobs.read / jobs.write UNAVAILABLE. |
| Impact without a physics raster | Assess reports UNAVAILABLE rather than zeros. |

## 4. Routes / pages added

This remains a Vite SPA. No Next.js migration.

RoleShell views (not URL routes):

- `explore` — command center (all roles)
- `forecast` — forecast + model status (all roles)
- `simulation` — emergency / researcher / admin
- `impact` — emergency / admin
- `research` — researcher / admin
- `reports` — region report
- `alerts` — general / emergency / admin

## 5. Components added

| File | Role |
|---|---|
| `frontend/src/platform/capabilities.js` | Product capability matrix |
| `frontend/src/platform/CapabilityMatrix.jsx` | Research-mode matrix |
| `frontend/src/platform/PanelState.jsx` | LOADING/EMPTY/ERROR/UNAVAILABLE/… |
| `frontend/src/platform/ForecastTimeline.jsx` | Bottom meteorological timeline |
| `frontend/src/platform/AlertsPanel.jsx` | In-app alerts |
| `frontend/src/platform/ImpactPanel.jsx` | OSM impact + population UNAVAILABLE |
| `frontend/src/platform/JobsListPanel.jsx` | Recent simulations |
| `frontend/src/platform/DataHealthPanel.jsx` | Command + health (emergency/admin) |
| `frontend/src/platform/ResearchDiagnostics.jsx` | Compare + experiments |
| `frontend/src/platform/LayerLegend.jsx` | Layer status + toggles |
| `frontend/src/platform/ReportsPanel.jsx` | JSON region report |
| `frontend/src/components/RiverNetworkLayer.jsx` | River polylines from real segment coordinates |

Existing components reused: RoleShell, StatusPanel, ForecastPanel, RiverForecastPanel, ModelStatusPanel, DataSourcesPanel, AssistantDock, JobProgressPanel, FloodMap, LocationSearchBar, OsmInfrastructureLayer, ProvenanceBadge.

## 6. APIs used (no duplicate surface)

Existing `/api/v1/` endpoints only, plus existing `/api/cities` and `/api/geocode/search`:

- `GET /api/v1/status` (risk, forecast, layers, command KPIs)
- `GET /api/v1/catalog/layers`
- `GET /api/v1/data-sources`
- `GET /api/v1/forecast`, `POST /api/v1/forecast/physics`, `POST /api/v1/forecast/ai`
- `POST /api/v1/forecast/ai-spatial` (fail-closed UNAVAILABLE result; not enabled as a product)
- `GET /api/v1/flood-states`
- `GET /api/v1/rivers`, `GET /api/v1/rivers/{id}/state`
- `GET /api/v1/observations?variable=precipitation_mm`
- `GET /api/v1/infrastructure` (bbox-capped)
- `POST /api/v1/impact/assess`
- `GET /api/v1/alerts/evaluate`
- `GET /api/v1/jobs`, `GET /api/v1/models`, `GET /api/v1/health`
- `GET /api/v1/command` (command.read)
- `GET /api/v1/research/compare`, `GET /api/v1/experiments`
- `POST /api/v1/reports`
- `POST /api/v1/assistant/chat`

Additive, backward-compatible: `GET /api/v1/rivers` now includes `segments` (coordinates when present) on each river object.

## 7. Tests

| Suite | Result |
|---|---|
| `tests/test_phase70_command_center.py` | passed |
| `tests/test_platform_frontend_contract.py` | passed |
| `tests/test_location_search_frontend_contract.py` | passed |
| `tests/test_platform_e2e.py` | passed (Playwright optional skipped) |
| `tests/test_phase5_api.py` | passed (spatial still UNAVAILABLE) |
| Full backend: `pytest tests --deselect tests/test_phase4_baselines.py::test_xgboost_beats_persistence_track_a_and_b` | **412 passed, 7 skipped, 1 deselected** |
| Frontend `npm run build` | **success** (Vite 6.4.3) |

Phase 7.0 tests cover: capability matrix, UNAVAILABLE population/level/discharge, P×E×S, roles, spatial fail-closed job result, no training hooks, no solver edits.

## 8. Browser / E2E result

Browser click-through on `http://127.0.0.1:5173` (Vite) with `http://127.0.0.1:8000` (FastAPI):

| Step | Result |
|---|---|
| OPEN DASHBOARD | Command Center loaded. Skip-to-map, search, role, map, timeline present. |
| SEARCH DHAKA | Autocomplete: Dhaka city, Mirpur neighbourhood/suburb. |
| MAP ZOOMS | City switched to Dhaka; OSM bbox fetch returned 7 features, then 2 after hospital filter. |
| CURRENT FLOOD STATE | No physics raster; max depth / flooded area UNAVAILABLE (not zeros). |
| VIEW RISK | LOW; Probability × Exposure × Severity; source risk-service; DEMO freshness. |
| VIEW AVAILABLE FORECAST | DEMO heuristic hours; expected depth UNAVAILABLE; spatial maps UNAVAILABLE. |
| TOGGLE RAINFALL | Control **disabled**; RAINFALL: UNAVAILABLE (no fake overlay). |
| TOGGLE RIVERS | River layer checkbox present and checked; Leaflet stacking initially intercepted clicks (legend z-index raised to 1100). Network drawn from fixture segments. |
| SELECT INFRASTRUCTURE | OSM type filter → hospital (2 features, bbox-capped). |
| OPEN IMPACT PANEL | Emergency role → Impact. Requires physics job; otherwise UNAVAILABLE. |
| VIEW PROVENANCE | DEMO/SNAPSHOT/UNAVAILABLE badges on sources, layers, forecast, models. |
| OPEN SIMULATION / JOBS | Emergency Simulation view; Recent simulations EMPTY (no session jobs). |
| SWITCH TO RESEARCH | Role selector exposes Research for researcher/admin (nav verified). Browser MCP dropped before the last two clicks. |
| RETURN TO GENERAL | Role selector includes General; jobs remain UNAVAILABLE for that role. |

API journey (`tests/test_platform_e2e.py`) independently covers status → forecast → job → impact → assistant → report.

Overpass was rate-limited / tunneled; OSM fixture fallback labeled **DEMO**.

## 9. Performance findings

- No full DEM or GFM rasters shipped to the browser.
- Infrastructure uses bbox + limit 400 + clustering below zoom 13; lines capped at 80.
- Layer catalog and flood-states are small JSON.
- Vite production bundle: `index-r-wFgvqS.js` ≈ 404 kB (120 kB gzip). Acceptable for this SPA.
- Rainfall toggle does not fetch until enabled, and stays disabled when UNAVAILABLE.

## 10. Accessibility findings

- Skip-to-map link; `aria-label` on search, role, views, map, assistant, timeline, OSM filter, layer toggles.
- Search is a combobox + listbox with ArrowUp/Down/Escape.
- PanelState uses `aria-busy` and `aria-live` for ERROR/UNAVAILABLE.
- Focus-visible outline on controls.
- Remaining: Leaflet itself has limited keyboard map pan; OSM markers are pointer-driven. Contrast on provenance chips is sufficient on the dark shell. Layer legend stacking vs Leaflet required a z-index fix so checkboxes are reachable.

## 11. Provenance behavior

- `ProvenanceBadge` labels: REAL, SIMULATED, DEMO, STALE, UNAVAILABLE, PARTIAL, EXPERIMENTAL.
- Freshness is never presented as LIVE for simulated products (contract: `status-active">Live` not in App).
- Modeled runs use the **Modeled** chip only when a local scenario exists.
- Data Sources panel lists OSM fixture DEMO+fallback, DEM UNAVAILABLE, Open-Meteo precipitation UNAVAILABLE, gauge UNAVAILABLE, solver SIMULATED.

## 12. Demo behavior

- DEMO IdP banner remains: role switcher is not hidden admin access.
- Heuristic 6–72h is DEMO meteorological hours, not a flood map.
- OSM Overpass failure → fixture DEMO with `fallback_used`.
- Physics/scenario jobs remain SIMULATED short SWE bursts.
- DEMO/SIMULATED is never relabeled REAL.

## 13. Remaining product gaps

- Validated spatial 6–72h flood maps (blocked: Spatial AI NOT_VALIDATED).
- Operational gauge discharge/level series.
- Population grid / exposure totals.
- Browser terrain tiles (metadata only).
- Rainfall raster overlay (point observations only, currently UNAVAILABLE).
- Time-indexed future flood states (timeline structure exists; states empty until a job writes them).
- Leaflet keyboard pan/zoom and river-toggle hit-testing under map panes (z-index mitigated).
- Phase 7.1: deeper Explore / map / location / infrastructure experience.

---

**SPATIAL AI:** NOT_VALIDATED  
**SPATIAL API:** UNAVAILABLE  
**TARGET B:** PARTIALLY FEASIBLE  
**MODEL TRAINING:** NOT AUTHORIZED  
**SOLVER MODIFIED:** NO  
**NEXT PHASE:** PHASE 7.1 — EXPLORE / MAP / LOCATION / INFRASTRUCTURE EXPERIENCE
