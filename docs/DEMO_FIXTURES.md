# DEMO operational fixtures

FloodLens-X can show **Command Center UI** for operational (non-scientific) empty features using explicitly labeled **DEMO** data. DEMO is never REAL or LIVE. Missing scientific products stay UNAVAILABLE.

## Gate

`FLOODLENS_DEMO_FIXTURES` is read by `demo_fixtures_enabled()` in `src/floodlens/application/demo_fixtures.py`.

| Context | Value | Effect |
|---|---|---|
| uvicorn / localhost | default **on** (`1`) | River, rainfall, terrain preview, population, evac routes, resources, history compare show DEMO |
| pytest | **off** (`0` via `tests/conftest.py`) | Phase 7.0–7.9 UNAVAILABLE tests keep passing |

Set `FLOODLENS_DEMO_FIXTURES=0` in the API process to run a demo server without fixtures.

## DEMO (hackathon show path)

- River water level + discharge series (`data_status=DEMO`, `simulated=true`, freshness `SNAPSHOT`)
- Rainfall overlay: Open-Meteo-style point/uniform field + tiny heatmap PNG (**not a radar grid**)
- Terrain/DEM preview: min/max metadata + tiny hillshade PNG (**not a solver DEM**; `/terrain/window` omits elevation arrays)
- Population exposure totals
- Evacuation **routes** (fixture polylines). `official_evacuation_order` stays **false**
- Resource inventories (`kind: DEMO RESOURCE INVENTORY`)
- One DEMO paired historical event for forecast-vs-reality metrics

## Stay UNAVAILABLE (not demo-faked)

- Spatial AI flood maps and `POST /api/v1/forecast/ai-spatial` as an operational product (`NOT_VALIDATED`)
- Validated 6–72h spatial AI inundation
- Official evacuation order
- Solver river coupling (`river_level_applied_to_solver: false`)
- Model training / Target B training / physics-vs-AI comparison chart
- Alert metrics `water_level` / `discharge` / `river_level` / `population` (`METRIC_UNAVAILABLE`). Demo alerts with `flood_probability` / `risk_level`

The SWE solver under `src/floodlens/numerical/**` is unmodified. DEMO hillshade is never passed into `resample_window_to_grid`.
