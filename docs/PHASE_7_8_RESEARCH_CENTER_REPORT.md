# PHASE 7.8 — Research Center + Scientific Diagnostics Integration

**Date:** 2026-09-03  
**Scope:** Expose existing SWE diagnostics in an auditable Research workspace.  
**Not in scope:** solver rewrites, stabilization hacks, spatial-AI training, Target-B training, fabricated metrics.

Scientific freeze (unchanged):

| Item | Status |
|---|---|
| Spatial AI | NOT_VALIDATED |
| Spatial API | UNAVAILABLE |
| Target B | PARTIALLY FEASIBLE |
| Model training | NOT AUTHORIZED |
| Physics vs spatial AI | NOT_COMPARABLE |
| Solver (`src/floodlens/numerical/**`) | unmodified |

---

## 1. Research workspace

Command Center **Research** (researcher/admin) is a dedicated scientific UI: `frontend/src/platform/ResearchCenter.jsx`.

Navigation: Overview, Lake at Rest, Parabolic Bowl, Conservation, Spectral, Perturbation, Flux/Source, Interface Balance, Jacobian, Long-Term Stability, AI Experiments, Provenance.

Operational Explore/Forecast chrome is unchanged. Pause is **UNAVAILABLE**.

## 2. Diagnostics inventory

`GET /api/v1/research/inventory` lists each diagnostic with source, input, output, units, meaning, limitations, UI readiness.

Runners wrap `ShallowWaterSimulatorWithDiagnostics` and public kernels (`calculate_dt_cfl`, `hydrostatic_reconstruction`, `rusanov_flux`, `calculate_bed_slope_source_terms`). Full grids are not returned; maps are subsampled (≤8×8) and series capped (≤32).

## 3. Lake-at-Rest

`GET/POST` suite `lake_at_rest`. Still-water on the synthetic parabolic bowl. Tolerance **unchanged**: `momentum_residual < 1e-10`. Criteria: finite state, no negative depth, momentum near zero. Initial/final mass, velocity, residuals, CFL, maps. Residuals are not clipped.

## 4. Parabolic bowl

Suite `parabolic_bowl`. Dry-start bowl with existing `InputManager.generate_parabolic_bowl`. Shows WSE, depth, velocity, mass, residuals, dt, CFL. Pause unsupported.

## 5. Conservation

Mass initial/final/relative error (m³, relative) and momentum residual (m²/s) with stated tolerances. Scientific notation in the UI. PASS/FAIL only from those numbers.

## 6. CFL / timestep

`calculate_dt_cfl` on the current state: `dt`, min/max CFL, step count. Note: **CFL is not proof of global stability.**

## 7. Boundary diagnostics

Validated active BC: **reflective walls**. Type and reflection rule are shown. Quality inferred from BC type: **UNAVAILABLE**.

## 8. Spectral analysis

`numpy.fft.rfft2` of `hu`. Nyquist-mode energy, ratio, low/high band energy, anti-symmetry ratio, amplitude head, Nyquist-ratio series. High-frequency content is **not** labeled UNSTABLE; no project criterion exists.

## 9. Perturbation testing

Checkerboard `hu` seeds at `1e-15`, `1e-12`, `1e-9`. Reports initial/final amplitude, growth factor, curve. Amplification is not hidden and is not auto-classified “solver unstable.”

## 10. Flux / source

Existing Rusanov + hydrostatic reconstruction + bed-slope source. Flux-divergence, topographic source, combined RHS norms and capped maps (hu). Hydrostatic-balance inspection, not a rewritten timestepper.

## 11. Interface balance

Selectable face `(i,j,direction)`. Left/right/reconstructed states, pressure flux, and Rusanov flux come from the existing kernels. Combined residual is the **cell finite-volume residual** (`source − flux divergence`) at `(i,j)` from `_flux_source_fields`, not a simplified face-only fake balance.

## 12. Jacobian

Local 3×3 finite-difference Jacobian of the FV residual at one cell (neighbors frozen). Eigenvalues and spectral radius. Banner:

LOCAL JACOBIAN SPECTRAL RADIUS IS NOT BY ITSELF PROOF OF GLOBAL LONG-TERM STABILITY.

