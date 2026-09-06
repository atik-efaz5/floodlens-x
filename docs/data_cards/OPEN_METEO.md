# Data card: Open-Meteo historical precipitation

| Field | Value |
| --- | --- |
| Dataset | Open-Meteo Historical `/v1/archive` |
| Provider | Open-Meteo (ERA5 / ERA5-Land family) |
| License | CC BY 4.0 (attribution: Weather data by Open-Meteo.com) |
| Role | Hourly precip lookback; antecedent 24/72 h |
| Spatial | Point at city center (not a dense radar grid) |
| Time | Hourly |
| Label kind | Feature only (not a flood label) |
| MVP extract | 3 city centers, 7-day sample committed |

**What it is not:** station rain-gauge observations. Reanalysis has ~2-day delay.

**Leakage:** analysis/reanalysis may be used only up to issue time `t`. ERA5 at `t+h` must not be stored as an observed feature or as a “forecast.” Forecast precip is a named feature only when issued at `t`.

**Acquisition:** `scripts/phase4_fetch_openmeteo.py`. Sample: `src/floodlens/application/data/ml/openmeteo_archive_sample.json`.
