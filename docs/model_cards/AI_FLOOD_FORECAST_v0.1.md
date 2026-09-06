# Model card: AI Flood Forecast v0.1

**Status:** `VALIDATED` on a held-out temporal split of **MODELLED** GloFAS river-discharge exceedance.  
**Not** a flood-extent model. **Not** a gauge model. **Not** a 6–72 h hydrodynamic forecast.  
Synthetic Track A/B scores are **development / pipeline validation only** and are not reported here.

## Purpose

AOI-level **flood occurrence** probability at issue time `t` (00:00 UTC) for
Dhaka, Sunamganj, and Sylhet. Target is binary: whether GloFAS v4 daily
`river_discharge` on the `valid_at` UTC date meets or exceeds a train-only
empirical ~2-year threshold (median of annual maxima, 2015–2021).

Shipped artifact: numpy gradient boosting (`xgboost_class`), model id
`FLOOD-OCCURRENCE-GBDT-v0.1`.

## Training data

| Field | Value |
| --- | --- |
| Dataset | Open-Meteo Flood API GloFAS v4 daily Q + Open-Meteo archive hourly precip |
| Card | [OPEN_METEO_FLOOD.md](../data_cards/OPEN_METEO_FLOOD.md) |
| Version | `phase4.5-openmeteo-glofas-v1` |
| Snapshot | `discharge_2015_2024.json` (sha256 `81943d2f…`), `precip_2014_2024.json` |
| Samples | 32,850 (3 cities × daily issues × horizons 24/48/72) |
| Time range | issue times 2015-01-01 … 2024-12-31 |
| Coverage | 3 GloFAS cells snapped to city centers (not a basin-wide map) |
| Label kind | `MODELLED` |
| Credentials | none (public HTTPS) |

### Labels

| Class | Definition |
| --- | --- |
| Positive | daily Q on `valid_at` date ≥ city-specific train-only median AMS |
| Negative | modelled Q below that threshold |
| Unknown | missing Q — **dropped**, never coded dry |

Train-only AMS thresholds (m³/s): Sunamganj 50.76, Dhaka 83.92, Sylhet 25.85.

Horizons **6 h and 12 h are not labeled**. Daily Q cannot support sub-daily targets.

## Input features (known at issue time `t`)

All features use information strictly before `t` (precip `t-24h … t-1h`; Q `t-7d … t-1d`).

- 24 hourly precipitation lookback
- accumulation windows 1 / 3 / 6 / 12 / 24 / 48 / 72 h
- log1p of last complete daily Q and a Q-present flag
- month sine/cosine
- horizon hours (24, 48, or 72)

**Excluded (not known at `t`, or unavailable):** future rainfall, ERA5 at `t+h`,
issue-day Q, future GloFAS Q, EMSR/satellite maps, DEM (unset), in-situ gauges,
physics SWE depth, future aggregated statistics.

## Prediction target

`P(flood occurrence at t+h | features ≤ t)` for `h ∈ {24, 48, 72}`.
`expected_depth` is always null. No flood-extent overlay.

## Evaluation split

Leakage-safe **temporal** split (no random rows):

| Split | Rule | n | Prevalence |
| --- | --- | ---: | ---: |
| Train | issue_time < 2022-01-01 | 23,004 | — |
| Validation | 2022 except named holdout | 2,889 | **0** |
| Test | 2023–2024 plus 2022-05-09…2022-06-21 NE Bangladesh holdout | 6,957 | 0.0259 |

**Why val prevalence is zero:** the 2022 monsoon peak for these cells falls in the
named holdout (test-only). Thresholds were fit on 2015–2021 AMS only. 2022 outside
the holdout never reached those thresholds. AUPRC/AUROC on val are **undefined**,
not zero.

Operating threshold and conformal residuals therefore used an **inner tune** on
train years **2020–2021** (not the test set).

**Geographic holdout (additional):** train Dhaka+Sylhet temporal-train; test
Sunamganj temporal-test (n=2,319, prevalence 0.066).

## Metrics (held-out TEST, Track A MODELLED)

Do **not** report accuracy. Rare-event metrics first.

Operating threshold = **0.15** (F1 on 2020–2021 inner tune).

