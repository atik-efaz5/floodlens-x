"""Pre- and post-solver validation. Invalid science fails the job; nothing is silently repaired."""

from __future__ import annotations

from typing import Optional

import numpy as np

from floodlens.core.config import SimulationConfig

MASS_RELATIVE_WARN = 0.05


class SolverValidationError(ValueError):
    """Raised when scientific inputs or outputs are invalid."""


def validate_inputs(
    config: SimulationConfig,
    dem: np.ndarray,
    rainfall_rate: float,
    u_init: Optional[np.ndarray] = None,
) -> None:
    expected = (config.Ny, config.Nx)
    if dem.shape != expected:
        raise SolverValidationError(f"DEM shape {dem.shape} != {expected}")
    if not np.isfinite(dem).all():
        raise SolverValidationError("DEM contains NaN or Inf")
    if rainfall_rate < 0:
        raise SolverValidationError("rainfall_rate must be >= 0 m/s")
    if u_init is not None:
        if u_init.shape != expected + (3,):
            raise SolverValidationError(f"U shape {u_init.shape} != {expected + (3,)}")
        if not np.isfinite(u_init).all():
            raise SolverValidationError("Initial state contains NaN or Inf")
        if np.min(u_init[:, :, 0]) < 0:
            raise SolverValidationError("Initial depth is negative")
    if config.Lx <= 0 or config.Ly <= 0:
        raise SolverValidationError("Domain lengths must be positive")
    if config.dt_initial <= 0:
        raise SolverValidationError("dt_initial must be positive")


def validate_outputs(
    depth: np.ndarray,
    rainfall_rate: float,
    duration_s: float,
    area_m2: float,
    initial_volume: Optional[float] = None,
) -> dict:
    warnings = []
    if not np.isfinite(depth).all():
        return {"validation_status": "FAIL", "reason": "Depth contains NaN or Inf", "warnings": warnings}
    if np.min(depth) < -1e-12:
        return {"validation_status": "FAIL", "reason": "Negative depth in output", "warnings": warnings}
    depth = np.maximum(depth, 0.0)
    if rainfall_rate > 0 and duration_s > 0:
        added = rainfall_rate * duration_s * area_m2
        volume = float(np.sum(depth)) * (area_m2 / depth.size)
        if initial_volume is None:
            initial_volume = 0.0
        expected = initial_volume + added
        if expected > 0:
            rel = abs(volume - expected) / expected
            if rel > MASS_RELATIVE_WARN:
                warnings.append(
                    f"Mass relative error {rel:.3f} exceeds {MASS_RELATIVE_WARN} "
                    "(rain is applied inside the SWE loop; dry-bed and CFL splitting can differ)."
                )
    status = "WARN" if warnings else "PASS"
    return {
        "validation_status": status,
        "reason": None if status == "PASS" else "; ".join(warnings),
        "warnings": warnings,
        "max_depth_m": float(np.max(depth)),
        "min_depth_m": float(np.min(depth)),
    }
