# Model card: AI-SPATIAL-OCCURRENCE-v2 (Phase 6)

| Field | Value |
| --- | --- |
| Purpose | Grid-cell flood **occurrence** probability on a Bangladesh AOI tile at the **next GFM scene** (~8 days / 192 h). Not a 6/12/24 h nowcast. Not flood depth. |
| Model id | `AI-SPATIAL-OCCURRENCE-v2` |
| Catalog id | `ai-spatial-forecast` (same public catalog row; v0.1 remains the Phase 5.5 checkpoint) |
| Status | **NOT_TRAINED** for the public catalog until **Gate 2**. Internal v2 training of a CNN is **refused** until Gate 0 and Gate 1 pass. This card does **not** contain claimed skill numbers. |
| Data | GFM OBSERVED 192 h occurrence. Dataset `phase6-gfm-spatial-v2`. See [SPATIAL_FLOOD_DATASET_V2.md](../data_cards/SPATIAL_FLOOD_DATASET_V2.md). |
| Features at t0 | Precip 24 h / 72 h **lattice** (spatial if ≥4 points), GloFAS Q 7-day (scalar), last completed GFM, elevation, slope, distance-to-river, month, i/j. Broadcast-only rain/Q/month are TEMPORAL-ONLY, not convolutional features. |
| Channel audit | Per-channel spatial variance, temporal variance, unique-value fraction, missingness. **CNN refused if &lt;4 SPATIAL channels.** |
| Target | `P(cell flooded at t0+192h)` from GFM class, τ=0.25; unknown ≠ dry |
| Protocol | Baselines first, same event-aware splits: (1) spatial persistence, (2) spatially varying rain threshold, (3) pixel logistic (distance-to-river + rain + DEM), (4) pixel GBDT, (5) pixel RF-style bag, (6) 3×3 conv-smooth of persistence. **Pixel GBDT is the bar.** Tiny U-Net is not a baseline to beat by architecture change. |
| Primary v2 model | Spatial **pixel GBDT / RF** if Gate 0 passes. A small U-Net is a **secondary experiment only** after Gate 1 (GBDT test IoU &gt; persistence on event holdout, ≥10 train events, ≥4 spatial channels). ConvLSTM / spatiotemporal Transformer / GNN are not Phase 6 primary. |
| Loss (if a CNN is ever allowed) | Masked BCE + Dice (or Tversky). Unknown excluded. Accuracy is not reported. |
| Gates | **Gate 0** (dataset freeze, required even for GBDT v2): ≥20 independent 45-day events; ≥3 AOIs with valid GFM; ≥4 spatial channels; DEM present and not synthetic; lattice rain on a majority of tiles; unknown never dry; no train/test event leak; OBSERVED labels only. **Gate 1** (DL allowed): Gate 0 + GBDT &gt; persistence + ≥10 train events. **Gate 2** (VALIDATED catalog): Gate 1 + event-level mean/median/std IoU/AUPRC, geographic holdout not collapsed to 0, conformal coverage reported without claiming 80% a priori, uncertainty informative or omitted. |
| If Gate 0 fails | **Stop.** Expand data. Do not tune a U-Net. Diagnostic baselines on available tensors may still be logged; they are not a catalog claim. |
| Uncertainty | Do not ship Phase 5.5 q10/q90 as confidence. Omit until empirical coverage and uncertainty–error rank correlation (&gt; 0.1) are shown on test events. Else mark `UNCALIBRATED` or omit. |
| API | `POST /api/v1/forecast/ai-spatial` stays **UNAVAILABLE** / catalog **NOT_VALIDATED** until Gate 2. 6/12/24/48/72 h remain UNAVAILABLE. No production overlay. |
| Physics | **COMPARISON NOT YET COMPARABLE** vs the 0.5 s SWE burst. A later Phase 7 comparison would need GloFAS Rapid Flood Mapping or hours-to-days SWE on the **same** 64×64 grid and 192 h clock. Out of Phase 6 training. |
| Geographic bias | Bangladesh haor / central floodplain AOIs only. Not South Asia. Not global. |
| Failure modes (known from Phase 5.5, still in force) | Broadcast features cannot locate flood; 7 events cannot identify event-level skill; geographic holdout IoU 0 on Sunamganj with v0.1 features; conformal uninformative. |
| Metrics table | Empty on purpose. No fabricated IoU/Dice/AUPRC. Fill only after Gate 2 evidence exists. |

## Metrics (empty until Gate 2)

| Split | Model | IoU | Dice | AUPRC | AUROC | n_events | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test | persistence | — | — | — | — | — | not reported |
| test | pixel_gbdt | — | — | — | — | — | not reported |
| test | pixel_rf | — | — | — | — | — | not reported |
| geographic holdout | pixel_gbdt | — | — | — | — | — | not reported |

Do not copy Phase 5.5 numbers onto this v2 card. Those describe 32×32 broadcast-feature tensors, not this formulation.
