# PHASE 7.2 — River Intelligence Report

**Date:** 2026-09-03  
**Scope:** Dedicated River Intelligence workspace on the Phase 7.0 command center and Phase 7.1 Explore map.  
**Not in scope:** spatial AI training, enabling `POST /api/v1/forecast/ai-spatial` as a product, Target B training, numerical solver changes, fabricated gauges, fabricated arrival times, or inferred hydrological flow direction.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. River workspace

- New **River** view in the command-center shell (`RoleShell` id `river`) for General, Emergency, Researcher, and Admin.
- Layout: left = city selector, river search, segment list, NETWORK TOPOLOGY graph, topology legend; center = Leaflet map with river highlights; right = selected-river intelligence; bottom = time-series empty/populated charts plus provenance.
- Explore remains intact. Selected-area “Open River workspace” now opens this view instead of Forecast.
- Scenario, Forecast, and Explore links are explicit navigation, not invented river forcing.

## 2. River search

- `GET /api/v1/rivers/search?q=&city_id=` returns river, segment, and **STUDY REGION** hits (city-registry bounds). Basin catalog is `{available: false}`.
- Frontend combobox: debounce, loading, empty, error, DEMO badges, keyboard arrows/Enter/Escape, aria-live.
- Selecting a river zooms to fixture geometry, highlights the polyline, loads segments, overview, observations, and neighbor topology.
- Empty query → HTTP 400. Unknown query → empty results, not a fabricated river.

## 3. Segment inspection

- `GET /api/v1/rivers/{id}/segments/{segment_id}` and `/neighbors` expose segment id, river, LineString geometry when present, upstream/downstream siblings, reachable walks, study-region intersections, source, timestamp, DEMO data status.
- WATER LEVEL and DISCHARGE remain `null` / UNAVAILABLE. Arrival time remains `null`.
- Map click and left-list click share the same selection path.

## 4. Topology

- Interactive **NETWORK TOPOLOGY** list (upstream → segments → downstream-connected area). Clicking a node selects that segment and highlights neighbors on the map.
- Colors: selected gold, upstream teal, downstream violet, reachable-downstream indigo dashed, other geometry sky. These are **not** risk colors.
- `from_node` / `to_node` are fixture/OSM topology. The UI labels this as network topology, not hydrological causality.

## 5. Flow-direction status

- Status string everywhere: **FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY**.
- `flow_direction_verified: false` on graph and neighbors.
- Line coordinate order is not treated as verified flow. HydroRIVERS / verified hydrological topology is not configured.

## 6. Observation status

- `RiverGaugeAdapter.fetch()` still returns no water level and no discharge.
- `GET /api/v1/rivers/{id}/observations` and `/overview` report WATER LEVEL UNAVAILABLE, DISCHARGE UNAVAILABLE, forecast UNAVAILABLE.
- Missing values are `null`, never `0` / `0.0` / “normal” / “stable”.

## 7. Time series

- Bottom `RiverTimeSeries` charts water level and discharge only when ≥2 **REAL** points with `available: true` and a non-null value exist.
- Otherwise an explicit empty state with the reason (no REAL series / fewer than two observed points).
- Forecast series is labeled UNAVAILABLE. DEMO geometry is never mixed into REAL gauge values.
- `compute_rate_of_change` documents units (`m/h` or `m3/s/h`) and interval only for REAL pairs.

## 8. Threshold handling

- `flood_threshold_m` is `null` unless a real threshold exists (none is configured).
- UI: FLOOD THRESHOLD UNAVAILABLE, CURRENT UNAVAILABLE when no level, TIME TO THRESHOLD UNAVAILABLE.
- Time-to-threshold is never estimated from a constant speed or missing forecast.

## 9. Propagation

- **NETWORK PROPAGATION:** topology walk of downstream-connected segments (`reachable_downstream`, bounded).
- **HYDROLOGICAL PROPAGATION: NOT_COMPUTED** — no hydraulic routing, lag model, or SWE river-boundary coupling is enabled.
- The two are labeled separately so OSM connectivity is not presented as a flood wave.

## 10. Downstream linkage

- Intersections use city-registry study rectangles, labeled **STUDY REGION**, source `city-registry`.
- Not labeled as administrative districts.
- Risk copy uses “downstream-connected area”, not “this river caused the flood.”

