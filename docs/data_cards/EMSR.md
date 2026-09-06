# Data card: CEMS Rapid Mapping (Track B)

| Field | Value |
| --- | --- |
| Dataset | Copernicus EMS Rapid Mapping (EMSR) |
| Provider | Copernicus EMS |
| License | Copernicus open (some activations sensitive/restricted) |
| Role | Track B observed flood occurrence when a delineation polygon intersects the AOI |
| Spatial | Event AOI vectors |
| Time | Event-based (sparse) |
| Label kind | **OBSERVED** (analyst / SAR / optical) |
| Positive | Flood polygon intersects city bounds with area ≥ ε |
| Negative | Mapped “no flood” in that activation — **not** “no activation” |

**Phase 4.1 harvest:** public Rapid Mapping list (`public-activations-info`) had **0** Bangladesh rows among 261 listed activations. Two older public activations are **cited** (EMSR097, EMSR439) from Copernicus/JRC pages. **Polygons were not downloaded.**

**2022 Sylhet / Sunamganj:** documented in GloFAS news and International Charter mapping. No EMSR code is invented. Track B is unavailable for that window until a licensed observed polygon is ingested.

**Cloud / delay:** optical labels with `acquired_at > issue_time t` are forbidden as forecast inputs. Unmapped times: `y_track_b_available=false`.
