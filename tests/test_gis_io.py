"""GIS I/O tests for GeoTIFF and NetCDF support."""

import numpy as np
import pytest

from floodlens.application.dem_manager import DEMManager, GeoTIFFMetadata
from floodlens.core.config import SimulationConfig
from floodlens.core.state import SimulationState
from floodlens.visualization.layer import VisualizationLayer

try:
    import rasterio

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    import netCDF4

    HAS_NETCDF = True
except ImportError:
    HAS_NETCDF = False


class TestGeoTIFFMetadata:
    """Test GeoTIFF metadata handling."""

    def test_metadata_creation(self):
        """Create and validate GeoTIFF metadata."""
        metadata = GeoTIFFMetadata(
            bounds_west=0.0,
            bounds_south=0.0,
            bounds_east=1000.0,
            bounds_north=1000.0,
            crs="EPSG:4326",
            nodata_value=None,
        )

        assert metadata.bounds_west == 0.0
        assert metadata.bounds_east == 1000.0
        assert metadata.bounds_south == 0.0
        assert metadata.bounds_north == 1000.0
        assert metadata.crs == "EPSG:4326"

    def test_metadata_with_nodata(self):
        """Test metadata with nodata value."""
        metadata = GeoTIFFMetadata(
            bounds_west=0.0,
            bounds_south=0.0,
            bounds_east=500.0,
            bounds_north=500.0,
            nodata_value=-9999.0,
        )
        assert metadata.nodata_value == -9999.0


@pytest.mark.skipif(not HAS_RASTERIO, reason="rasterio not installed")
class TestGeoTIFFRoundTrip:
    """Test GeoTIFF save and load round-trip."""

    def test_geotiff_save_and_load(self, tmp_path):
        """Save and load a synthetic elevation grid as GeoTIFF."""
        # Create synthetic DEM
        z = np.random.rand(50, 50) * 100  # 50x50 grid, elevations 0-100m

        metadata = GeoTIFFMetadata(
            bounds_west=0.0,
            bounds_south=0.0,
            bounds_east=5000.0,
            bounds_north=5000.0,
            crs="EPSG:32633",  # UTM Zone 33N
        )

        output_path = tmp_path / "dem.tif"

        # Save
        DEMManager.save_geotiff(z, metadata, output_path)
        assert output_path.exists()

        # Load
        z_loaded, metadata_loaded = DEMManager.load_geotiff(output_path)

        # Validate shape and values
        assert z_loaded.shape == z.shape
        np.testing.assert_array_almost_equal(z_loaded, z, decimal=4)

        # Validate metadata
        assert metadata_loaded.bounds_west == metadata.bounds_west
        assert metadata_loaded.bounds_east == metadata.bounds_east
        assert metadata_loaded.bounds_south == metadata.bounds_south
        assert metadata_loaded.bounds_north == metadata.bounds_north

    def test_geotiff_file_not_found(self):
        """Load from non-existent GeoTIFF raises error."""
        with pytest.raises(FileNotFoundError):
            DEMManager.load_geotiff("/nonexistent/path/dem.tif")


@pytest.mark.skipif(not HAS_NETCDF, reason="netCDF4 not installed")
class TestNetCDFExport:
    """Test NetCDF time-series export."""

    def test_netcdf_export_basic(self, tmp_path):
        """Export simulation frames to NetCDF."""
        config = SimulationConfig(
            Nx=20, Ny=20, Lx=500.0, Ly=500.0, T_end=5.0
        )

        # Create synthetic frames
        frames = []
        for t in [0.0, 1.0, 2.0]:
            U = np.zeros((20, 20, 3), dtype=np.float64)
            U[:, :, 0] = 0.5 + 0.1 * t  # Increasing depth
            U[:, :, 1] = 0.1 * np.sin(2 * np.pi * t / 5.0)
            U[:, :, 2] = 0.05 * np.cos(2 * np.pi * t / 5.0)
            z = np.zeros((20, 20))

            state = SimulationState(U=U, z=z, time=t, iteration=int(t * 10))
            frames.append(state)

        output_path = tmp_path / "simulation.nc"

        # Export
        viz = VisualizationLayer()
        viz.export_netcdf(frames, config, output_path)
        assert output_path.exists()

        # Validate structure
        import netCDF4

        with netCDF4.Dataset(output_path, "r") as ds:
            assert "time" in ds.dimensions
            assert "x" in ds.dimensions
            assert "y" in ds.dimensions
            assert len(ds.dimensions["time"]) == 3
            assert len(ds.dimensions["x"]) == 20
            assert len(ds.dimensions["y"]) == 20

            assert "h" in ds.variables
            assert "hu" in ds.variables
            assert "hv" in ds.variables

            # Validate time values
            times = ds.variables["time"][:]
            np.testing.assert_array_almost_equal(times, [0.0, 1.0, 2.0])

            # Validate first depth field
            h_first = ds.variables["h"][0, :, :]
            np.testing.assert_array_almost_equal(h_first, frames[0].h, decimal=4)


@pytest.mark.skipif(not HAS_RASTERIO, reason="rasterio not installed")
class TestVisualizationGeoTIFFExport:
    """Test GeoTIFF export via VisualizationLayer."""

    def test_export_depth_as_geotiff(self, tmp_path):
        """Export flood depth field via VisualizationLayer."""
        # Create state
        U = np.zeros((30, 30, 3), dtype=np.float64)
        U[:, :, 0] = 1.5  # 1.5 m depth
        z = np.zeros((30, 30))
        state = SimulationState(U=U, z=z, time=5.0)

        metadata = GeoTIFFMetadata(
            bounds_west=0.0,
            bounds_south=0.0,
            bounds_east=3000.0,
            bounds_north=3000.0,
            crs="EPSG:3857",  # Web Mercator
        )

        output_path = tmp_path / "flood_depth.tif"

        # Export
        viz = VisualizationLayer()
        viz.export_geotiff(state, metadata, output_path)
        assert output_path.exists()

        # Verify can be reloaded
        z_loaded, metadata_loaded = DEMManager.load_geotiff(output_path)
        assert z_loaded.shape == state.h.shape
        np.testing.assert_array_almost_equal(z_loaded, state.h, decimal=4)
