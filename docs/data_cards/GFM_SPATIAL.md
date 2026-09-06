# Data card: GFM spatial extract (Phase 5.5)

| Field | Value |
| --- | --- |
| Provider | CEMS / EODC Copernicus Global Flood Monitoring |
| Dataset | `ensemble_flood_extent` (Sentinel-1 SAR algorithm ensemble) |
| STAC | https://stac.eodc.eu/api/v1 collection `GFM` |
| License | STAC **proprietary**. Copernicus / CEMS attribution. Not claimed CC-BY. |
| Label kind | **OBSERVED** |
| Label semantics | Native 20 m: `0` dry, `1` flood, `255` nodata/exclusion. Coarse cell: flood if valid flood fraction ≥ τ=0.25. Nodata → **unknown**, never dry. |
| Native resolution / CRS | 20 m Equi7 Asia AS020M, product tile **E039N021T3** only (neighbor tiles e.g. E039N024T3 are rejected) |
| Working tensor | 32×32 on city EPSG:4326 bounds (Sunamganj ~1 km/cell; Dhaka/Sylhet coarser). Not 500 m radar. |
| Time range (this extract) | Valid-AOI scenes 2018-01-13 … 2023-08-15. 2016/2017/2024 windows were searched; those dates had insufficient AOI coverage (unknown, not dry). |
| Regions | Dhaka and Sunamganj. **Sylhet: insufficient valid GFM coverage** (valid fraction &lt; 5% in this pull). Bangladesh NE/central floodplain AOIs only. |
| Independent events | Meteorological episodes separated by **&gt;45 days**. Two city tiles on the same flood = one event. Orbit twins = one event. Intra-monsoon 12-day revisits = one event. |
| Counts (Phase 5.5 local index) | **7 independent events**, **39 unique days**, **63 city-tiles**. Splits: train 10 / val 34 / test 19. |
| Pixel mix (valid vs unknown) | Among labeled cells: flood ≈ 5.5% of valid; unknown ≈ 60% of all cells. |
| Horizon | **192 h (8-day slot)** = issue `t0` to GFM scene time. **6/12/24/48/72 h are not labeled.** |
| Features | Open-Meteo hourly precip (AOI **point**, broadcast), GloFAS Q t−7…t−1 (cell, broadcast), lagged completed GFM map. DEM unset (`FLOODLENS_DEM_PATH`). |
| Nodata handling | Scenes with &lt;5% valid AOI pixels are dropped. Remaining 255 stays unknown in loss/metrics. Never recoded as dry. |
| Target alignment | `valid_at` = GFM scene datetime. `issue_time` = `valid_at − 192 h`. Features use only times **&lt; t0**. Persistence is the previous completed map with `valid_at &lt; t0`. |
| Geographic scope (defensible) | This product AOI set: Dhaka, Sunamganj, Sylhet (when covered). Additional Bangladesh districts on **E039N021T3** could add within-tile diversity. South Asian or global claims require other Equi7 tiles and a new data card. **Do not claim global generalization from this extract.** |
| Independent-event floor for VALIDATED | 20 meteorological episodes. **Not reached (7).** Verdict: **INSUFFICIENT FOR VALIDATION**. |
| Limitations | STAC geometry is the Equi7 tile, not the SAR swath. Broadcast rain/Q. No DEM. Bangladesh AOIs only. 8-day target is not a 24 h forecast. 39 days ≠ 39 independent floods. |
| Citation | Copernicus Emergency Management Service — Global Flood Monitoring (GFM). |
