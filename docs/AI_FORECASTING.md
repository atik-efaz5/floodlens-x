# AI flood forecasting (Phase 4)

AOI-level **flood occurrence probability** at meteorological horizons
`6 / 12 / 24 / 48 / 72` h for Dhaka, Sunamganj, and Sylhet.

`p̂(c, t, h) = P(flood at t+h | features up to t)` maps onto `ForecastPoint.probability`.
`expected_depth` stays **null** until depth labels exist.

This is **not** a claim that AI beats physics. The physics product is a **short
SWE burst forced by that hour’s rain**, not 24 h hydrodynamics
([FORECAST_ENGINE.md](FORECAST_ENGINE.md)).

## Label tracks (never mix in one metric table)

| Track | Label | Kind | Density |
| --- | --- | --- | --- |
| **A** | GloFAS Q ≥ 2-year RP at the AOI 0.05° cell | `MODELLED` / `SIMULATED` | Daily |
| **B** | CEMS Rapid Mapping flood polygon intersects AOI | `OBSERVED` | Event-based |

Primary published claims use Track B **when an event polygon exists**.
Track A is the dense development set. Absence of an EMSR map is **not** dry.

## Inputs (MVP)

- 24 hourly precip lookback `t-24h → t` (Open-Meteo archive / ERA5 family)
- Antecedent 24 h and 72 h accumulation (from lookback only)
- Forecast precip **issued at t** (named feature; never ERA5 at `t+h`)
- DEM stats when a windowed GeoTIFF exists (never invented elevations)
- Optional GloFAS Q lookback for Track A (`times ≤ t` only)

Not used: in-situ gauges (none configured), population, physics SWE depth as a
primary-model input, satellite maps acquired after `t`.

## Splits

Do **not** random-split hours.

- **Temporal:** train through 2021, val 2022, test 2023–2024
- **Named holdout:** 2022-05-09 … 2022-06-21 NE Bangladesh window is test-only
- **Geographic:** train other basins, test BD AOIs (required for an “unseen region” claim)

Scalers fit on **train** only. Same event must not straddle train and test.

## Models

Baselines before any DL credit: persistence, monthly climatology, rain-threshold
logistic, gradient boosting (XGBoost-class). Heuristic and physics are scored
separately with clock disclaimers.

LSTM multi-horizon heads are trained **only if** boosting leaves headroom on
val AUPRC. A tiny temporal Transformer is the documented alternative.

Registry: `NOT_TRAINED` → `TRAINED` → `VALIDATED` → `DEPLOYED`.
`GET /api/v1/models` stays `NOT_TRAINED` until **VALIDATED** on a real held-out
split with Track A/B tables. Synthetic development skill is not operational skill.

## Metrics

AUPRC, Brier, BSS vs climatology, recall at fixed precision, CSI at a val-chosen
threshold. **Not** accuracy. Always report n, prevalence, split id, horizon.

## Uncertainty

Quantile residuals + split-conformal 80% intervals on validation.
`confidence_kind` is `conformal` or `quantile`, never heuristic.

## Phase 4.5 real data (not synthetic skill)

The first **real** training set is Open-Meteo Flood API GloFAS v4 daily
`river_discharge` at three AOI cells plus Open-Meteo hourly precip
([OPEN_METEO_FLOOD.md](data_cards/OPEN_METEO_FLOOD.md)).

Labels are **MODELLED** Q-exceedance (empirical 2-year AMS on train years),
not gauges and not flood-extent maps. Horizons **6h and 12h are not labeled**.

Synthetic Track A/B remains **development / pipeline validation only**.
Do not quote synthetic GBDT-vs-persistence scores as real-world skill.

See [AI_FLOOD_FORECAST_v0.1.md](model_cards/AI_FLOOD_FORECAST_v0.1.md).

## Inference

`POST /api/v1/forecast/ai` enqueues a BackgroundTasks job and returns
`FloodForecast` with `model_kind=AI`. No depth raster is invented. Until the
registry is `VALIDATED`, the job result is `UNAVAILABLE`. Supported real
horizons are 24/48/72 h; 6h/12h stay `UNAVAILABLE`.

## Data cards

- [Open-Meteo](data_cards/OPEN_METEO.md)
- [Open-Meteo Flood / GloFAS extract](data_cards/OPEN_METEO_FLOOD.md)
- [GloFAS Track A](data_cards/GLOFAS.md)
- [EMSR Track B](data_cards/EMSR.md)
