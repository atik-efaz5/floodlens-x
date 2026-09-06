# Model provenance

| Model | Status | Kind | Accuracy claim |
| --- | --- | --- | --- |
| Physics Baseline v0.1 | IMPLEMENTED | PHYSICS_BASELINE | none |
| Heuristic forecast | IMPLEMENTED | HEURISTIC | none (`confidence_kind=heuristic`) |
| AI forecast | NOT TRAINED | AI | none |
| Hybrid AI/Physics | NOT_IMPLEMENTED | HYBRID | none |

`GET /api/v1/models` and `GET /api/v1/models/performance` refuse fabricated
accuracy percentages.

Physics output is a short SWE burst forced by meteorological rainfall. Labels:

- `forcing_clock`: meteorological hours
- `solver_clock`: simulation seconds
- `data_status`: `SIMULATED` or `PARTIAL`, never observation/`LIVE`

`GET /api/v1/research/compare` reports physics vs heuristic metrics only
(depth/fraction/validation vs heuristic horizons). Mass-error diagnostics stay
on `/api/v1/research/diagnostics/*`.
