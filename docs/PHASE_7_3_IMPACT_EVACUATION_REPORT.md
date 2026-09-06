# PHASE 7.3 — Impact, Evacuation, Shelter, and Resource Planning

**Date:** 2026-09-03  
**Scope:** Operational Impact workspace on the Phase 7.0–7.2 command center.  
**Not in scope:** spatial AI training, enabling `POST /api/v1/forecast/ai-spatial`, Target B training, numerical solver changes, fabricated population/capacity/routes/inventories.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Impact workspace

- Dedicated **Impact** view for General, Emergency, Researcher, and Admin.
- Layout: left = region/scenario, category filters, impact legend, optional physics-job assess; center = Leaflet map with OSM assets; right = summary / shelters / evacuation / resources by role; bottom = evidence, assumptions, provenance.
- Explore “Open Impact workspace” preserves the selected city/map context.
- `GET /api/v1/impact` plus infrastructure/shelters/evacuation/resources. Existing `POST /api/v1/impact/assess` is unchanged.

## 2. Population status

- **POPULATION EXPOSURE: UNAVAILABLE**
- Reason: no authoritative population dataset is currently configured.
- `NullPopulationProvider` remains the plug-in point for a future raster/table.
- OSM building counts are not used as population.

## 3. Infrastructure impact

- Hospitals, schools, bridges, roads, critical OSM amenities, and shelters from the existing catalog (bbox + limit 200).
- Totals are catalog counts. **Affected** is `null` until a flood raster exists; it is never shown as `0` for NOT_COMPUTED/UNAVAILABLE.
- DEMO fixture geometry stays DEMO.

## 4. Road impact

- Road **geometry** remains OSM/fixture polylines.
- **ROAD FLOOD IMPACT** is NOT_COMPUTED without a raster (or without shapely).
- With a raster and shapely, a potential flood-exposure percentage is computed. That is not travel time or a safe route.

## 5. Hospital / school / bridge impact

- Point depth uses the existing 0.05 m threshold on an attached physics/scenario raster.
- States: EXPOSED / NOT_EXPOSED / UNKNOWN / NOT_COMPUTED.
- EXPECTED DEPTH is the point sample or UNAVAILABLE. Regional maximum depth is labeled separately and is not substituted.
- Language: potential flood exposure, not “bridge damaged.”

## 6. Shelter analysis

- Cataloged shelters are listed with source, coordinates, and computed exposure when a raster exists.
- **CAPACITY / OCCUPANCY: UNAVAILABLE.** Fixture capacity figures are not treated as an authoritative inventory.
- **ACCESSIBILITY: UNAVAILABLE / NOT_COMPUTED.**
- Suitability: EXPOSED, CAUTION (not exposed but access unknown), or UNKNOWN. Never labeled globally safe.

## 7. Evacuation analysis

- Labeled **POTENTIAL EVACUATION-RISK ANALYSIS**.
- `official_evacuation_order: false`.
- Routes NOT_COMPUTED (no routing graph). Travel time and safe route are null.
- Planning boundary is the city-registry **STUDY REGION**.
- Current P × E × S category is shown as heuristic risk, not an evacuation zone.

## 8. Resource planning

- OBSERVED RESOURCE INVENTORY for boats, workers, medical teams, pumps, food, water, and shelter capacity: all UNAVAILABLE (`value: null`).
- PLANNING ESTIMATE: UNAVAILABLE (no documented estimate model).
- Priorities include WHAT / WHY / EVIDENCE / LIMITATIONS / data status. Hospital HIGH/LOW only uses the computed exposed count.

## 9. Scenario integration

- Optional `job_id` or latest completed city artifact.
- Scenario label BASELINE vs SCENARIO, with job/artifact ids when present.
- Reports consume the same impact/shelter/evacuation/resource payloads.

## 10. Safety language

- Copy uses planning support, potentially exposed, and “review with official emergency guidance.”
- The UI/API do not say “Evacuate now” and do not impersonate an emergency authority.

## 11. Provenance

- Every workspace payload includes provenance (provider, dataset, data_status, freshness).
- Computation status is explicit: UNAVAILABLE, NOT_COMPUTED, or COMPUTED FROM CURRENT FLOOD OVERLAY.

## 12. Unavailable capabilities

- Population exposure, density
- Authoritative shelter capacity and occupancy
- Road accessibility / travel time / evacuation routes
- Observed resource inventories and planning estimates
- Agriculture exposure
- Building polygon impact
- Spatial AI flood maps

## 13. Tests

- `tests/test_phase73_impact_evacuation.py`: population, infrastructure, line impact, shelters, evacuation language, resource evidence, role 403, scenario job, reports, frontend contracts, spatial AI fail-closed.

## 14. Browser/E2E

Live API after uvicorn reload (`127.0.0.1:8000`):

- `GET /api/v1/impact?city_id=dhaka` — population UNAVAILABLE, hospital affected `null` without a raster, safety banner present.
- `GET /api/v1/impact/shelters` — CAPACITY UNAVAILABLE.
- `GET /api/v1/impact/resources` as General — 403 (`resources.read`).

The IDE browser MCP was not available for a full click-through. Frontend contracts cover SEARCH/OPEN IMPACT/category/evacuation/resource/return-to-map copy. Vite `npm run build` succeeded.

## 15. Performance

- Infrastructure/shelter lists capped at 200; bbox supported.
- Map OSM layer remains viewport/bbox clustered.
- No national GeoJSON dump.

## 16. Accessibility

- Category filters use `aria-pressed`.
- Impact summary `aria-live` announces population UNAVAILABLE and planning-support language.
- Evacuation/resource sections are labeled. Status is textual, not color-only.
- Legend explains type fill vs exposure outline.

## 17. Limitations

- Point/line impact still requires a completed physics/scenario raster.
- Line fraction needs shapely; otherwise NOT_COMPUTED.
- DEMO OSM/fixture assets are not a live emergency inventory.
- No routing engine, no official orders, no invented capacities.
- Spatial AI stays NOT_VALIDATED; solver unmodified.