`global_stability_proof: false`.

## 13. Long-term stability

Outer steps 20 (legacy GET), 50, 100, 500. Mass, momentum drift, equilibrium residual, negative depth, NaN/Inf, Nyquist series, max velocity/depth. Mid-run death: **FAILED AT STEP N**, never COMPLETED.

## 14. AI experiment center

`GET /api/v1/research/ai`

- Track A / AOI GBDT: registry status; AOI task only  
- Target B: PARTIALLY FEASIBLE, NOT TRAINED  
- Spatial AI: NOT_VALIDATED, API UNAVAILABLE, metrics null  
- Uncertainty: not calibrated (metrics ≠ confidence)  
- Model training: NOT AUTHORIZED  

## 15. Physics vs AI

**PHYSICS VS SPATIAL AI: NOT_COMPARABLE** — target, resolution, forcing, and horizon mismatch. No comparison chart.

## 16. Uncertainty

`calibrated: false`. Status `not calibrated`. Performance is not converted to confidence.

## 17. Reproducibility

Every run stores `experiment_id`, `config_hash`, `solver_version`, timestamp, dataset/version. `GET /api/v1/research/experiments/{id}` reopens the stored snapshot.

## 18. Provenance

Each payload: source, solver version (`SW-SOLVER-v0.6`), config, experiment ID, timestamp, artifact version, `data_status=SIMULATED`. These are solver diagnostics, not observations.

## 19. RBAC

`research.read`: researcher, admin. General/emergency: 403 on research routes. Assistant tools `get_lake_at_rest_status`, `get_equilibrium_residual`, `get_nyquist_energy`, `get_spectral_radius`, `get_run_failure`, `generate_research_report` require `research.read`.

## 20. Testing

`tests/test_phase78_research_center.py`: RBAC, NOT_RUN overview, Lake-at-Rest / bowl / conservation / CFL / boundary, spectral, perturbation, flux, interface, Jacobian disclaimer, long-term, FAILED AT STEP 40 report, experiment reopen, AI freeze, assistant RBAC, frontend copy.

## 21. Browser / E2E

Verified in the IDE browser (Researcher role):

- Command Center **Research** nav appears only for Researcher/Admin.
- Overview shows **NOT_RUN** cards before any experiment.
- Lake-at-Rest workspace: Run / Reset; Pause **UNAVAILABLE**.
- All diagnostic tabs present: Overview, Lake at Rest, Parabolic Bowl, Conservation, Spectral Analysis, Perturbation, Flux / Source, Interface Balance, Numerical Jacobian, Long-Term Stability, AI Experiments, Provenance.
- Banner states Spatial AI **NOT_VALIDATED** and that local Jacobian spectral radius is not proof of global stability.
- Generate research report stays disabled until an experiment exists.

API E2E against the live server (Bearer `demo.researcher`) ran Lake-at-Rest (PASS), parabolic bowl (PASS), spectral (COMPUTED, `unstable_classified=false`), perturbation (COMPUTED), flux/source (COMPUTED), interface balance (cell FV residual ~1e-15, not a fake face residual), Jacobian (`global_stability_proof=false`), long-term 20-step PASS, AI freeze, physics-vs-AI **NOT_COMPARABLE**, research report `live: false` / `kind: research`. General role: 403.

Mid-run death is covered by the synthetic **FAILED AT STEP 40** report test (never labeled COMPLETED).

## 22. Limitations

- Synthetic parabolic bowl, not a city DEM observational product.  
- Outer “steps” are `SimulationService` intervals (`T_end=0.05`), not SWE inner subcycles.  
- Pause not implemented.  
- Flux residual is an inspection operator using public kernels, not a bit-identical dump of the scalar timestepper internals.  
- Local Jacobian ≠ global stability.  
- Nyquist content ≠ automatic instability.  
- Arrays bounded; PNG plot artifacts are not rendered server-side.  
- Email/push and spatial AI remain out of scope.

Reports: `POST /api/v1/research/reports` writes an immutable snapshot. Failed diagnostics stay FAILED.
