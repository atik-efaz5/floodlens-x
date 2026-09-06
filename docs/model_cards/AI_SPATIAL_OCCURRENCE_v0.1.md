# Model card: AI-SPATIAL-OCCURRENCE-v0.1

| Field | Value |
| --- | --- |
| Model id | `AI-SPATIAL-OCCURRENCE-v0.1` |
| Catalog id | `ai-spatial-forecast` |
| Task | Grid-cell flood **occurrence** probability on a city AOI tile |
| Input | 24 h precip lookback + 72 h accum (AOI point, not radar), 7-day GloFAS Q (cell), lagged previous GFM map, month. No SAR at t+h. No SWE depth. DEM unset. |
| Target | P(cell flooded) from GFM ensemble extent, τ=0.25 on resampled cells, 8-day / next-scene horizon (192 h) |
| Architecture | Persistence / climatology / rain-threshold / pixel GBDT, then one Tiny U-Net with precip/Q broadcast channels |
| Status | Public catalog **NOT_TRAINED** until VALIDATED on held-out maps. Display **TRAINED — NOT VALIDATED**. Does **not** inherit AOI GBDT VALIDATED. See `docs/model_cards/SPATIAL_AI_FLOOD_v0.1.md`. |
| Label kind | OBSERVED (GFM). Do not mix with MODELLED Q or DERIVED fusion in one table. |
| Splits | Train issue years ≤ 2018; val 2019–2021; test 2022 named NE Bangladesh holdout + later. No pixel-i.i.d. split. |
| Uncertainty | Split conformal on pixel residuals; q10/q90 maps |
| What this is not | Not a 6/12/24 h forecast. Not a depth model. Not global. Not “AI beats physics.” Physics remains a sub-second SWE burst (**COMPARISON NOT YET COMPARABLE**). |
