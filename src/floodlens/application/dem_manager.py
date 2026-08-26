"""Digital Elevation Model ingestion and resampling (notebook cell 554)."""

from typing import Any, Dict, Tuple

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from floodlens.core.config import SimulationConfig


class DEMManager:
    """Handles ingestion, validation, and resampling of Digital Elevation Models."""

    @staticmethod
    def validate_raw_input(data: np.ndarray) -> Dict[str, Any]:
        """Performs a structural audit on raw terrain arrays."""
        report = {
            "dtype": data.dtype,
            "shape": data.shape,
            "has_nan": np.isnan(data).any(),
            "has_inf": np.isinf(data).any(),
            "finite_range": (np.nanmin(data), np.max(data))
            if not np.isnan(data).all()
            else (0, 0),
        }

        if report["has_nan"] or report["has_inf"]:
            raise ValueError("DEM contains invalid non-finite values (NaN/Inf).")

        if data.ndim != 2:
            raise ValueError(f"DEM must be a 2D array, got {data.ndim}D.")

        return report

    @staticmethod
    def resample_terrain(
        raw_z: np.ndarray,
        current_lxly: Tuple[float, float],
        target_config: SimulationConfig,
    ) -> np.ndarray:
        """Resamples raw DEM to match target grid resolution using bilinear interpolation."""
        ny_raw, nx_raw = raw_z.shape
        x_raw = np.linspace(0, current_lxly[0], nx_raw)
        y_raw = np.linspace(0, current_lxly[1], ny_raw)

        interp = RegularGridInterpolator(
            (y_raw, x_raw), raw_z, method="linear", bounds_error=False, fill_value=None
        )

        # Target mesh
        dx = target_config.Lx / target_config.Nx
        dy = target_config.Ly / target_config.Ny
        x_target = np.linspace(0.5 * dx, target_config.Lx - 0.5 * dx, target_config.Nx)
        y_target = np.linspace(0.5 * dy, target_config.Ly - 0.5 * dy, target_config.Ny)
        YY, XX = np.meshgrid(y_target, x_target, indexing="ij")

        pts = np.stack([YY.ravel(), XX.ravel()], axis=-1)
        z_resampled = interp(pts).reshape(target_config.Ny, target_config.Nx)

        return z_resampled.astype(np.float64)
