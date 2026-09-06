"""Research diagnostics wrapping the public simulator and numerical kernels.

The numerical core is not modified. Arrays are summarized, never dumped wholesale.
UNAVAILABLE / NOT_RUN are explicit. PASS is never inferred from partial data.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

import numpy as np

from floodlens.application.input_manager import InputManager
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import PHYSICS_MODEL_VERSION, isoformat
from floodlens.application.service import SimulationService
from floodlens.core.config import SimulationConfig
from floodlens.numerical.flux import F, G, max_wave_speed_x, max_wave_speed_y
from floodlens.numerical.reconstruction import hydrostatic_reconstruction
from floodlens.numerical.riemann import rusanov_flux
from floodlens.numerical.sources import calculate_bed_slope_source_terms
from floodlens.numerical.timestep import calculate_dt_cfl

LAKE_AT_REST_MOMENTUM_TOL = 1e-10
MASS_RELATIVE_TOL = 1e-8
LONG_TERM_STEPS = (20, 50, 100, 500)
PERTURBATION_AMPLITUDES = (1e-15, 1e-12, 1e-9)
MAP_CAP = 8
SERIES_CAP = 32

JACOBIAN_NOTE = (
    "LOCAL JACOBIAN SPECTRAL RADIUS IS NOT BY ITSELF PROOF OF GLOBAL "
    "LONG-TERM STABILITY."
)
CFL_NOTE = (
    "CFL is a numerical stability diagnostic for the local timestep, "
    "not proof of global stability."
)


def diagnostic_inventory() -> dict:
    return {
        "solver_version": PHYSICS_MODEL_VERSION,
        "note": "Inventory of existing diagnostics. Missing implementations stay UNAVAILABLE.",
        "diagnostics": [
            {
                "id": "mass_conservation",
                "source": "DiagnosticsReport.total_mass via ShallowWaterSimulatorWithDiagnostics",
                "input": "simulation state h, dx, dy",
                "output": "mass initial/final/relative error",
                "units": "m^3 ; relative error dimensionless",
                "meaning": "Volume change over the run. Rainfall is not applied in these suites.",
                "limitations": "Relative error uses initial mass; zero initial mass is undefined.",
                "ui_ready": True,
            },
            {
                "id": "momentum_residual",
                "source": "max|hu|+max|hv| on the conserved state",
                "input": "hu, hv",
                "output": "L1/L2/L∞ of momentum magnitude plus legacy max|hu|+max|hv|",
                "units": "m^2/s",
                "meaning": "Lake-at-rest should remain near still water.",
                "limitations": f"Pass uses momentum_residual < {LAKE_AT_REST_MOMENTUM_TOL} (unchanged).",
                "ui_ready": True,
            },
            {
                "id": "equilibrium_residual",
                "source": "same momentum field; named L1/L2/L∞",
                "input": "hu, hv",
                "output": "mean |p|, RMS |p|, max |p|",
                "units": "m^2/s",
                "meaning": "Still-water residual after N steps.",
                "limitations": "Not claimed as machine precision unless the number is.",
                "ui_ready": True,
            },
            {
                "id": "cfl_timestep",
                "source": "calculate_dt_cfl (numerical.timestep)",
                "input": "U, dx, dy, g, h_dry, C",
                "output": "dt, min_cfl, max_cfl, steps",
                "units": "s ; CFL dimensionless",
                "meaning": CFL_NOTE,
                "limitations": "Config CFL is passed into calculate_dt_cfl; not a global-stability proof.",
                "ui_ready": True,
            },
            {
                "id": "boundary",
                "source": "SimulationConfig.boundary_condition; NUMERICAL_CONTRACT reflective walls",
                "input": "config",
                "output": "boundary type, quality UNAVAILABLE",
                "units": None,
                "meaning": "Validated active BC is reflective walls.",
                "limitations": "Boundary type is not a quality score.",
                "ui_ready": True,
            },
            {
                "id": "spectral",
                "source": "numpy.fft.rfft2 of hu after the existing solver run",
                "input": "hu field samples over steps",
                "output": "Nyquist-mode energy ratio, low/high band energy, growth of Nyquist ratio",
                "units": "energy ratio dimensionless",
                "meaning": "High-frequency content of momentum. Not automatically instability.",
                "limitations": "No project UNSTABLE criterion on Nyquist ratio; observed only.",
                "ui_ready": True,
            },
            {
                "id": "perturbation",
                "source": "checkerboard hu on lake-at-rest, then existing solver",
                "input": "amplitudes 1e-15, 1e-12, 1e-9",
                "output": "initial/final amplitude, growth factor",
                "units": "m^2/s ; growth dimensionless",
                "meaning": "Observed amplification of a checkerboard momentum seed.",
                "limitations": "Growth is not automatically classified as solver unstable.",
                "ui_ready": True,
            },
            {
                "id": "flux_source",
                "source": "rusanov_flux + hydrostatic_reconstruction + calculate_bed_slope_source_terms",
                "input": "current U, z, dx, dy, g",
                "output": "flux-divergence and topographic-source norms and a capped map",
                "units": "m/s^2 (momentum residual density)",
                "meaning": "Hydrostatic-balance inspection using existing kernels.",
                "limitations": "Finite-volume residual at the inspected state, not a rewritten timestepper.",
                "ui_ready": True,
            },
            {
                "id": "interface_balance",
                "source": "same kernels on one selected face",
                "input": "i, j, direction",
                "output": "left/right/reconstructed states, pressure flux, source, residual",
                "units": "conserved variables; fluxes in SI",
                "meaning": "Face-level well-balanced inspection.",
                "limitations": "One face. Not a global proof.",
                "ui_ready": True,
            },
            {
                "id": "jacobian",
                "source": "local 3×3 numerical Jacobian of the FV residual at one cell",
                "input": "cell (j,i), eps=1e-8",
                "output": "Jacobian estimate, eigenvalues, spectral radius",
                "units": "1/s for eigenvalues of residual/state",
                "meaning": JACOBIAN_NOTE,
                "limitations": "Local, frozen neighbors. Not global stability.",
                "ui_ready": True,
            },
            {
                "id": "long_term_stability",
                "source": "lake-at-rest runner for 20/50/100/500 outer steps",
                "input": "steps",
                "output": "mass, momentum, equilibrium, NaN/Inf, negative depth, max speed/depth",
                "units": "mixed",
                "meaning": "If the run dies mid-way the status is FAILED AT STEP N, not COMPLETED.",
                "limitations": "Outer steps are SimulationService intervals, not SWE inner subcycles.",
                "ui_ready": True,
            },
        ],
    }


def _config_hash(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _series(values, cap: int = SERIES_CAP) -> list:
    if not values:
        return []
    if len(values) <= cap:
        return [float(v) for v in values]
    idx = np.linspace(0, len(values) - 1, cap).astype(int)
    return [float(values[i]) for i in idx]


def _cap_map(arr: np.ndarray) -> dict:
    array = np.asarray(arr, dtype=np.float64)
    finite = np.isfinite(array)
    if array.size == 0 or not finite.any():
        return {
            "shape": list(array.shape),
            "max": None,
            "min": None,
            "mean": None,
            "subsample": None,
            "status": "UNAVAILABLE",
        }
    ny, nx = array.shape[:2]
    step_y = max(1, ny // MAP_CAP)
    step_x = max(1, nx // MAP_CAP)
    sample = array[::step_y, ::step_x]
    return {
        "shape": [int(ny), int(nx)],
        "max": float(np.nanmax(array)),
        "min": float(np.nanmin(array)),
        "mean": float(np.nanmean(array)),
        "subsample": np.round(sample, 12).tolist(),
        "status": "COMPUTED",
    }


def _momentum_norms(hu: np.ndarray, hv: np.ndarray) -> dict:
    mag = np.sqrt(hu**2 + hv**2)
    return {
        "L1": float(np.mean(np.abs(mag))),
        "L2": float(np.sqrt(np.mean(mag**2))),
        "Linf": float(np.max(mag)),
        "legacy_max_abs_hu_plus_hv": float(np.max(np.abs(hu)) + np.max(np.abs(hv))),
        "norm_definition": "L1=mean(|p|), L2=RMS(|p|), L∞=max(|p|), |p|=sqrt(hu²+hv²)",
    }


def _state_pack(service: SimulationService) -> dict:
    state = service.sim.get_state()
    U = state.U
    h, hu, hv = U[:, :, 0], U[:, :, 1], U[:, :, 2]
    u, v, speed = service.sim.velocity
    mass = float(service.sim.compute_total_volume())
    norms = _momentum_norms(hu, hv)
    finite = bool(np.isfinite(U).all())
    negative_depth = bool(np.min(h) < -1e-12)
    dt, min_cfl, max_cfl = calculate_dt_cfl(
        U,
        service.sim.grid.dx,
        service.sim.grid.dy,
        service.config.g,
        service.config.h_dry_threshold,
        C=service.config.CFL,
    )
    return {
        "time_s": float(state.time),
        "iteration": int(state.iteration),
        "mass_m3": mass,
        "max_depth_m": float(np.max(h)),
        "min_depth_m": float(np.min(h)),
        "max_velocity_mps": float(np.max(speed)),
        "mean_velocity_mps": float(np.mean(speed)),
        "momentum_norms": norms,
        "momentum_residual": norms["legacy_max_abs_hu_plus_hv"],
        "equilibrium_residual": {
            "L1": norms["L1"],
            "L2": norms["L2"],
            "Linf": norms["Linf"],
            "norm_definition": norms["norm_definition"],
        },
        "dt_s": float(dt),
        "cfl_min": float(min_cfl) if np.isfinite(min_cfl) else None,
        "cfl_max": float(max_cfl) if np.isfinite(max_cfl) else None,
        "finite": finite,
        "negative_depth": negative_depth,
        "nan_inf": not finite,
        "depth_map": _cap_map(h),
        "speed_map": _cap_map(speed),
        "wse_map": _cap_map(h + state.z),
    }


def _lake_setup(nx: int, ny: int, name: str) -> tuple[SimulationConfig, np.ndarray, np.ndarray]:
    config = SimulationConfig(Nx=nx, Ny=ny, Lx=10.0, Ly=10.0, T_end=0.05, name=name)
    z = InputManager.generate_parabolic_bowl(config)
    surface = 2.0
    u_init = np.zeros((ny, nx, 3), dtype=np.float64)
    u_init[:, :, 0] = np.maximum(0.0, surface - z)
    return config, z, u_init


def _provenance(config: SimulationConfig, experiment_id: str, extra: Optional[dict] = None) -> dict:
    cfg = {
        "Nx": config.Nx,
        "Ny": config.Ny,
        "Lx": config.Lx,
        "Ly": config.Ly,
        "g": config.g,
        "h_dry_threshold": config.h_dry_threshold,
        "CFL": config.CFL,
        "dt_initial": config.dt_initial,
        "T_end": config.T_end,
        "boundary_condition": config.boundary_condition,
        "manning_n": config.manning_n,
        "name": config.name,
    }
    row = {
        "source": "ShallowWaterSimulatorWithDiagnostics + public numerical kernels",
        "solver_version": PHYSICS_MODEL_VERSION,
        "config": cfg,
        "config_hash": _config_hash(cfg),
        "experiment_id": experiment_id,
        "timestamp": isoformat(),
        "dataset_version": "synthetic-parabolic-bowl",
        "artifact_version": "research-diagnostics-v1",
        "data_status": "SIMULATED",
        "freshness": "SNAPSHOT",
        "simulated": True,
        "note": "These are solver diagnostics on a synthetic basin, not observational products.",
    }
    if extra:
        row.update(extra)
    return row


def _store_experiment(payload: dict) -> dict:
    store = get_platform_store()
    return store.put_experiment(payload)


def _fft_nyquist(hu: np.ndarray) -> dict:
    field = np.asarray(hu, dtype=np.float64)
    spec = np.fft.rfft2(field)
    energy = np.abs(spec) ** 2
    total = float(np.sum(energy))
    ny, nx_r = spec.shape
    nyquist = spec[ny // 2, nx_r - 1]
    nyquist_energy = float(np.abs(nyquist) ** 2)
    low = float(np.sum(energy[: max(1, ny // 4), : max(1, nx_r // 4)]))
    high = float(total - low)
    ratio = (nyquist_energy / total) if total > 0 else None
    # Real-valued FFT conjugate symmetry: anti-symmetry of imag(hu) is not used.
    # Checkerboard anti-symmetry: odd-odd index energy vs total.
    odd_odd = float(np.sum(np.abs(field[1::2, 1::2])))
    even_even = float(np.sum(np.abs(field[0::2, 0::2])))
    denom = odd_odd + even_even
    anti = (odd_odd / denom) if denom > 0 else None
    amp = np.abs(spec).ravel()
    k = min(16, amp.size)
    return {
        "nyquist_mode_energy": nyquist_energy,
        "total_spectral_energy": total,
        "nyquist_energy_ratio": ratio,
        "low_frequency_energy": low,
        "high_frequency_energy": high,
        "anti_symmetry_ratio": anti,
        "spectral_amplitude_head": [float(v) for v in amp[:k]],
        "unstable_classified": False,
        "unstable_reason": (
            "No project criterion maps Nyquist-mode energy to UNSTABLE. "
            "High-frequency content is reported, not labeled instability."
        ),
    }


def _flux_source_fields(U: np.ndarray, z: np.ndarray, dx: float, dy: float, g: float, h_dry: float) -> dict:
    ny, nx, _ = U.shape
    source = calculate_bed_slope_source_terms(U, z, dx, dy, g)
    flux_div = np.zeros_like(U)
    for j in range(ny):
        for i in range(nx):
            iL = max(i - 1, 0)
            iR = min(i + 1, nx - 1)
            jB = max(j - 1, 0)
            jT = min(j + 1, ny - 1)
            uL, uC, uR = U[j, iL], U[j, i], U[j, iR]
            zL, zC, zR = z[j, iL], z[j, i], z[j, iR]
            rec_LC, rec_CL = hydrostatic_reconstruction(uL.copy(), uC.copy(), zL, zC, h_dry)
            rec_CR, rec_RC = hydrostatic_reconstruction(uC.copy(), uR.copy(), zC, zR, h_dry)
            f_left = rusanov_flux(rec_LC, rec_CL, F, max_wave_speed_x, g, h_dry)
            f_right = rusanov_flux(rec_CR, rec_RC, F, max_wave_speed_x, g, h_dry)
            uB, uT = U[jB, i], U[jT, i]
            zB, zT = z[jB, i], z[jT, i]
            rec_BC, rec_CB = hydrostatic_reconstruction(uB.copy(), uC.copy(), zB, zC, h_dry)
            rec_CT, rec_TC = hydrostatic_reconstruction(uC.copy(), uT.copy(), zC, zT, h_dry)
            g_bottom = rusanov_flux(rec_BC, rec_CB, G, max_wave_speed_y, g, h_dry)
            g_top = rusanov_flux(rec_CT, rec_TC, G, max_wave_speed_y, g, h_dry)
            flux_div[j, i] = (f_right - f_left) / dx + (g_top - g_bottom) / dy
    residual = source - flux_div
    return {
        "flux_divergence": flux_div,
        "topographic_source": source,
        "combined_rhs": residual,
    }


def _interface_at(U, z, i: int, j: int, direction: str, dx, dy, g, h_dry) -> dict:
    ny, nx, _ = U.shape
    if not (0 <= i < nx and 0 <= j < ny):
        raise ValueError("interface indices out of range")
    if direction == "x":
        iR = min(i + 1, nx - 1)
        uL, uR = U[j, i].copy(), U[j, iR].copy()
        zL, zR = float(z[j, i]), float(z[j, iR])
        rec_L, rec_R = hydrostatic_reconstruction(uL.copy(), uR.copy(), zL, zR, h_dry)
        flux = rusanov_flux(rec_L, rec_R, F, max_wave_speed_x, g, h_dry)
        pressure = 0.5 * g * rec_L[0] ** 2
    else:
        jT = min(j + 1, ny - 1)
        uL, uR = U[j, i].copy(), U[jT, i].copy()
        zL, zR = float(z[j, i]), float(z[jT, i])
        rec_L, rec_R = hydrostatic_reconstruction(uL.copy(), uR.copy(), zL, zR, h_dry)
        flux = rusanov_flux(rec_L, rec_R, G, max_wave_speed_y, g, h_dry)
        pressure = 0.5 * g * rec_L[0] ** 2
    source = calculate_bed_slope_source_terms(U, z, dx, dy, g)[j, i]
    fields = _flux_source_fields(U, z, dx, dy, g, h_dry)
    cell_residual = fields["combined_rhs"][j, i]
    return {
        "i": int(i),
        "j": int(j),
        "direction": direction,
        "left_state": [float(v) for v in uL],
        "right_state": [float(v) for v in uR],
        "reconstructed_left": [float(v) for v in rec_L],
        "reconstructed_right": [float(v) for v in rec_R],
        "pressure_flux": float(pressure),
        "rusanov_flux": [float(v) for v in flux],
        "topographic_source": [float(v) for v in source],
        "combined_residual": [float(v) for v in cell_residual],
        "note": "Face states/fluxes from existing kernels. Combined residual is the cell FV residual (source − flux divergence), not a simplified fake balance.",
    }


def _local_jacobian(U, z, i: int, j: int, dx, dy, g, h_dry, eps: float = 1e-8) -> dict:
    def rhs(state):
        fields = _flux_source_fields(state, z, dx, dy, g, h_dry)
        return fields["combined_rhs"][j, i]

    base = U.copy()
    r0 = rhs(base)
    jac = np.zeros((3, 3), dtype=np.float64)
    for k in range(3):
        pert = base.copy()
        pert[j, i, k] += eps
        r1 = rhs(pert)
        jac[:, k] = (r1 - r0) / eps
    eig = np.linalg.eigvals(jac)
    radius = float(np.max(np.abs(eig)))
    return {
        "cell": {"i": int(i), "j": int(j)},
        "eps": eps,
        "jacobian": np.round(jac, 12).tolist(),
        "eigenvalues_real": [float(v.real) for v in eig],
        "eigenvalues_imag": [float(v.imag) for v in eig],
        "spectral_radius": radius,
        "methodological_note": JACOBIAN_NOTE,
        "global_stability_proof": False,
    }


def _finalize(suite: str, config: SimulationConfig, body: dict, passed: Optional[bool], status: str) -> dict:
    experiment_id = f"exp_{suite}_{isoformat().replace(':', '').replace('-', '')[:18]}"
    provenance = _provenance(config, experiment_id)
    payload = {
        "id": experiment_id,
        "experiment_id": experiment_id,
        "suite": suite,
        "passed": passed,
        "status": status,
        "model_version": PHYSICS_MODEL_VERSION,
        "solver_version": PHYSICS_MODEL_VERSION,
        "pause_supported": False,
        "live": False,
        "data_status": "SIMULATED",
        "provenance": provenance,
        "config_hash": provenance["config_hash"],
        "timestamp": provenance["timestamp"],
        **body,
    }
    stored = _store_experiment(payload)
    payload["id"] = stored["id"]
    payload["experiment_id"] = stored["id"]
    payload["provenance"]["experiment_id"] = stored["id"]
    return payload


def _run_tracked_lake(nx: int, ny: int, steps: int, name: str, u_init: Optional[np.ndarray] = None):
    config, z, default_u = _lake_setup(nx, ny, name)
    if u_init is None:
        u_init = default_u
    service = SimulationService(config)
    service.sim.set_initial_conditions(z, u_init.copy())
    initial = _state_pack(service)
    nyquist_series = []
    failed_at_step = None
    fail_reason = None
    for step in range(steps):
        pipeline = service.run_scenario(steps=1, rainfall_rate=0.0, track_progress=False)
        state = service.sim.get_state()
        spec = _fft_nyquist(state.U[:, :, 1])
        nyquist_series.append(spec["nyquist_energy_ratio"])
        if not pipeline.success or not np.isfinite(state.U).all():
            failed_at_step = step + 1
            fail_reason = f"FAILED AT STEP {failed_at_step}"
            break
    final = _state_pack(service)
    diag = service.sim.diagnostics
    mass0 = float(diag.total_mass[0]) if diag.total_mass else initial["mass_m3"]
    mass1 = float(diag.total_mass[-1]) if diag.total_mass else final["mass_m3"]
    mass_err = abs(mass1 - mass0) / mass0 if mass0 else None
    return {
        "config": config,
        "service": service,
        "z": z,
        "initial": initial,
        "final": final,
        "failed_at_step": failed_at_step,
        "fail_reason": fail_reason,
        "mass0": mass0,
        "mass1": mass1,
        "mass_err": mass_err,
        "nyquist_series": nyquist_series,
        "diagnostics": diag,
        "executed_steps": int(service.sim.get_state().iteration),
        "requested_steps": steps,
    }


def run_lake_at_rest(nx: int = 16, ny: int = 16, steps: int = 5) -> dict:
    tracked = _run_tracked_lake(nx, ny, steps, "lake_at_rest")
    mom = tracked["final"]["momentum_residual"]
    finite = tracked["final"]["finite"]
    failed = tracked["failed_at_step"] is not None
    passed = bool(
        not failed
        and finite
        and mom < LAKE_AT_REST_MOMENTUM_TOL
        and not tracked["final"]["negative_depth"]
    )
    if failed:
        status = tracked["fail_reason"]
    elif passed:
        status = "PASS"
    else:
        status = "VALIDATION FAILED"
    cfl_vals = list(tracked["diagnostics"].max_cfl or [])
    body = {
        "momentum_residual": mom,
        "mass_relative_error": tracked["mass_err"],
        "mass_initial_m3": tracked["mass0"],
        "mass_final_m3": tracked["mass1"],
        "steps": tracked["executed_steps"],
        "requested_steps": steps,
        "tolerance": {
            "momentum_residual": LAKE_AT_REST_MOMENTUM_TOL,
            "mass_relative_error": MASS_RELATIVE_TOL,
        },
        "criteria": {
            "velocity_near_zero": mom < LAKE_AT_REST_MOMENTUM_TOL,
            "momentum_near_zero": mom < LAKE_AT_REST_MOMENTUM_TOL,
            "finite_state": finite,
            "no_negative_depth": not tracked["final"]["negative_depth"],
        },
        "initial_state": {k: tracked["initial"][k] for k in (
            "mass_m3", "max_depth_m", "max_velocity_mps", "momentum_residual",
            "equilibrium_residual", "time_s",
        )},
        "final_state": {k: tracked["final"][k] for k in (
            "mass_m3", "max_depth_m", "min_depth_m", "max_velocity_mps",
            "momentum_residual", "equilibrium_residual", "time_s", "finite",
            "negative_depth", "nan_inf", "dt_s", "cfl_min", "cfl_max",
        )},
        "conservation": {
            "mass_initial": tracked["mass0"],
            "mass_final": tracked["mass1"],
            "mass_error": tracked["mass_err"],
            "mass_error_abs_m3": abs(tracked["mass1"] - tracked["mass0"]),
            "units": {"mass": "m^3", "mass_error": "relative"},
            "tolerance": MASS_RELATIVE_TOL,
            "status": (
                "PASS"
                if tracked["mass_err"] is not None and tracked["mass_err"] < MASS_RELATIVE_TOL
                else "FAIL"
                if tracked["mass_err"] is not None
                else "UNAVAILABLE"
            ),
        },
        "equilibrium_residual": tracked["final"]["equilibrium_residual"],
        "cfl": {
            "dt_s": tracked["final"]["dt_s"],
            "cfl_min": tracked["final"]["cfl_min"],
            "cfl_max": tracked["final"]["cfl_max"],
            "max_cfl_series": _series(cfl_vals),
            "steps": tracked["executed_steps"],
            "note": CFL_NOTE,
        },
        "boundary": {
            "type": tracked["config"].boundary_condition,
            "domain_edges": ["left", "right", "bottom", "top"],
            "reflection_behavior": "Validated reflective walls: hu negated on x-ghosts, hv negated on y-ghosts.",
            "diagnostic_status": "IMPLEMENTED",
            "quality_inferred": "UNAVAILABLE",
            "note": "Boundary type is not a numerical-quality score.",
        },
        "spectral": {
            **_fft_nyquist(tracked["service"].sim.get_state().U[:, :, 1]),
            "nyquist_energy_ratio_series": _series(tracked["nyquist_series"]),
        },
        "maps": {
            "final_depth": tracked["final"]["depth_map"],
            "final_speed": tracked["final"]["speed_map"],
            "final_wse": tracked["final"]["wse_map"],
        },
        "failed_at_step": tracked["failed_at_step"],
        "note": "Residuals are not clipped or damped for display.",
    }
    return _finalize("lake_at_rest", tracked["config"], body, passed, status)


def run_parabolic_bowl(nx: int = 16, ny: int = 16, steps: int = 3) -> dict:
    config = SimulationConfig(Nx=nx, Ny=ny, Lx=10.0, Ly=10.0, T_end=0.05, name="parabolic_bowl")
    z = InputManager.generate_parabolic_bowl(config)
    service = SimulationService(config)
    u_init = np.zeros((ny, nx, 3), dtype=np.float64)
    service.sim.set_initial_conditions(z, u_init)
    initial = _state_pack(service)
    pipeline = None
    failed_at_step = None
    for step in range(steps):
        pipeline = service.run_scenario(steps=1, rainfall_rate=0.0, track_progress=False)
        if not pipeline.success or not np.isfinite(service.sim.get_state().U).all():
            failed_at_step = step + 1
            break
    final = _state_pack(service)
    finite = final["finite"]
    passed = bool(failed_at_step is None and finite and pipeline is not None and pipeline.success)
    status = f"FAILED AT STEP {failed_at_step}" if failed_at_step else ("PASS" if passed else "VALIDATION FAILED")
    diag = service.sim.diagnostics
    mass0 = float(diag.total_mass[0]) if diag.total_mass else initial["mass_m3"]
    mass1 = float(diag.total_mass[-1]) if diag.total_mass else final["mass_m3"]
    body = {
        "max_speed": final["max_velocity_mps"],
        "steps": int(service.sim.get_state().iteration),
        "pause_supported": False,
        "initial_state": {
            "mass_m3": initial["mass_m3"],
            "max_depth_m": initial["max_depth_m"],
            "max_velocity_mps": initial["max_velocity_mps"],
        },
        "final_state": {
            "mass_m3": final["mass_m3"],
            "max_depth_m": final["max_depth_m"],
            "min_depth_m": final["min_depth_m"],
            "max_velocity_mps": final["max_velocity_mps"],
            "free_surface_max_m": final["wse_map"]["max"],
            "momentum_residual": final["momentum_residual"],
            "equilibrium_residual": final["equilibrium_residual"],
            "dt_s": final["dt_s"],
            "cfl_max": final["cfl_max"],
        },
        "conservation": {
            "mass_initial": mass0,
            "mass_final": mass1,
            "mass_error": abs(mass1 - mass0) / mass0 if mass0 else None,
            "units": {"mass": "m^3"},
        },
        "cfl": {
            "dt_s": final["dt_s"],
            "cfl_max": final["cfl_max"],
            "note": CFL_NOTE,
        },
        "maps": {"final_depth": final["depth_map"], "final_wse": final["wse_map"], "final_speed": final["speed_map"]},
        "failed_at_step": failed_at_step,
    }
    return _finalize("parabolic_bowl", config, body, passed, status)


def long_term_stability(steps: int = 50) -> dict:
    requested = int(steps)
    if requested not in LONG_TERM_STEPS and requested > 500:
        requested = 500
    executed_plan = requested if requested in LONG_TERM_STEPS or requested <= 500 else 50
    tracked = _run_tracked_lake(12, 12, executed_plan, "long_term_stability")
    failed = tracked["failed_at_step"] is not None
    finite = tracked["final"]["finite"]
    mom = tracked["final"]["momentum_residual"]
    passed = bool(
        not failed
        and finite
        and not tracked["final"]["negative_depth"]
        and mom < LAKE_AT_REST_MOMENTUM_TOL
    )
    if failed:
        status = tracked["fail_reason"]
    elif passed:
        status = "PASS"
    else:
        status = "VALIDATION FAILED"
    spec = _fft_nyquist(tracked["service"].sim.get_state().U[:, :, 1])
    growth = None
    series = [v for v in tracked["nyquist_series"] if v is not None]
    if len(series) >= 2 and series[0] not in (0, None):
        growth = series[-1] / series[0] if series[0] else None
    body = {
        "requested_steps": steps,
        "executed_steps": tracked["executed_steps"],
        "failed_at_step": tracked["failed_at_step"],
        "mass_conservation": {
            "initial": tracked["mass0"],
            "final": tracked["mass1"],
            "relative_error": tracked["mass_err"],
        },
        "momentum_drift": mom,
        "equilibrium_residual": tracked["final"]["equilibrium_residual"],
        "negative_depth": tracked["final"]["negative_depth"],
        "nan_inf": tracked["final"]["nan_inf"],
        "spectral_growth": growth,
        "nyquist_energy_ratio_series": _series(tracked["nyquist_series"]),
        "max_velocity": tracked["final"]["max_velocity_mps"],
        "max_depth": tracked["final"]["max_depth_m"],
        "momentum_residual": mom,
        "mass_relative_error": tracked["mass_err"],
        "steps": tracked["executed_steps"],
        "cfl": {
            "dt_s": tracked["final"]["dt_s"],
            "cfl_max": tracked["final"]["cfl_max"],
            "note": CFL_NOTE,
        },
        "note": "A failed mid-run is FAILED AT STEP N, not COMPLETED.",
        "spectral": spec,
    }
    return _finalize("long_term_stability", tracked["config"], body, passed, status)


def run_conservation(nx: int = 16, ny: int = 16, steps: int = 5) -> dict:
    result = run_lake_at_rest(nx=nx, ny=ny, steps=steps)
    result["suite"] = "conservation"
    return result


def run_spectral(nx: int = 16, ny: int = 16, steps: int = 8) -> dict:
    tracked = _run_tracked_lake(nx, ny, steps, "spectral")
    spec = _fft_nyquist(tracked["service"].sim.get_state().U[:, :, 1])
    status = tracked["fail_reason"] if tracked["failed_at_step"] else "COMPUTED"
    body = {
        **spec,
        "nyquist_energy_ratio_series": _series(tracked["nyquist_series"]),
        "steps": tracked["executed_steps"],
        "failed_at_step": tracked["failed_at_step"],
        "maps": {"hu_final": _cap_map(tracked["service"].sim.get_state().U[:, :, 1])},
    }
    return _finalize("spectral", tracked["config"], body, None if not tracked["failed_at_step"] else False, status)


def run_perturbation(amplitude: float = 1e-12, nx: int = 16, ny: int = 16, steps: int = 8) -> dict:
    amp = float(amplitude)
    if amp not in PERTURBATION_AMPLITUDES:
        raise ValueError(f"amplitude must be one of {PERTURBATION_AMPLITUDES}")
    config, z, u_init = _lake_setup(nx, ny, "perturbation")
    checker = np.fromfunction(lambda j, i: ((i + j) % 2) * 2 - 1, (ny, nx), dtype=np.float64)
    u_init = u_init.copy()
    u_init[:, :, 1] += amp * checker
    initial_amp = float(np.max(np.abs(u_init[:, :, 1])))
    tracked = _run_tracked_lake(nx, ny, steps, "perturbation", u_init=u_init)
    final_hu = tracked["service"].sim.get_state().U[:, :, 1]
    final_amp = float(np.max(np.abs(final_hu)))
    growth = (final_amp / initial_amp) if initial_amp > 0 else None
    status = tracked["fail_reason"] if tracked["failed_at_step"] else "COMPUTED"
    body = {
        "perturbation": "checkerboard momentum hu",
        "amplitude_requested": amp,
        "initial_amplitude": initial_amp,
        "final_amplitude": final_amp,
        "growth_factor": growth,
        "growth_curve": _series(tracked["nyquist_series"]),
        "observed_growth": growth,
        "interpretation": (
            "OBSERVED GROWTH of a checkerboard hu seed. "
            "Amplification is reported and not hidden. "
            "This is not automatically classified as solver unstable; "
            "no project UNSTABLE criterion is applied here."
        ),
        "unstable_classified": False,
        "steps": tracked["executed_steps"],
        "failed_at_step": tracked["failed_at_step"],
    }
    return _finalize("perturbation", tracked["config"], body, None, status)


def run_flux_source(nx: int = 16, ny: int = 16) -> dict:
    config, z, u_init = _lake_setup(nx, ny, "flux_source")
    service = SimulationService(config)
    service.sim.set_initial_conditions(z, u_init)
    service.run_scenario(steps=1, rainfall_rate=0.0, track_progress=False)
    state = service.sim.get_state()
    fields = _flux_source_fields(
        state.U, state.z, service.sim.grid.dx, service.sim.grid.dy, config.g, config.h_dry_threshold
    )
    flux = fields["flux_divergence"][:, :, 1]
    src = fields["topographic_source"][:, :, 1]
    rhs = fields["combined_rhs"][:, :, 1]
    body = {
        "component": "hu",
        "flux_divergence_norms": _momentum_norms(flux, np.zeros_like(flux)),
        "topographic_source_norms": _momentum_norms(src, np.zeros_like(src)),
        "combined_rhs_norms": _momentum_norms(rhs, np.zeros_like(rhs)),
        "maps": {
            "flux_divergence_hu": _cap_map(flux),
            "topographic_source_hu": _cap_map(src),
            "combined_rhs_hu": _cap_map(rhs),
        },
        "note": "Hydrostatic-balance inspection using existing flux/source kernels. Not a solver rewrite.",
    }
    return _finalize("flux_source", config, body, None, "COMPUTED")


def run_interface_balance(i: Optional[int] = None, j: Optional[int] = None, direction: str = "x", nx: int = 16, ny: int = 16) -> dict:
    config, z, u_init = _lake_setup(nx, ny, "interface_balance")
    service = SimulationService(config)
    service.sim.set_initial_conditions(z, u_init)
    service.run_scenario(steps=1, rainfall_rate=0.0, track_progress=False)
    state = service.sim.get_state()
    ii = nx // 2 if i is None else int(i)
    jj = ny // 2 if j is None else int(j)
    face = _interface_at(
        state.U,
        state.z,
        ii,
        jj,
        direction if direction in {"x", "y"} else "x",
        service.sim.grid.dx,
        service.sim.grid.dy,
        config.g,
        config.h_dry_threshold,
    )
    body = {"interface": face}
    return _finalize("interface_balance", config, body, None, "COMPUTED")


def run_jacobian(i: Optional[int] = None, j: Optional[int] = None, nx: int = 12, ny: int = 12) -> dict:
    config, z, u_init = _lake_setup(nx, ny, "jacobian")
    service = SimulationService(config)
    service.sim.set_initial_conditions(z, u_init)
    state = service.sim.get_state()
    ii = nx // 2 if i is None else int(i)
    jj = ny // 2 if j is None else int(j)
    local = _local_jacobian(
        state.U, state.z, ii, jj, service.sim.grid.dx, service.sim.grid.dy, config.g, config.h_dry_threshold
    )
    body = {
        **local,
        "note": JACOBIAN_NOTE,
    }
    return _finalize("jacobian", config, body, None, "COMPUTED")
