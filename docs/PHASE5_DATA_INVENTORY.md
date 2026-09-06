# Phase 5 data inventory (probed, then capped acquire)

Inspected 2026-09-02. A data card is **not** a local dataset until files are on disk.

| Dataset | Locally present? | Downloaded? | Credentials? | Label kind | Role |
| --- | --- | --- | --- | --- | --- |
| Copernicus GFM ensemble flood extent (STAC) | After `scripts/phase5_acquire_gfm.py` if AOI-valid scenes kept | Capped; Equi7 tile E039N021T3 | **No** (public STAC + data.eodc.eu HEAD 200) | **OBSERVED** | Primary spatial labels |
| Giezendanner BD inundation (CyVerse) | No | No | Probe HEAD may succeed; **not acquired** (GFM is primary OBSERVED) | DERIVED | Fallback **not used** |
| Open-Meteo precip 2014–2024 3 cities | Yes (Phase 4.5) | Yes | No | features | Broadcast onto grid (`precip_is_aoi_point`) |
| Open-Meteo GloFAS Q 2015–2024 | Yes (Phase 4.5) | Yes | No | MODELLED features | `q_is_glofas_cell`; **not** spatial labels |
| DEM `FLOODLENS_DEM_PATH` | Unset | No | N/A | — | Missing; zeros + `dem_present=0` |
| WorldFloods / Sen1Floods11 | No | No | — | — | Out of scope (size/NC/same-time mapping) |
| JRC RP hazard | No | No | — | MODELLED | Spatial baseline later, never truth |
| AOI GBDT v0.1 | Yes | n/a | n/a | MODELLED | Unchanged VALIDATED AOI product |

## Probe decisions

1. GFM STAC search works. Sample GeoTIFF ~147 KB public. License STAC=`proprietary` (Copernicus attribution, not CC-BY).
2. All three city bboxes sit in Equi7 **E039N021T3**. STAC geometry is the **tile**, so many hits are nodata over the AOI — those maps are **unknown**, never dry.
3. CyVerse fallback was **not** used (GFM is public OBSERVED). DEM unset.
4. Acquire (Phase 5.5): local product-tile index of **39** unique days / **63** city-tiles (~33 MB raw, under 200 MB / 8 GB). 7 independent meteorological episodes (45-day gap). Sylhet still has no scene above the 5% valid-pixel cutoff. Neighbor Equi7 tiles are rejected.
5. Builder: train 10 / val 34 / test 19. Horizon **192 h**. Spatial catalog **TRAINED** internally, public **NOT_TRAINED** (not VALIDATED). AOI GBDT remains VALIDATED. Verdict: **INSUFFICIENT FOR VALIDATION**.

## Honesty

- 6h/12h/24h spatial labels are **not invented**. API those horizons stay UNAVAILABLE.
- Derived 8-day fusion maps would stay **DERIVED** if used.
- Physics vs spatial AI: **COMPARISON NOT YET COMPARABLE**.
- Spatial catalog starts **NOT_TRAINED** and does not inherit AOI VALIDATED.
