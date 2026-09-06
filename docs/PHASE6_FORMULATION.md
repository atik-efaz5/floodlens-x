# Phase 6 formulation status

Phase 6 rebuilds the **spatial forecasting formulation**. It does not train a U-Net or Transformer, does not invent 6–72 h labels, and does not modify `src/floodlens/numerical/**`.

## What changed

- Channel audit (`src/floodlens/ml/spatial/channel_audit.py`): spatial vs TEMPORAL-ONLY vs CONSTANT vs MISSING. CNN refused if fewer than 4 SPATIAL channels.
- Bangladesh AOIs (`aois_v2.py`): haor + floodplain + Dhaka subtiles. Product catalog still has three cities.
- Working tensors: 64×64 GFM clips (`index_local_v2`), Open-Meteo precip lattice, real elevation lattice, HydroRIVERS or OSM distance-to-river.
- Gates 0 / 1 / 2 (`gates.py`). `train_spatial` no longer fits a U-Net. `phase6.py` never calls `mark_spatial_validated`.
- Baselines on v2 tensors: persistence, rain threshold (spatial if lattice exists), logistic, pixel GBDT, RF-style bag, conv-smooth. GBDT is the bar.
- Cards: [SPATIAL_FLOOD_DATASET_V2.md](data_cards/SPATIAL_FLOOD_DATASET_V2.md), [SPATIAL_AI_FLOOD_V2.md](model_cards/SPATIAL_AI_FLOOD_V2.md).

## Honest expectation for Gate 0

The local GFM extract is still the Equi7 **E039N021T3** monsoon scenes already on disk (Phase 5.5: **7 independent 45-day events**). Expanding AOIs on the same tile adds spatial diversity; it does **not** create 20 independent meteorological episodes. Gate 0 is therefore expected to **fail** on `independent_events` until more years/tiles are acquired.

If Gate 0 fails: **do not train a U-Net**. Diagnostic baselines may be written to `src/floodlens/application/data/ml/spatial/phase6_eval.json`. They are not a VALIDATED claim.

## Catalog / API

Public spatial status remains **NOT_TRAINED** / **NOT_VALIDATED**. `POST /api/v1/forecast/ai-spatial` stays UNAVAILABLE. Frontend status text only; no “AI Powered”; no production overlay.

Physics vs spatial AI: **COMPARISON NOT YET COMPARABLE**.

## How to run

```text
python scripts/phase6_acquire.py --skip-features   # 64×64 index from local GFM GeoTIFFs
python scripts/phase6_acquire.py                   # also fetch elevation, rivers, precip lattice (network)
python scripts/phase6_evaluate.py                  # audit + gates + baselines; never VALIDATED
```
