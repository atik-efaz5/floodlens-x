import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from floodlens.application.dem_manager import DEMManager
from floodlens.application.service import SimulationService
from floodlens.core.config import SimulationConfig
from floodlens.visualization.layer import VisualizationLayer


def test_full_pipeline_synthetic_terrain(tmp_path):
    """
    Test complete lifecycle:
    1. DEM generation & resampling via DEMManager
    2. Configuration setup with transmissive boundaries & rainfall
    3. Multi-step execution via SimulationService
    4. Diagnostics & metric generation via VisualizationLayer
    5. Headless figure export
    """
    raw_x = np.linspace(0, 1000, 100)
    raw_y = np.linspace(0, 1000, 100)
    raw_z = np.sin(raw_x[:, None] / 200.0) * np.cos(raw_y[None, :] / 200.0) * 5.0 + 10.0

    dem_mgr = DEMManager()
    validated_dem = dem_mgr.validate_raw_input(raw_z)

    config = SimulationConfig(
        Nx=30,
        Ny=30,
        Lx=1000.0,
        Ly=1000.0,
        T_end=2.0,
        CFL=0.8,
        manning_n=0.03,
        boundary_condition="transmissive",
    )

    resampled_z = dem_mgr.resample_terrain(validated_dem, config)
    assert resampled_z.shape == (30, 30)

    service = SimulationService(config)
    result = service.run_scenario(
        dem=resampled_z,
        rainfall_rate=1e-4,
        steps=5,
        track_progress=False,
    )

    assert result.success is True
    assert result.final_state is not None
    assert result.final_state.U.shape == (30, 30, 3)
    assert np.all(result.final_state.h >= 0.0)
    assert np.all(np.isfinite(result.final_state.U))

    viz = VisualizationLayer(h_dry_threshold=config.h_dry_threshold)
    metrics = viz.compute_metrics(result.final_state, config)
    assert "inundated_area" in metrics
    assert "max_depth" in metrics
    assert metrics["max_depth"] >= 0.0

    fig_path = tmp_path / "flood_depth.png"
    fig = viz.plot_instantaneous_depth(
        result.final_state, resampled_z, save_path=str(fig_path)
    )
    assert fig_path.exists()
    assert fig is not None
