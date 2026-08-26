# FloodLens-X Extraction Plan

**Status:** Authoritative extraction sequence  
**Governs:** `docs/NUMERICAL_CONTRACT.md`  
**Source notebook:** `notebooks/source/FloodLens_Colab.ipynb`

---

## Overview

Extraction proceeds in three phases. **Phase A** extracts the validated baseline
without modification. **Phase B** proves equivalence. **Phase C** lists
enhancement candidates that each require a new validation gate before entering
the production solver.

---

## PHASE A — Baseline Extraction

**Goal:** Port validated notebook code into package structure without changing
mathematical behavior.

### A.1 Numerical Kernel

Extract from authoritative cells only:

| Source cell | Destination | Contents |
|-------------|-------------|----------|
| 343 | `src/floodlens/numerical/flux.py` | `F`, `G`, `max_wave_speed_x`, `max_wave_speed_y` |
| 343 | `src/floodlens/numerical/reconstruction.py` | `hydrostatic_reconstruction` |
| 343 | `src/floodlens/numerical/riemann.py` | `rusanov_flux` |
| 343 | `src/floodlens/numerical/sources.py` | `calculate_bed_slope_source_terms`, `calculate_manning_source_terms` |
| 146 | `src/floodlens/numerical/timestep.py` | `calculate_dt_cfl` (preserve `C=0.9` default and `dt_initial` fallback behavior) |
| 301 | `src/floodlens/numerical/timestepper.py` | `run_shallow_water_simulation` |

**Extraction rules:**
- Copy logic verbatim; refactor only for imports and module boundaries.
- Preserve hard-coded `C=0.9` and global `dt_initial=0.01` fallback exactly.
- Do not add rainfall, infiltration, or inflow handling.
- Do not import vectorized functions from cell 24 or cell 121.

### A.2 Core API (Merged)

Merge cells 522, 525, 526, 514, 532, 533 into `src/floodlens/core/`:

| Merged class | Source cells | Required methods |
|-------------|-------------|-----------------|
| `SimulationConfig` | 522 | As defined |
| `GridData` | 522 | As defined |
| `SimulationState` | 522 | Fields: `U`, `z`, `time`, `iteration` |
| `SimulationResult` | 525 | As defined |
| `BoundaryCondition` | 522 | As defined (documented as unused in baseline) |
| `DiagnosticsReport` | 532 | As defined |
| `ShallowWaterSimulator` | 525 + 526 + 514 | `__init__`, `set_initial_conditions`, `run`, `get_state`, `get_result`, `get_grid`, `velocity`, `save_simulation`, `load_simulation` |
| `ShallowWaterSimulatorWithDiagnostics` | 533 | Overrides `run`, `velocity`; inherits merged base |

`run()` must call the extracted cell-301 timestepper with the same argument
mapping as cell 526.

### A.3 Application Layer

| Source cell | Destination | Contents |
|-------------|-------------|----------|
| 538 | `src/floodlens/application/input_manager.py` | `InputManager` |
| 538 | `src/floodlens/application/progress.py` | `ProgressManager` (replace Colab `clear_output` with logging callback) |
| 538 | `src/floodlens/application/service.py` | `SimulationService` |
| 554 | `src/floodlens/application/dem_manager.py` | `DEMManager` |

### A.4 Visualization Layer

| Source cell | Destination | Contents |
|-------------|-------------|----------|
| 544 | `src/floodlens/visualization/layer.py` | `VisualizationLayer` |

### A.5 Package Infrastructure

- `pyproject.toml` or `requirements.txt` with: `numpy`, `scipy`, `matplotlib`
- `.gitignore` for Python artifacts
- `src/floodlens/__init__.py` with public API exports

---

## PHASE B — Regression Tests

**Goal:** Prove extracted package reproduces validated notebook behavior before
any enhancements.

Port gate logic to `src/floodlens/validation/` and `tests/`:

| Test | Source | Pass criterion |
|------|--------|---------------|
| Lake-at-rest equivalence | Cell 530, scenario 1 | max abs error < 1e-15 |
| Dam-break equivalence | Cell 530, scenario 2 | max abs error < 1e-15 |
| Dry-cell rain equivalence | Cell 530, scenario 3 | max abs error < 1e-15 (API/oracle only; rain has no effect) |
| Diagnostic transparency | Cell 534 | bit-perfect match |
| Persistence round-trip | Cell 530, section 4 | `U` arrays equal after save/load |
| Well-balancedness | Phase 11.0C lake-at-rest | momentum residual < 1e-13 |

**Regression methodology:**
1. Run notebook gate cells in Colab (or cached reference outputs) to produce reference `U` arrays.
2. Run equivalent tests against extracted package with identical inputs.
3. Compare final state arrays element-wise.