| Model | AUPRC | Recall | F1 | AUROC | Brier |
| --- | ---: | ---: | ---: | ---: | ---: |
| Persistence (`y` at `t-1`) | **0.507** | 0.667 | **0.667** | 0.829 | **0.017** |
| Climatology (month) | 0.181 | 0.000 | 0.000 | 0.862 | 0.024 |
| Logistic regression | 0.182 | 0.228 | 0.216 | 0.920 | 0.024 |
| GBDT (`xgboost_class`) | 0.276 | 0.200 | 0.258 | **0.940** | 0.022 |

GBDT **does not beat persistence** on AUPRC or F1. That is expected: labels are
**daily Q exceedance**, which is strongly autocorrelated. Persistence is the
correct skill reference. GBDT ranks better (AUROC) but is worse on
precision-recall.

Geographic Sunamganj holdout: persistence AUPRC 0.589 vs GBDT 0.327 (same pattern).

By horizon (GBDT AUPRC): 24 h 0.297, 48 h 0.289, 72 h 0.258.

## Deep model

**Not trained.** TinyLSTM packing requires all five production horizons including
6 h / 12 h. Fabricating those labels would be invalid. The data are tabular AOI
series, not rasters or a river graph, so ConvLSTM / GNN are not justified.
GBDT is the appropriate first learned model; persistence remains the stronger
baseline.

## Uncertainty

Split-conformal 80% intervals on `|y − p|` using the 2020–2021 inner tune.

| Set | Empirical coverage | Target |
| --- | ---: | ---: |
| Inner tune (2020–2021) | 0.801 | 0.80 |
| Held-out test | 0.830 | 0.80 |

Coverage is close to the nominal 80% level. The half-width (`q80` ≈ 0.022) is
narrow because most probabilities are small. This is **not** a decorative
confidence score; it is residual conformal on a rare binary label.

## Physics comparison

**LIMITED / not like-for-like.** Physics Baseline v0.1 is a **short SWE burst**
forced by that hour’s rain. Solver seconds are not meteorological hours. SWE
flood fraction is not GloFAS Q exceedance. No conversion was invented.
`n_paired = 0`; physics test metrics are **null**, not zero.

## Known failure modes

From the test set at threshold 0.15 (GBDT): 144 false negatives, 63 false positives,
6,750 correct (mostly true negatives).

- **AI misses (FN):** Dhaka 2024-05-25/26, dry 24 h rain (~0–0.4 mm), low Q
  lookback (~14 m³/s vs 83.9 threshold), but valid_at Q later exceeds. Persistence
  of low Q hid a later jump.
- **AI false alarms (FP):** Sunamganj 2022-06-18 (named holdout), 96 mm / 24 h and
  Q 40.9 vs 50.8 threshold — wet but still below AMS. Physics SWE would also be
  expected to wet the grid; that is not evidence that SWE “got the Q label right.”
- **Persistence succeeds** whenever exceedance lasts several days (the common case).
- **Both fail** when Q jumps across the AMS threshold inside the horizon with little
  antecedent rain or Q (flashy modelled hydrograph vs lagged features).

## Deployment constraints

- Catalog `GET /api/v1/models` shows `VALIDATED` only after this held-out eval.
- `POST /api/v1/forecast/ai` is `UNAVAILABLE` until `VALIDATED`.
- Live inference needs ≥80% complete hourly precip lookback **and** GloFAS Q for
  `t-7d … t-1d`. The committed Q snapshot ends **2024-12-31**; later issue dates
  require the public Open-Meteo flood API. Missing Q is **not** treated as dry.
- 6 h / 12 h points stay `UNAVAILABLE`.
- No depth raster. No accuracy percentage in the UI.

## Data freshness assumptions

Training used Open-Meteo GloFAS **reanalysis-style** daily Q and archive precip
retrieved 2026-09-02. Operational GloFAS forecasts are a different product and
were **not** used as labels or as future-rain features.

## Reproducibility

- Run id: `real-A-62e492594d5f5fa6`
- Seed: 7
- GBDT: 30 trees, learning rate 0.08, numpy stumps (not the `xgboost` package)
- Feature scaler: train split only
- Software: floodlens-x phase 4.5 numpy GBDT
- Artifact: `src/floodlens/application/data/ml/real/checkpoint.json`
