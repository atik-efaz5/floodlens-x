# FloodLens-X Numerical Contract

**Status:** Authoritative extraction contract  
**Source:** Forensic audit of `notebooks/source/FloodLens_Colab.ipynb`  
**Date:** 2026-08-26

This document defines the validated numerical baseline for FloodLens-X extraction.
All baseline extraction work must conform to this contract. Deviations require
explicit approval and new validation gates.

---

## 1. Validated Baseline

### 1.1 Production Timestepper

| Component | Authoritative cell | Notes |
|-----------|-------------------|-------|
| Full 2D scalar timestepper | **301** | `run_shallow_water_simulation` — last definition before Phase 11 gates |
| Active kernel functions at Phase 11 gates | **343** | `F`, `G`, `rusanov_flux`, `hydrostatic_reconstruction`, `max_wave_speed_x`, `max_wave_speed_y`, `calculate_bed_slope_source_terms`, `calculate_manning_source_terms` |
| CFL / timestep selection | **146** | `calculate_dt_cfl` |

**Dependency chain (validated Phase 11.0C / 11.0D behavior):**

```
run_shallow_water_simulation (301)
  → calculate_dt_cfl (146)
  → hydrostatic_reconstruction (343)
  → rusanov_flux (343) + F/G (343) + max_wave_speed_x/y (343)
  → calculate_bed_slope_source_terms (343)
  → calculate_manning_source_terms (343)
```

**Not part of the validated baseline:**
- Cell **121** (X-flux-only vectorized timestepper; superseded by 301)
- Cell **24** vectorized kernels (validated only as X-flux sub-operator, not production solver)

### 1.2 Boundary Conditions

The only validated active boundary behavior is **reflective walls**, hardcoded in cell 301:
- X-direction: momentum `hu` negated at left/right ghosts
- Y-direction: momentum `hv` negated at bottom/top ghosts
- Bed elevation mirrored at boundaries (`z_ghost = z_internal`)
- Hydrostatic reconstruction applied at boundary interfaces before Rusanov flux

### 1.3 Public API (Merged Specification)

The validated API is a **merge** of these notebook cells:

| Cell | Contribution |
|------|-------------|
| **522** | `BoundaryCondition`, `SimulationConfig`, `GridData`, `SimulationState` |
| **525** | `SimulationResult`; `ShallowWaterSimulator` constructor, `set_initial_conditions`, `save_simulation`, `load_simulation` |
| **526** | `run()`, `get_result()` (monkey-patched onto class from 525) |
| **514** | `get_state()`, `get_grid()`, `velocity` property |
| **533** | `ShallowWaterSimulatorWithDiagnostics`, `DiagnosticsReport` integration |
| **532** | `DiagnosticsReport` schema |

`SimulationState` uses field name **`time`** (cell 522), not `current_time`.

---

## 2. Known Validated Limitations

The following behaviors are documented facts of the validated baseline. They are
**not bugs to fix during extraction** — they are constraints to preserve until
enhancement phases pass new validation gates.

| Limitation | Evidence |
|------------|----------|
| Rainfall/infiltration accepted by API but **ignored** by active cell 301 | Parameters appear only in function signature; no assignment in body |
| Inflow/outflow parameters accepted but **ignored** by active cell 301 | `inflow_boundary_params` in signature only; API hardcodes `{'location': 'none'}` |
| CFL uses **hard-coded `C=0.9`** | `calculate_dt_cfl(..., C=0.9)` default; never passed from config |
| `dt_initial=0.01` is a **global fallback** dependency | Set in cell 140; referenced in cell 146 fallback branch |
| `SimulationConfig.CFL` is **not wired** to the validated timestepper | No call path passes `config.CFL` to `calculate_dt_cfl` |
| API class definitions require an **explicit merge** | Cell 525 drops `run()`/`get_state()`; cell 526 patches `run()` only |
| **No validated full-2D vectorized** production solver | Phase 10 vectorization (cells 24, 121) validated X-flux sub-operator only; superseded before Phase 11 gates |
| `ShallowWaterSimulatorWithDiagnostics.load_simulation` **does not exist** | Cell 600 references it; only base class `load_simulation` defined in 525 |
| `BoundaryCondition` dataclass (522) is **defined but unused** | Zero references in timestepper or `run()` |

