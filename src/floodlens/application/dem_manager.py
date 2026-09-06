"""Digital Elevation Model ingestion and resampling (notebook cell 554)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from floodlens.core.config import SimulationConfig

try:
    import rasterio
    from rasterio.transform import Affine
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


@dataclass(frozen=True)
class ValidatedDEM:
    """Validated DEM payload for pipeline resampling."""

    data: np.ndarray
    report: Dict[str, Any]


@dataclass(frozen=True)
class GeoTIFFMetadata:
    """Spatial metadata for a georeferenced elevation grid."""

    bounds_west: float  # min X / left edge (m or degrees)
    bounds_south: float  # min Y / bottom edge (m or degrees)
    bounds_east: float  # max X / right edge (m or degrees)
    bounds_north: float  # max Y / top edge (m or degrees)
    crs: str = "EPSG:4326"  # Coordinate Reference System
    nodata_value: Optional[float] = None


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

    @staticmethod
    def load_geotiff(filepath: Union[str, Path]) -> Tuple[np.ndarray, GeoTIFFMetadata]:
        """
        Load DEM elevation grid from a GeoTIFF file.

        Returns:
            Tuple of (elevation_array, metadata)
        """
        if not HAS_RASTERIO:
            raise ImportError(
                "rasterio is required for GeoTIFF support. "
                "Install with: pip install rasterio"
            )

        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"GeoTIFF file not found: {filepath}")

        with rasterio.open(filepath) as src:
            z = src.read(1)  # Read first band as elevation
            bounds = src.bounds
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            nodata = src.nodata

        metadata = GeoTIFFMetadata(
            bounds_west=bounds.left,
            bounds_south=bounds.bottom,
            bounds_east=bounds.right,
            bounds_north=bounds.top,
            crs=crs,
            nodata_value=nodata,
        )

        return z.astype(np.float64), metadata

    @staticmethod
    def windowed_stats(
        filepath: Union[str, Path],
        max_size: int = 64,
    ) -> Dict[str, Any]:
        """Read a small window of a GeoTIFF. Does not load the full raster."""
        if not HAS_RASTERIO:
            raise ImportError(
                "rasterio is required for GeoTIFF support. "
                "Install with: pip install rasterio"
            )

        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"GeoTIFF file not found: {filepath}")

        from rasterio.windows import Window

        with rasterio.open(filepath) as src:
            window = Window(0, 0, min(max_size, src.width), min(max_size, src.height))
            sample = src.read(1, window=window)
            transform = src.transform
            nodata = src.nodata
            if nodata is not None:
                finite = sample[sample != nodata]
            else:
                finite = sample[np.isfinite(sample)]
            min_z = float(finite.min()) if finite.size else None
            max_z = float(finite.max()) if finite.size else None
            bounds = src.bounds
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            return {
                "crs": crs,
                "bounds": {
                    "west": float(bounds.left),
                    "south": float(bounds.bottom),
                    "east": float(bounds.right),
                    "north": float(bounds.top),
                },
                "resolution_deg": (abs(float(transform.a)), abs(float(transform.e))),
                "nodata": float(nodata) if nodata is not None else None,
                "min_elevation": min_z,
                "max_elevation": max_z,
                "window_shape": [int(sample.shape[0]), int(sample.shape[1])],
                "full_shape": [int(src.height), int(src.width)],
                "uri": str(filepath.resolve()),
            }

    @staticmethod
    def save_geotiff(
        data: np.ndarray,
        metadata: GeoTIFFMetadata,
        output_path: Union[str, Path],
    ) -> None:
        """
        Save elevation or flood depth grid as a georeferenced GeoTIFF.

        Args:
            data: 2D elevation or depth array
            metadata: Spatial metadata (bounds, CRS)
            output_path: Output file path
        """
        if not HAS_RASTERIO:
            raise ImportError(
                "rasterio is required for GeoTIFF export. "
                "Install with: pip install rasterio"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        height, width = data.shape
        dy = (metadata.bounds_north - metadata.bounds_south) / height
        dx = (metadata.bounds_east - metadata.bounds_west) / width

        transform = Affine.translation(metadata.bounds_west, metadata.bounds_north) * Affine.scale(dx, -dy)

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=data.dtype,
            crs=metadata.crs,
            transform=transform,
            nodata=metadata.nodata_value,
        ) as dst:
            dst.write(data, 1)
