# PHASE 7.1 — Explore Workspace Report

**Date:** 2026-09-03  
**Scope:** Geospatial Explore workspace on the Phase 7.0 command center (Vite + React + Leaflet).  
**Not in scope:** spatial AI training, enabling `POST /api/v1/forecast/ai-spatial` as a product, Target B training, numerical solver changes, Next.js/Mapbox rewrite.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Explore features

- Dedicated Explore information architecture: search in the header; layer control on the left; Leaflet map in the center; selected-area analysis on the right; observed/DEMO timeline at the bottom.
- Location search with autocomplete, keyboard navigation, clear, loading, empty, invalid-coordinate, and multi-result disambiguation (country, city, district, river, neighborhood, coordinates, region ID).
- Map navigation: pan, zoom, fit region, reset extent, coordinate click, optional rectangle selection, study-region selection (city-registry bounds only).
- Layer manager with available / conditionally available / unavailable rows, each with provenance and a reason when disabled.
- Consistent legend: risk colors only for LOW / MODERATE / HIGH / CRITICAL; distinct infrastructure symbols; flood overlay uses the existing cyan/blue convention.
- Selected-area panel sections: Overview, Risk, Flood, Forecast, Rivers, Infrastructure, Data. Missing values render **UNAVAILABLE**, never zero.
- Infrastructure quick filters (All / Hospitals / Schools / Bridges / Roads / Critical / Shelters) update the map without a page reload.
- URL hash restores city, lat/lon, zoom, layers, filter, and river. Reports remain the sharing product.
- Responsive: desktop side panels; tablet/mobile map-first with bottom sheets for layers and analysis.
- Simulation controls stay on the Simulation view so Explore is an investigation workspace, not a solver console.

## 2. Map capabilities

- Existing Leaflet FloodMap retained (no Mapbox/Next rewrite).
- Study-region rectangle from the city registry; hover/selected outline; click selects the region. No manufactured administrative polygons.
- Optional two-click rectangle is labeled as a map rectangle, not an admin boundary.
- Coordinate clicks expose latitude and longitude only.
- Flood/forecast image overlays appear only when a physics/scenario artifact URL exists.
- Inspection popup depth/velocity use UNAVAILABLE when null or zero (does not fabricate 0.000 m).
- Fit region / reset extent map commands.

## 3. Search capabilities

- Demo geocoder catalog extended with Buriganga (river), Bangladesh (country), and region_id on Dhaka / Sunamganj / Sylhet.
- GET /api/geocode/search results include region_id when present.
- Autocomplete combobox with aria-activedescendant, live status, and a clear control.
- Selection flies the map, updates city when the hit is inside a registered study region, refreshes status, and writes hash state.

## 4. Infrastructure capabilities

- OSM bbox fetch (GET /api/v1/infrastructure, limit capped at 500) with client clustering at low zoom.
- Categories: hospitals, schools, bridges, roads, critical (emergency), shelters.
- Asset inspect: name, type, coordinates, source, timestamp, data status.
- Flood impact and accessibility only when computed; otherwise NOT_COMPUTED.
- Roads use geometry gray. ROAD FLOOD IMPACT: NOT_COMPUTED. Roads are never colored as flooded.
- Nearby assets for a map click use a small bbox around the point (not a national dump).

## 5. River integration

- River polylines from stored segment coordinates.
- Click shows name, segment, upstream/downstream siblings, source, geometry, WATER LEVEL / DISCHARGE UNAVAILABLE.
- GET /api/v1/rivers/{river_id}/segments/{segment_id} returns topology plus provenance without inventing gauges.
- Deep-analysis link opens the existing Forecast view (RiverForecastPanel). Phase 7.2 owns fuller river intelligence.

## 6. Layers

Available now (when data exists): flood extent overlay (physics/scenario artifact), rivers, roads, hospitals, schools, bridges, critical infrastructure, shelters.

Conditionally available: forecast overlay (heuristic/physics artifact only); historical flood as stored flood-states after a physics job (not EMSR polygons).

Catalog rows include source, timestamp, dataset/version via provenance, status, optional spatial/temporal resolution, freshness, and reason when disabled.

## 7. Unavailable layers

Disabled with an explicit reason:

