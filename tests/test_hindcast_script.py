"""Hindcast script validation tests."""

import numpy as np
import pytest


def test_sunamganj_synthetic_dem_generator():
    """Test synthetic DEM generation for Sunamganj basin."""
    from scripts.run_sunamganj_hindcast import generate_sunamganj_synthetic_dem

    z, meta = generate_sunamganj_synthetic_dem(nx=40, ny=40)

    assert z.shape == (40, 40)
    assert np.all(np.isfinite(z))
    assert np.min(z) >= 0.8
    assert np.max(z) <= 35.0
    assert meta.crs == "EPSG:4326"
    assert meta.bounds_west == 91.20
    assert meta.bounds_south == 24.80


def test_hindcast_execution_smoke(tmp_path):
    """Smoke test for full hindcast execution."""
    from scripts.run_sunamganj_hindcast import run_hindcast

    out_dir = tmp_path / "hindcast_test"
    run_hindcast(output_dir=str(out_dir))

    assert (out_dir / "sunamganj_flood_depth.png").exists()
    assert (out_dir / "sunamganj_state.npz").exists()

    data = np.load(out_dir / "sunamganj_state.npz")
    assert "U" in data
    assert "z" in data
    assert "time" in data
    assert data["U"].shape == (120, 120, 3)
    assert data["z"].shape == (120, 120)
    assert np.all(np.isfinite(data["U"]))
    assert np.all(np.isfinite(data["z"]))
