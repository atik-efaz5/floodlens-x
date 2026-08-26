import time

import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.simulator import ShallowWaterSimulator
from floodlens.numerical.timestepper import run_shallow_water_simulation


def test_vectorized_runtime_scaling():
    """
    Ensure 50x50 grid running until t=0.5 completes in under 1.5 seconds.
    """
    nx, ny = 50, 50
    u = np.zeros((ny, nx, 3), dtype=np.float64)
    u[:, :, 0] = 1.0
    z = np.zeros((ny, nx), dtype=np.float64)
    manning = np.full_like(z, 0.03)

    start_time = time.perf_counter()
    frames, u_out, _ = run_shallow_water_simulation(
        u,
        z,
        manning,
        0.0,
        0.0,
        {"location": "none"},
        0.5,
        0.01,
        float(nx),
        float(ny),
        1.0,
        1.0,
        nx,
        ny,
        9.81,
        1e-4,
        store_frames=True,
        cfl_sim=0.9,
        bc_type="reflective",
    )
    elapsed = time.perf_counter() - start_time

    assert elapsed < 1.5, f"Vectorized solver took {elapsed:.2f}s, exceeding 1.5s threshold"
    assert np.all(np.isfinite(u_out))
    assert len(frames) >= 1


def test_multigrid_vectorized_throughput():
    """Verify solver scales efficiently from small to medium grids."""
    for size in [20, 60]:
        config = SimulationConfig(
            Nx=size,
            Ny=size,
            Lx=500.0,
            Ly=500.0,
            T_end=0.5,
            CFL=0.8,
            manning_n=0.03,
        )
        z = np.zeros((size, size))
        sim = ShallowWaterSimulator(config)
        sim.set_initial_conditions(h_init=0.5, z=z)

        start_time = time.perf_counter()
        sim.run()
        elapsed = time.perf_counter() - start_time

        assert elapsed < 1.0, f"Grid {size}x{size} exceeded 1.0s runtime budget ({elapsed:.3f}s)"
        assert sim.get_state() is not None
