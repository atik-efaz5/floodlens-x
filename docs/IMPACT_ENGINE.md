# Impact engine

Impact is computed **on the backend** from a physics depth raster plus OSM
assets. The frontend never multiplies P×E×S and never invents counts.

## What is computed

- **Point assets** (hospitals, schools, …): depth at lat/lon via the existing
  grid mapping. Flooded if depth > 0.05 m.
- **Roads (lines):** if shapely is installed, sampled length fraction under
  water. Otherwise `roads_affected.computed=false`, `reason=NOT_COMPUTED`.
- **Polygons / accessibility:** always `NOT_COMPUTED`.
- **Population:** `PopulationDataProvider` default is
  `NullPopulationProvider` → `population_exposed=null` until a raster exists.

## Risk (P×E×S)

`risk_from_physics` (formula_id unchanged):

- probability = min(1, flood_fraction)
- severity = min(1, max_depth_m / 2.0)
- exposure = 0.6 for Dhaka, 0.4 otherwise (same city prior as heuristic risk)

Heuristic `risk_for_city` remains for the status panel when no physics run is
attached.
