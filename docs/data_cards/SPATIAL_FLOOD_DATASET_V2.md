# Data card: spatial flood dataset v2 (Phase 6 formulation)

| Field | Value |
| --- | --- |
| Dataset version | `phase6-gfm-spatial-v2` |
| Provider (labels) | CEMS / EODC Copernicus Global Flood Monitoring |
| Label dataset | `ensemble_flood_extent` (Sentinel-1 SAR algorithm ensemble) |
| Label kind | **OBSERVED** only in the headline table. DERIVED sources (Giezendanner, GFD) are not mixed into this metric table. |
| License (labels) | STAC **proprietary**. Copernicus / CEMS attribution. Not claimed CC-BY. |
| Label semantics | Native 20 m: `0` dry, `1` flood, `255` nodata/exclusion. Working cell: flood if valid flood fraction ≥ τ=0.25. Nodata → **unknown**, never dry. |
| Target | Binary flood **occurrence** at **t0 + 192 h** (next GFM scene slot). **6/12/24/48/72 h labels do not exist** and are not interpolated. |
| Native resolution / CRS | 20 m Equi7 Asia AS020M, product tile **E039N021T3**. Neighbor tiles rejected. |
| Working tensor | **64×64** on Bangladesh AOI bounds (haor + central floodplain + Dhaka subtiles). Sunamganj ≈ 470 m/cell. Dhaka is subtiled so cells are closer to 1 km, not a fake 20 m upsample. |
| Spatial AOIs (training/eval, not the product catalog) | sunamganj, sylhet, kishoreganj, netrokona, dhaka_sw, dhaka_se, dhaka_nw, dhaka_ne. Product UI still has exactly three cities: Dhaka, Sunamganj, Sylhet. |
| Rainfall | Open-Meteo archive **3×3 lat/lon lattice** (ERA5-Land family), IDW onto the working grid. `precip_is_aoi_point=false` only when ≥4 lattice points fall in the AOI. **Not fabricated rain.** Reanalysis at t0 is not an operational NWP forecast; kinds stay separate. IMERG is the upgrade if within-tile variance is still ~0. |
| Terrain | Real elevation: Open-Meteo elevation API (SRTM / Copernicus GLO family) or `FLOODLENS_DEM_PATH` GLO-30 window. Slope from the elevation grid. **Not synthetic.** FABDEM is not used (CC BY-NC-SA). |
| Rivers | Distance-to-river (+ optional binary mask). Prefer a local **HydroRIVERS v1** clip (`FLOODLENS_HYDRORIVERS_PATH`). Else OSM waterways (ODbL) as a real-geometry substitute. GloFAS Q remains a **tile-level** hydrologic scalar (TEMPORAL-ONLY is acceptable once distance-to-river is present). |
| Persistence | Last completed GFM map with `valid_at < t0`. Missing where previous scene was unknown. |
| Event grouping | 45-day `event_id`. City/subtile maps of the same pulse are one event. Orbit twins are one event. |
| Independent-event floor | **≥20** meteorological episodes for Gate 0. This is a minimum for attempting validation, not a claim of sufficiency. Prefer 25–40 BD-basin episodes. |
| Unknown / nodata | 255 retained. Masked loss and metrics. Scene drop if valid fraction < 5%. Never recode nodata as dry. |
| Splits | Temporal: train issue &lt; 2019-01-01; val &lt; 2022-01-01; test 2022+ and named NE holdout. Geographic: sunamganj, sylhet, netrokona held out of geographic-train. Same `event_id` must not sit in train and test. Pixel-i.i.d. splits are forbidden. |
| Licenses (features) | Open-Meteo archive CC BY 4.0; elevation via Open-Meteo; HydroRIVERS free scientific/commercial; OSM ODbL if used. |
| Not in this dataset | 6–72 h GFM interpolation; mixed OBSERVED/DERIVED labels; South Asia / global GFD or WorldFloods as the headline target; synthetic DEM; national DEM mosaic; radar. |
| Limitations | Equi7 STAC geometry is the tile, not the SAR swath (AOI nodata is unknown). ERA5-Land lattice is coarse on Sunamganj (~30 km). Event count on the current local GFM extract is expected **below 20** until more years/tiles are acquired. 192 h is not a 24 h forecast. |
| Metrics policy | No fake metrics on this card. Gate 0/1/2 results live in `docs/PHASE6_FORMULATION.md` and `phase6_eval.json` after evaluate. Accuracy is not a headline. |
| Citation | Copernicus Emergency Management Service — Global Flood Monitoring (GFM). Open-Meteo. HydroRIVERS / OSM as documented in the acquire caches. |
