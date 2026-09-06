# Forecast engine (Phase 3)

FLOODLENS-X runs a **physics baseline** on top of Phase-2 canonical data. The
shallow-water kernel is unchanged. This document is the scientific contract
for clocks, forcing, and labels.

## Two clocks

| Clock | Meaning | Where it appears |
| --- | --- | --- |
| `forcing_clock` | Meteorological hours (`valid_at` on Open-Meteo forecast rain) | Forecast horizons 6/12/24/48/72 h |
| `solver_clock` | Shallow-water **simulation seconds** (`T_end`) | Job `available_times`, TimePlaybackBar |

A “24 h forecast state” means: take the Open-Meteo **forecast rainfall valid at
T+24 h**, convert it to m/s, run a **documented short SWE burst** on the model
domain, and store depth/extent as a **physics baseline forced by that hour’s
rain**. Solver seconds are **not** 24 hours of hydrodynamics.

`data_status` for that product is `PARTIAL` or `SIMULATED`. SWE output is never
presented as an observation. `LIVE` is forbidden.

## Pipeline

Region AOI → `TerrainService.get_window` (windowed GeoTIFF) → resample to
`(Ny, Nx)` → `RainfallService` uniform field (`NEAREST_STATION`) →
`SIMPLE_RUNOFF_BASELINE` → `SimulationAdapter` → `SimulationService.run_scenario`
→ validation → artifacts (npy reference + overlay PNG) → `FloodState` /
`FloodForecast` → backend `risk_from_physics` (P×E×S) → API → Leaflet
`ImageOverlay`.

The adapter **does not import** `floodlens.numerical`. Jobs enqueue via FastAPI
`BackgroundTasks`; Celery is optional and unused by default.

## Rainfall → m/s

Hourly precipitation (mm) is treated as mm in that hour:

`effective_mps = (precip_mm / 1000 / 3600) * runoff_coefficient`

Default `runoff_coefficient = 1.0` (all rain becomes surface water, matching
the existing SWE source term). Interpolation is a **uniform field** from the
city-center / nearest-station value, not a radar grid.

If the rainfall provider has no series, the physics forecast is
`UNAVAILABLE`. The heuristic nowcast may still run and is labeled `HEURISTIC`,
not AI.

## Terrain

Windowed `rasterio` read only. Missing `FLOODLENS_DEM_PATH` → `UNAVAILABLE`.
Synthetic DEM is used **only** when the caller sets `allow_synthetic_dem=true`,
and the result is labeled `fallback_used` + `SIMULATED`. Never silent.

## Flood extent

A cell is flooded when depth **> 0.05 m** (`FLOOD_DEPTH_THRESHOLD_M`), the same
cutoff already used for `flood_fraction` in jobs.

## Heuristic vs physics vs AI

- Heuristic: documented nowcast, `expected_depth=null`, `confidence_kind=heuristic`
- Physics Baseline v0.1: SWE burst per horizon, `expected_depth` from max depth
- AI: `NOT_TRAINED` — no accuracy percentage