---

## 3. Protected Invariants

During baseline extraction (Phase A), the following invariants **must not be violated**:

1. **Do not silently change mathematical behavior** during baseline extraction.
   Extracted code must reproduce notebook gate behavior bit-for-bit (within
   floating-point tolerance established by Phase 11.0C: max abs error < 1e-15).

2. **Do not import rainfall/infiltration from cell 121** into the baseline.
   Cell 121 is superseded and its rain/infil logic was never validated against
   the Phase 11 oracle (cell 301).

3. **Do not replace reflective BCs with configurable BCs** in the baseline.
   Only reflective walls are validated. `BoundaryCondition` and inflow parameters
   are out of scope for Phase A.

4. **Do not replace hard-coded CFL behavior** (`C=0.9`, global `dt_initial=0.01`)
   before regression validation confirms identical timestep selection.

5. **Do not treat partial X-flux vectorization (cells 24, 121) as the production
   solver.** The validated production path is scalar full-2D (cell 301).

6. **Do not modify numerical equations, flux formulations, source-term
   discretizations, or validated constants** unless explicitly approved per
   `.cursor/rules/floodlens-core.mdc`.

---

## 4. Validation Requirements

Before any enhancement (Phase C), the extracted baseline must pass regression
tests (Phase B) that reproduce validated notebook behavior:

### 4.1 Numerical Equivalence (Phase 11.0C scenarios)

| Scenario | Initial condition | Steps | Rainfall |
|----------|------------------|-------|----------|
| Lake-at-rest | WSE = 2.0 on parabolic bowl | 10 | 0 |
| Dam-break | h = 1.5 left / 0.1 right at x = 5 | 50 | 0 |
| Dry-cell rain | U = 0 | 20 | 1e-4 m/s |

**Pass criterion:** max absolute error < 1e-15 between extracted package and
notebook oracle (cell 301 + cell 343 kernel).

Note: The "Dry-cell rain" scenario validates API/oracle equivalence only.
Rain has no effect on either path with cell 301 active. Do not interpret a pass
as validation of rainfall physics.

### 4.2 Diagnostic Transparency (Phase 11.0D)

Bit-perfect match between `ShallowWaterSimulatorWithDiagnostics.run()` and
direct `run_shallow_water_simulation` call on parabolic bowl, 50×50 grid.

### 4.3 Persistence Round-Trip

Save/load via `.npz` must preserve `U`, `z`, `time`, `iteration`, and config.

### 4.4 Well-Balancedness

Lake-at-rest on sloped terrain: momentum residual < 1e-13 after 10 steps.

---

## 5. Intended Destination Modules

| Notebook source | Destination module |
|----------------|-------------------|
| Cell 343: F, G, wave speeds, rusanov, HR | `src/floodlens/numerical/flux.py`, `riemann.py`, `reconstruction.py` |
| Cell 343: bed slope, Manning | `src/floodlens/numerical/sources.py` |
| Cell 146: CFL | `src/floodlens/numerical/timestep.py` |
| Cell 301: timestepper | `src/floodlens/numerical/timestepper.py` |
| Cells 522/525/526/514/533 | `src/floodlens/core/` |
| Cells 538, 554 | `src/floodlens/application/` |
| Cell 544 | `src/floodlens/visualization/` |
| Cells 530, 534 gate logic | `src/floodlens/validation/` |

---

## 6. Python Dependencies (Baseline)

| Package | Required for |
|---------|-------------|
| `numpy` | All numerical kernel and API code |
| `scipy` | `DEMManager` only (`RegularGridInterpolator`) |
| `matplotlib` | `VisualizationLayer` only |

Stdlib: `dataclasses`, `json`, `typing`, `time`.

Not required for baseline numerical core: `pandas`, `IPython`.
