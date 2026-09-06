# Data card: GloFAS discharge (Track A)

| Field | Value |
| --- | --- |
| Dataset | CEMS GloFAS historical river discharge |
| Provider | Copernicus CDS `cems-glofas-historical` |
| License | CEMS-FLOODS / Copernicus open |
| Role | Track A flood-occurrence labels + optional Q lookback |
| Spatial | Nearest **0.05°** cell to each AOI center (**3 cells only**) |
| Time | Daily |
| Label kind | **MODELLED** (LISFLOOD). Never “ground truth observations.” |
| Positive | Daily Q ≥ documented 2-year return period |
| MVP extract | Time series at 3 cells; **global cube forbidden** |

**What it is not:** in-situ gauges, SWE depth, a flood warning, or Track B.

**Return period:** the official GloFAS RP threshold file is `UNAVAILABLE` until CDS extract. Tests use a synthetic modelled series labeled `SIMULATED` with an explicit proxy threshold — not a published RP.

**Acquisition:** `scripts/phase4_extract_glofas.py` (requires CDS credentials; no-op without them).
