# Data card: Open-Meteo Flood API (GloFAS v4 river discharge)

| Field | Value |
| --- | --- |
| Provider | Open-Meteo (source model: CEMS GloFAS v4) |
| Dataset name | Open-Meteo Global Flood API `/v1/flood` |
| URL | https://flood-api.open-meteo.com/v1/flood |
| License | Open-Meteo **CC BY 4.0** (attribution: Weather data by Open-Meteo.com). Underlying GloFAS is Copernicus CEMS-FLOODS / open. |
| Coverage | Global river network; this extract is **3 AOI centers** (Dhaka, Sunamganj, Sylhet) snapped to nearest GloFAS cell |
| Spatial resolution | GloFAS v4 **0.05°** (~5 km); API returns the nearest cell |
| Temporal resolution | **Daily** |
| Time span (this extract) | 2015-01-01 … 2024-12-31 (API itself: 1984 → near real time) |
| File format | JSON (Open-Meteo daily arrays) |
| Approximate size | **~0.21 MB** for 3 cells × 10 years (committed snapshot) |
| Variables | `river_discharge` (m³/s) |
| Labels | **MODELLED** flood occurrence: daily Q ≥ train-only empirical 2-year threshold (median of annual maxima, 2015–2021). This extract: Sunamganj 50.76, Dhaka 83.92, Sylhet 25.85 m³/s. |
| Limitations | LISFLOOD hydrology, **not** a gauge and **not** a flood-extent map. 5 km cell may miss the intended river. Reanalysis is delayed vs operations. Sub-daily (6h/12h) targets are **not** labeled. |
| Missing data | This extract: **0 nulls** in 3 × 3653 days. Missing Q is dropped (unknown), never coded dry. |
| Update frequency | Open-Meteo consolidates GloFAS reanalysis; forecasts update daily (not used as labels). |
| Known leakage risks | Using Q at `t+h` as a **feature** is forbidden. Using ERA5 precip after `t` as observed is forbidden. Thresholds must be fit on **train years only**. Issue-day Q is excluded from features (day not complete at 00:00 UTC). |
| Preprocessing | Snap to API cell; log1p(Q) in the feature vector; AMS median per city on train years. |
| Citation | Open-Meteo; Copernicus Emergency Management Service — Global Flood Awareness System (GloFAS v4). Harrigan et al., GloFAS-ERA5 operational global river discharge reanalysis 1979–present. |

**Role in Phase 4.5:** primary real training set (Track A). Not Track B observations.

**Access:** public HTTPS, **no CDS account**. Three cells only. Global cube not downloaded.