- Rainfall raster — no validated spatial rainfall layer is currently configured.
- Terrain raster — no browser DEM raster is loaded (metadata only) or terrain raster UNAVAILABLE.
- Population density — population data is not ingested. Exposure is not invented.
- Spatial AI map — Spatial AI is NOT_VALIDATED. POST /api/v1/forecast/ai-spatial stays UNAVAILABLE.
- Water depth — only on a completed physics/scenario artifact.
- Water level — no public gauge series is configured. Water level is not invented.

## 8. Provenance

- ProvenanceBadge on layers, selected-area Data/Risk/Forecast/River/Infrastructure, freshness bar, and timeline.
- Freshness language: REAL / STALE / DEMO / SIMULATED / UNAVAILABLE with UPDATED X AGO when a timestamp exists.
- LIVE is never claimed for simulated or unlabeled sources.
- DEMO heuristic forecast hours are labeled DEMO, not operational spatial maps.

## 9. Performance

- Infrastructure remains bbox-scoped and limit-capped.
- Marker clustering below zoom 13.
- Debounced moveend refetch (350 ms).
- No national infrastructure load; no DEM/rainfall rasters stuffed into React state.
- Overlay PNGs stay as image URLs, not in-memory grids.

## 10. Accessibility

- Search combobox: keyboard arrows, Escape, clear, aria-live announcements.
- Layer checkboxes and filter buttons have labels / aria-pressed.
- Selected-area sections are collapsible headings with aria-expanded.
- Map skip link (existing RoleShell), focus-visible outlines.
- Status is textual (UNAVAILABLE / DEMO / NOT_COMPUTED), not color-only.
- Risk colors are not reused for infrastructure or flood depth.

## 11. Browser test

Journey against the Vite app at `http://127.0.0.1:5173/` (Leaflet Explore workspace):

- SEARCH DHAKA — autocomplete opened with disambiguation (Dhaka city, Mirpur 10, Mirpur suburb).
- ZOOM — selecting Dhaka switched the city selector to Dhaka, set hash `city=dhaka`, zoom 12, header “Command Center · Dhaka”.
- ENABLE RIVERS — Rivers layer enabled with `osm-or-fixture` source/timestamp (not a fabricated flood product).
- ENABLE HOSPITALS — Hospitals layer enabled with provenance; 7 OSM features loaded via bbox fetch (capped).
- VIEW DATA STATUS — flood extent UNAVAILABLE with reason; rainfall/terrain/population/water depth UNAVAILABLE; Spatial AI NOT_VALIDATED on the timeline.
- Timeline showed Heuristic 6/12/24/48/72h labeled **DEMO / not spatial AI**, not as operational spatial maps.
- Selected-area Flood depth rendered UNAVAILABLE (not zero). Risk showed P × E × S.

MCP browser lock dropped before hospital-marker click and river-polyline click could be finished interactively. Those paths are covered by `tests/test_phase71_explore.py` (infrastructure bbox/type filter, river segment upstream/downstream, unavailable-layer reasons).

## 12. API changes

Reuse of existing /api/v1 surfaces. Additive only:

- GET /api/v1/regions/{city_id} — study-region rectangle geometry from the city registry (not admin polygons). Auth: map.read.
- GET /api/v1/rivers/{river_id}/segments/{segment_id} — segment geometry + upstream/downstream. Water level/discharge remain null. Auth: map.read.

Catalog: optional reason / resolution fields; bridges, water_level, ai_spatial rows.

No duplicate APIs. Spatial AI endpoint remains fail-closed.

## 13. Remaining limitations

- No validated spatial AI flood maps, rainfall rasters, terrain rasters in the browser, population density, discharge, or water levels.
- Heuristic 6–72h points remain DEMO meteorological hours, not inundation maps.
- OSM often falls back to fixture data (DEMO) when Overpass is rate-limited.
- Per-feature flood impact and road flooding are NOT_COMPUTED until a physics raster plus impact job exists.
- Region geometry is the rectangular study AOI, not census/admin polygons.
- Deeper upstream/downstream propagation and river monitoring UI is Phase 7.2.
- URL hash restores Explore context; it is not a second sharing system (Reports still owns share snapshots).
