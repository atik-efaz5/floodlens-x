"""Spatial input loading and validation (notebook cell 538)."""

import numpy as np

from floodlens.core.config import SimulationConfig


class InputManager:
    """Handles loading and validation of spatial input data."""

    @staticmethod
    def validate_spatial_data(z: np.ndarray, Nx: int, Ny: int) -> bool:
        if z.shape != (Ny, Nx):
            raise ValueError(
                f"Input shape {z.shape} does not match configuration ({Ny}, {Nx})"
            )
        if not np.all(np.isfinite(z)):
            raise ValueError("Input data contains non-finite values (NaN/Inf)")
        return True

    @staticmethod
    def generate_parabolic_bowl(config: SimulationConfig) -> np.ndarray:
        dx = config.Lx / config.Nx
        dy = config.Ly / config.Ny
        x = np.linspace(0.5 * dx, config.Lx - 0.5 * dx, config.Nx)
        y = np.linspace(0.5 * dy, config.Ly - 0.5 * dy, config.Ny)
        X, Y = np.meshgrid(x, y)
        # Canonical Parabolic Bowl
        z = 0.05 * ((X - config.Lx / 2) ** 2 + (Y - config.Ly / 2) ** 2)
        return z.astype(np.float64)
