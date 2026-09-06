# Data card: Copernicus Global Flood Monitoring (GFM) ensemble flood extent

| Field | Value |
| --- | --- |
| Provider | CEMS / EODC (Copernicus Emergency Management Service — Global Flood Monitoring) |
| Dataset name | GFM `ensemble_flood_extent` (Sentinel-1 SAR algorithms) |
| STAC | https://stac.eodc.eu/api/v1 collection `GFM` |
| License | STAC field **proprietary**. Copernicus / CEMS attribution required. Do **not** claim CC-BY. Some REST wiki pages mention a GFM Web Portal token; this project used **public** STAC search + public `data.eodc.eu` asset URLs (HEAD 200, no token). |
| Coverage (this extract) | Three Bangladesh AOIs (Dhaka, Sunamganj, Sylhet) on Equi7 Asia 20 m tile **E039N021T3** |
| Spatial resolution | Native **20 m** Equi7 AS020M; working tensors resampled to **32×32** on city geographic bounds (~0.5–2 km/cell depending on AOI). Not 500 m radar. |
| Temporal resolution | Sentinel-1 scene times (often several days). **Not** 6/12/24 h. |
| Time span (this extract) | Capped monsoon / dry windows 2018, 2020–2021, 2022 named NE Bangladesh holdout |
| File format | GeoTIFF (ZSTD) raw; processed `npz` class + fraction maps |
| Size cap | ≤ 80 MB raw in acquire (plan ceiling 8 GB). Empty-AOI scenes dropped. |
| Variables | Ensemble flood extent: `0` dry, `1` flood, `255` nodata/exclusion |
| Labels | **OBSERVED**. Positive: flood fraction ≥ τ=0.25 on the coarse cell. Negative: valid observation below τ. Unknown: nodata — **never coded dry**. |
| Limitations | Scene geometry in STAC is the Equi7 tile, not the SAR swath. Many “intersecting” items are nodata over the AOI. Permanent-water mask not applied in MVP (exclusion coded as 255 when present in the extent product). |
| Missing data | Nodata / exclusion → unknown. |
| Known leakage risks | Same-time SAR as **input** is forbidden (label only). Issue time is scene time minus 8 days. Persistence is the previous **completed** map. No pixel-i.i.d. split. |
| CRS | Native Equi7 aeqd (lat0=47, lon0=94). City grids EPSG:4326. Same physics CRS mismatch as docs/TERRAIN.md. |
| Citation | Copernicus Emergency Management Service — Global Flood Monitoring (GFM). |

**Role in Phase 5:** primary **OBSERVED** spatial labels when the 5.0 probe shows public download.

**Access:** public HTTPS in this environment. Do not fabricate a portal token.
