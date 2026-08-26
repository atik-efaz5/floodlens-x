import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.simulator import ShallowWaterSimulator


def _sunamganj_topography(nx: int, ny: int, lx: float, ly: float) -> np.ndarray:
  y = np.linspace(0, ly, ny)
  x = np.linspace(0, lx, nx)
  y_grid, x_grid = np.meshgrid(y, x, indexing="ij")
  return 2.0 + 20.0 * (x_grid / lx) ** 2 + 3.0 * np.sin(np.pi * y_grid / ly)


def test_reproduce_and_bound_steep_dem_velocity():
    """
    Simulate steep real-world terrain gradient (elevations 2m to 25m over 1km)
    with heavy convective rainfall (50 mm/hr = 1.388e-5 m/s) over dry bed.
    Verify maximum flow velocity remains physically bounded (< 10.0 m/s)
    and does not experience the legacy 43.77 m/s singularity spike.
    """
    nx, ny = 50, 50
    lx, ly = 1000.0, 1000.0
    z = _sunamganj_topography(nx, ny, lx, ly)

    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=lx,
        Ly=ly,
        T_end=10.0,
        CFL=0.5,
        manning_n=0.035,
        h_dry_threshold=1e-3,
        boundary_condition="transmissive",
    )

    sim = ShallowWaterSimulator(config)
    sim.set_initial_conditions(z=z, h_init=0.0)

    result = sim.run(rainfall_rate=1.388e-5, track_frames=False)

    _, _, speed = sim.velocity
    max_speed = float(np.max(speed))

    assert result.success is True
    assert np.all(np.isfinite(result.final_state.U))
    assert np.all(result.final_state.h >= 0.0)
    assert max_speed < 10.0, f"Unphysical velocity spike detected: max_speed={max_speed:.2f} m/s"


def test_dry_sloped_bed_zero_velocity_without_rain():
    """
    Steep dry sloped terrain without rain must remain stationary with zero velocity.
    """
    nx, ny = 30, 30
    y = np.linspace(0, 500.0, ny)
    x = np.linspace(0, 500.0, nx)
    y_grid, x_grid = np.meshgrid(y, x, indexing="ij")
    z = 10.0 + 0.05 * x_grid + 0.02 * y_grid

    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=500.0,
        Ly=500.0,
        T_end=5.0,
        CFL=0.5,
        manning_n=0.03,
        h_dry_threshold=1e-3,
        boundary_condition="reflective",
    )

    sim = ShallowWaterSimulator(config)
    sim.set_initial_conditions(z=z, h_init=0.0)
    result = sim.run(rainfall_rate=0.0)

    assert result.success is True
    _, _, speed = sim.velocity
    assert np.max(speed) == 0.0
