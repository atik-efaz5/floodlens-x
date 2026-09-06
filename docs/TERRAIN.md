# Terrain service

`TerrainService` reads a **window** of a GeoTIFF. It never invents elevations
and never loads a full-country raster into memory.

## Access

- Path: `FLOODLENS_DEM_PATH` or an explicit `path` argument
- Window: `rasterio.windows.from_bounds` on the city AOI (or query bbox)
- Resample: existing `DEMManager.resample_terrain` onto `(Ny, Nx)`
- Slope: `numpy.gradient` on the window (`calculate_slope`)
- Flow direction: `NOT_COMPUTED`

## Missing data

If the file is unset, missing, or rasterio is unavailable, `get_window` returns
`available=false`, `elevation=null`, `data_status=UNAVAILABLE`. The physics job
fails with “Terrain unavailable” unless `allow_synthetic_dem=true`.

JSON APIs omit the elevation array (`GET /api/v1/terrain/window`). Use physics
jobs and overlay PNGs for grids.

## CRS

Window metadata includes the GeoTIFF CRS string. The model domain currently
uses the city geographic bounds plus the SWE metric lengths from
`ScenarioSession` (same as Phase 1). That mismatch is documented, not hidden.
