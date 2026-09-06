# Model card: AI-SPATIAL-OCCURRENCE-v0.1 (Phase 5.5)

| Field | Value |
| --- | --- |
| Purpose | Grid-cell flood **occurrence** probability on a city AOI tile at the **next GFM scene** (~8 days). Not a 6/12/24 h nowcast. |
| Model id | `AI-SPATIAL-OCCURRENCE-v0.1` |
| Catalog id | `ai-spatial-forecast` |
| Data | Copernicus GFM ensemble flood extent, OBSERVED, AOI-clipped Equi7 **E039N021T3**. Dataset version `phase55-gfm-aoi-v0.2`. |
| Features at t0 | 24 h precip + 72 h accum (AOI **point**, broadcast), 7-day GloFAS Q (cell, broadcast), lagged completed GFM map, month sin/cos, persistence-valid flag, `precip_is_aoi_point` flag. **6/8 U-Net channels are spatially constant.** No SAR at t+h. No SWE depth. DEM absent (`dem_present=0`). |
| Target | `P(cell flooded at t0+192h)` from GFM class, τ=0.25; unknown ≠ dry |
| Architecture | Baselines: spatial persistence, rainfall threshold, cell climatology, pixel logistic, pixel GBDT, 3×3 conv-smooth. Then Tiny U-Net (8 channels, 2-level, numpy/scipy). |
| Training split | Issue years ≤ 2018 (10 tiles; events 2018-01 dry + 2018-06 monsoon) |
| Validation split | 2019–2021 (34 tiles; three monsoon episodes) |
| Test split | 2022+ including named NE Bangladesh holdout 2022-05-09 … 2022-06-21, plus 2022-07 and 2023 monsoon (19 tiles; two episodes). Geographic holdout: train Dhaka, test Sunamganj/Sylhet (Sylhet uncovered). |
| Event grouping | `event_id` = 45-day meteorological episode. Adjacent city tiles and orbit pairs are **not** extra events. No `event_id` appears in two of {train, val, test}. |
| Metrics | IoU/CSI, Dice, recall, precision, AUPRC, AUROC, Brier. **Accuracy is not the headline metric.** Event-level mean/median/std + worst map. Hard-case subsets. |
| Uncertainty | Split conformal on val pixels; q10/q90 maps. Empirical coverage is measured on test. **Do not claim 80% a priori.** If uncertainty–error rank correlation is weak, the uncertainty map is **not** trustworthy confidence. |
| Status | Internal **TRAINED**. Public catalog **NOT_TRAINED**. Display **TRAINED — NOT VALIDATED**. Does **not** inherit AOI GBDT VALIDATED. Never promoted by Phase 5.5. |
| Failure modes | Broadcast rain cannot locate flood within an AOI; persistence and pixel GBDT beat the Tiny U-Net on this extract (test IoU 0.13 / 0.23 vs U-Net 0.03); Dhaka often dry/nodata; Sylhet uncovered; 8-day GFM ≠ 24 h product; 7 independent events cannot support generalization. |
| Geographic bias | Bangladesh NE/central AOIs only. Not South Asia. Not global. |
| Temporal bias | Monsoon-season GFM scenes; one dry-season 2018 episode; 2022 holdout is one named monsoon pulse. |
| Physics | **COMPARISON NOT YET COMPARABLE** (0.5 s SWE burst vs 8-day SAR occurrence). A comparable benchmark needs hours-to-days hydrodynamics or GloFAS Rapid Flood Mapping on the **same** 192 h / GFM grid. |
| Dataset growth decision | **OPTION A** — limited proof-of-concept only. Expand toward ≥20 independent flood episodes (more years/regions, not more 2-day twins) before any VALIDATED claim. |
