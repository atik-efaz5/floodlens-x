"""Digital Elevation Model ingestion and resampling (notebook cell 554)."""

from dataclasses import dataclass
from typing import Any, Dict, Tuple, Union

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from floodlens.core.config import SimulationConfig


@dataclass(frozen=True)
class ValidatedDEM:
    """Validated DEM payload for pipeline resampling."""

    data: np.ndarray
    report: Dict[str, Any]


class DEMManager:
    """Handles ingestion, validation, and resampling of Digital Elevation Models."""

    @staticmethod
    def _validate_report(data: np.ndarray) -> Dict[str, Any]:
        report = {
            "dtype": data.dtype,
            "shape": data.shape,
            "has_nan": np.isnan(data).any(),
            "has_inf": np.isinf(data).any(),
            "finite_range": (np.nanmin(data), np.max(data))
            if not np.isnan(data).all()
            else (0, 0),
            "data": np.asarray(data, dtype=np.float64),
        }

        if report["has_nan"] or report["has_inf"]:
            raise ValueError("DEM contains invalid non-finite values (NaN/Inf).")

        if data.ndim != 2:
            raise ValueError(f"DEM must be a 2D array, got {data.ndim}D.")

        return report

    @staticmethod
    def validate_raw_input(data: np.ndarray) -> Dict[str, Any]:
        """Performs a structural audit on raw terrain arrays."""
        return DEMManager._validate_report(data)

    def validate(self, data: np.ndarray) -> ValidatedDEM:
        """Instance helper returning a typed validated DEM container."""
        report = self._validate_report(data)
        return ValidatedDEM(data=report["data"], report=report)

    @staticmethod
    def _extract_dem_array(dem_source: Union[np.ndarray, Dict[str, Any], ValidatedDEM]) -> np.ndarray:
        if isinstance(dem_source, ValidatedDEM):
            return dem_source.data
        if isinstance(dem_source, dict):
            return np.asarray(dem_source["data"], dtype=np.float64)
        return np.asarray(dem_source, dtype=np.float64)

    @staticmethod
    def resample_terrain(
        raw_z_or_validated: Union[np.ndarray, Dict[str, Any], ValidatedDEM],
        current_lxly_or_config: Union[Tuple[float, float], SimulationConfig],
        target_config: SimulationConfig | None = None,
    ) -> np.ndarray:
        """Resamples raw DEM to match target grid resolution using bilinear interpolation."""
        if target_config is None and isinstance(current_lxly_or_config, SimulationConfig):
            target_config = current_lxly_or_config
            current_lxly = (target_config.Lx, target_config.Ly)
            raw_z = DEMManager._extract_dem_array(raw_z_or_validated)
        else:
            current_lxly = current_lxly_or_config  # type: ignore[assignment]
            if target_config is None:
                raise ValueError("target_config is required for the three-argument form.")
            raw_z = DEMManager._extract_dem_array(raw_z_or_validated)

        ny_raw, nx_raw = raw_z.shape
        x_raw = np.linspace(0, current_lxly[0], nx_raw)
        y_raw = np.linspace(0, current_lxly[1], ny_raw)

        interp = RegularGridInterpolator(
            (y_raw, x_raw), raw_z, method="linear", bounds_error=False, fill_value=None
        )

        dx = target_config.Lx / target_config.Nx
        dy = target_config.Ly / target_config.Ny
        x_target = np.linspace(0.5 * dx, target_config.Lx - 0.5 * dx, target_config.Nx)
        y_target = np.linspace(0.5 * dy, target_config.Ly - 0.5 * dy, target_config.Ny)
        yy, xx = np.meshgrid(y_target, x_target, indexing="ij")

        pts = np.stack([yy.ravel(), xx.ravel()], axis=-1)
        z_resampled = interp(pts).reshape(target_config.Ny, target_config.Nx)

        return z_resampled.astype(np.float64)
