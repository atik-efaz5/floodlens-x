# Phase 4.5 data inventory (inspected, not assumed)

Inspected on 2026-09-02. A data card or script is **not** treated as a local dataset.

| Dataset | Locally present? | Downloaded? | Metadata only? | Credentials? | Public HTTPS? | First supervised model? |
| --- | --- | --- | --- | --- | --- | --- |
| Open-Meteo precip 7-day sample | Yes (`openmeteo_archive_sample.json`) | Tiny sample only | No | No | Yes | Features only, no labels |
| Open-Meteo precip 2014–2024 3 cities | **Yes** after Phase 4.5 acquire (~6.1 MB) | Yes | No | No | Yes | Features |
| Open-Meteo Flood API Q 2015–2024 3 cells | **Yes** after acquire (~0.21 MB) | Yes | No | No | Yes | **Primary labels (MODELLED)** |
| GloFAS CDS cube / RP file | No | No | Cell list only | **CDS required** | No | Blocked |
| EMSR Rapid Mapping | Catalog JSON | Polygons **not** downloaded | **Yes** | Detail API 403 | List API yes | Not enough AOI positives |
| WorldFloods v2 | No | No (~76 GB, CC BY-NC) | Card only | HF | Yes but NC + huge | Out of scope |
| In-situ BWDB gauges | No | No | Product always UNAVAILABLE | N/A | No | Do not invent |
| Local DEM GeoTIFF | Only if `FLOODLENS_DEM_PATH` | Unset in this run | — | — | — | Missing; not invented |
| Synthetic Track A/B | Generated in tests | N/A | N/A | No | N/A | **Pipeline only — not real skill** |

## Primary choice

**Open-Meteo Flood API river discharge (GloFAS v4) + Open-Meteo hourly precip** at the three MVP AOI centers.

Why this, not EMSR/CDS/WorldFloods:

- Actually downloaded in this environment without credentials (~6.3 MB total).
- Ten years of timestamps, both flood and non-flood days (negatives are modelled-below-threshold, not “no map”).
- License is CC BY 4.0 + Copernicus open (commercial-safe path).
- Coherent: same access family as operations precip; labels and precip share UTC dates.
- CDS GloFAS and EMSR polygons were **not** available here.

Honest limit: labels are **MODELLED hydrology**, not observed inundation. Product copy must say so.