## 11. Provenance

- List, search, overview, graph, segment, neighbors, and observations all carry `provenance` (provider, dataset, data_status, freshness, retrieved_at, simulated, fallback_used).
- UI uses `ProvenanceBadge`. Geometry is DEMO / osm-fixture / SNAPSHOT. Gauge series is UNAVAILABLE / river-gauge.
- DEMO and REAL are not mixed.

## 12. Demo behavior

- River centerlines currently come from the OSM-style fixture (`dhaka_osm.json`), including when Overpass infrastructure succeeds.
- DEMO is visible on search hits, map popups, overview, and a workspace disclaimer: “DEMO fixture topology. Not live river monitoring.”
- DEMO values are never shown as live gauges.

## 13. Unavailable capabilities

- Real water level, discharge, rate of change, flood threshold, time-to-threshold.
- River level/discharge forecast.
- Verified flow direction / HydroRIVERS.
- Hydrological propagation and estimated arrival time.
- Basin catalog.
- Administrative district polygons.
- Live river monitoring.
- Scenario `river_level_delta_m` recorded but **not** applied as a SWE river-boundary condition (`river_level_applied_to_solver` remains false).

## 14. Testing

- `tests/test_phase72_river_intelligence.py`: search, overview, segment/neighbors, flow-direction status, unavailable observations, rate-of-change, bbox/limit validation, frontend contracts, spatial AI still fail-closed.
- Existing `/api/v1/rivers/{id}` and `/graph` (`edges`) contracts preserved.
- Explore and command-center contract tests remain.

## 15. Browser/E2E

Journey against the Vite app at `http://127.0.0.1:5173/` with the Phase 7.2 API on `127.0.0.1:8000`:

- OPEN RIVER — Command-center **River** view loaded (search, NETWORK TOPOLOGY legend, intelligence panel, time-series empty states).
- VIEW OBSERVATION STATUS — WATER LEVEL / DISCHARGE / THRESHOLD / RATE OF CHANGE UNAVAILABLE (not zero).
- VIEW PROPAGATION — HYDROLOGICAL PROPAGATION NOT_COMPUTED; ESTIMATED ARRIVAL TIME UNAVAILABLE; STUDY REGION labeled, not an administrative district.
- DEMO disclaimer visible: “DEMO fixture topology. Not live river monitoring.”
- OPEN FORECAST / OPEN SCENARIO / RETURN TO EXPLORE buttons present.
- SEARCH / SELECT / MAP ZOOM — verified at the API (`GET /rivers/search?q=Buriganga` returns DEMO Buriganga + segments; overview/neighbors/observations honest). In-browser combobox selection was started; the IDE browser MCP dropped before the type/select/zoom sequence could be finished. Search is global (not limited to the current city) so Buriganga can be chosen from Sunamganj, then the study city switches to Dhaka and the map flies to fixture coordinates.

API restart was required: an older uvicorn still bound `:8000` and treated `/rivers/search` as `{river_id}=search` (404). After reload, the new routes responded correctly.

## 16. Performance

- `GET /api/v1/rivers` supports `bbox` and `limit` (cap 80). Invalid bbox → 400.
- Graph edges and neighbor walks are capped (80 / 50). Observation series capped at 200.
- Search capped at 20 unique hits.
- No national river dump is rendered; the current fixture is two Buriganga segments.

## 17. Accessibility

- River search combobox with listbox, aria-expanded, aria-live loading/empty/error.
- Segment and topology controls are buttons (keyboard).
- Chart `role="img"` with a text description of REAL point counts, or a textual empty reason.
- Legend includes text labels, not color alone.
- Intelligence panel `aria-live` announces river name and UNAVAILABLE observation/flow-direction status.
- Mobile: existing Explore sheet toggles reused for River left/right panels.

## 18. Limitations

- Topology is a two-segment DEMO fixture, not a national HydroRIVERS network.
- No public gauge feed is configured; observations cannot become REAL until a legitimate source is ingested.
- Flow direction is not verified; do not treat `from_node` → `to_node` as hydraulic direction.
- Arrival times and hydrological propagation remain unavailable by design.
- Spatial AI stays NOT_VALIDATED; Spatial API stays UNAVAILABLE; Target B stays PARTIALLY FEASIBLE; solver unmodified.