**Phase B gate:** All tests pass. No Phase C work begins until Phase B passes.

---

## PHASE C — Enhancement Candidates

Each enhancement is **out of scope for baseline extraction**. Each requires a
**new validation gate** before it may be considered part of the production solver.

### C.1 Configurable CFL

**Change:** Wire `SimulationConfig.CFL` to `calculate_dt_cfl`; remove global
`dt_initial` dependency; pass `dt_initial_sim` or explicit fallback parameter.

**Validation gate required:**
- Re-run all Phase B tests with `CFL=0.9` and confirm bit-identical results to baseline.
- Add test with `CFL=0.5` confirming proportionally smaller timesteps.

**Status:** Enhancement only. Not part of baseline.

### C.2 Real Rainfall / Infiltration

**Change:** Port `S_ext[:,:,0] = rainfall - infiltration` from cell 121 into
cell-301 timestepper (or equivalent extracted timestepper).

**Validation gate required:**
- Mass conservation test with known rain rate over flat bed.
- Bit-perfect equivalence is NOT expected vs baseline (baseline ignores rain).
- New reference solutions required.

**Status:** Enhancement only. Do not import during Phase A.

### C.3 Configurable Boundaries

**Change:** Wire `BoundaryCondition` dataclass and `inflow_boundary_params` into
timestepper; support inflow/outflow/open BC types.

**Validation gate required:**
- Reflective BC regression: must still pass all Phase B tests with
  `{'location': 'none'}` (default).
- New tests for each BC type against known analytical or reference solutions.

**Status:** Enhancement only. Baseline remains reflective-only.

### C.4 Full 2D Vectorization

**Change:** Vectorize Y-flux and boundary handling; replace scalar loops in
cell 301 with `vectorized_*` equivalents.

**Validation gate required:**
- Bit-perfect match vs scalar baseline (cell 301) on all Phase B scenarios.
- Performance benchmark showing speedup at N ≥ 200.

**Status:** Enhancement only. Partial X-flux vectorization (cells 24, 121) is
not sufficient evidence.

### C.5 Production API Cleanup

**Change:** Unify fragmented class definitions; add
`ShallowWaterSimulatorWithDiagnostics.load_simulation`; replace Colab-specific
`clear_output`; normalize `time` vs `current_time`; add `get_state()` to base
class without monkey-patching.

**Validation gate required:**
- All Phase B tests pass after refactor.
- No numerical state change (API-only refactor).

**Status:** Structural cleanup allowed during Phase A merge if behavior
preserved; full cleanup is Phase C with regression confirmation.

---

## Module Map Summary

```
src/floodlens/
├── numerical/
│   ├── flux.py           ← cell 343
│   ├── reconstruction.py ← cell 343
│   ├── riemann.py        ← cell 343
│   ├── sources.py        ← cell 343
│   ├── timestep.py       ← cell 146
│   └── timestepper.py    ← cell 301
├── core/
│   ├── config.py         ← cell 522 (SimulationConfig, BoundaryCondition)
│   ├── grid.py           ← cell 522 (GridData)
│   ├── state.py          ← cell 522 (SimulationState)
│   ├── result.py         ← cell 525 (SimulationResult)
│   ├── diagnostics.py    ← cell 532 (DiagnosticsReport)
│   └── simulator.py      ← cells 525+526+514+533 (merged)
├── application/
│   ├── input_manager.py  ← cell 538
│   ├── progress.py       ← cell 538
│   ├── service.py        ← cell 538
│   └── dem_manager.py    ← cell 554
├── visualization/
│   └── layer.py          ← cell 544
└── validation/
    ├── equivalence.py    ← cell 530 gate logic
    └── diagnostics_gate.py ← cell 534 gate logic

tests/
├── test_equivalence.py   ← Phase B
├── test_diagnostics.py   ← Phase B
└── test_persistence.py   ← Phase B
```

---

## EXTRACTION GO/NO-GO

### GO — Baseline Extraction (Phase A + Phase B)

Baseline extraction may proceed. The forensic audit resolved all critical
ambiguities. The authoritative source cells are identified, validated
limitations are documented, and protected invariants are defined. Extracting
cells 301 + 343 + 146 and the merged API (522/525/526/514/533) with no
mathematical changes is safe, provided Phase B regression tests are implemented
and pass before the baseline is declared complete.

### NO-GO — Enhancement Implementation (Phase C)

Do not implement Phase C enhancements until:
1. Phase B regression tests pass against the extracted baseline.
2. Each enhancement has its own validation gate defined above.
3. Explicit approval is obtained for any change to protected numerical invariants.

Specifically **do not** during initial extraction:
- Add rainfall/infiltration (cell 121 logic)
- Wire configurable boundaries
- Replace scalar solver with vectorized solver
- Change CFL behavior from hard-coded `C=0.9`
