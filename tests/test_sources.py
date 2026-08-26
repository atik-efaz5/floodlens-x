"""Rainfall and infiltration source-term tests (EXTRACTION_PLAN Section C.2)."""

import numpy as np

from floodlens.numerical.timestepper import run_shallow_water_simulation

from tests import oracle

G = 9.81
H_DRY = 1e-3
EQUIV_TOL = 1e-15
MASS_TOL = 1e-12


def _flat_domain(nx=50, ny=50, dx=1.0, dy=1.0):
    lx = nx * dx
    ly = ny * dy
    z = np.zeros((ny, nx), dtype=np.float64)
    manning = np.zeros_like(z)
    return z, manning, lx, ly, dx, dy, nx, ny


class TestZeroRainEquivalence:
    """Rainfall=0 and infiltration=0 reproduces the frozen baseline bit-for-bit."""

    def test_zero_rain_matches_oracle_lake_at_rest(self):
        nx = ny = 50
        lx = ly = 10.0
        dx = lx / nx
        dy = ly / ny
        x = np.linspace(0.5 * dx, lx - 0.5 * dx, nx, dtype=np.float64)
        y = np.linspace(0.5 * dy, ly - 0.5 * dy, ny, dtype=np.float64)
        x_grid, y_grid = np.meshgrid(x, y)
        z = 0.1 * ((x_grid - 5.0) ** 2 + (y_grid - 5.0) ** 2)
        u_init = np.zeros((ny, nx, 3), dtype=np.float64)
        u_init[:, :, 0] = np.maximum(0.0, 2.0 - z)
        manning = np.zeros_like(z)

        u_oracle = oracle.advance_simulation(
            u_init, z, manning, 0.0, 0.0, 10, G, H_DRY, lx, ly, dx, dy, nx, ny
        )

        u_package = u_init.copy()
        for _ in range(10):
            dt, _, _ = oracle.calculate_dt_cfl(u_package, dx, dy, G, H_DRY)
            _, u_package, _ = run_shallow_water_simulation(
                u_package,
                z,
                manning,
                0.0,
                0.0,
                {"location": "none"},
                dt,
                0.01,
                lx,
                ly,
                dx,
                dy,
                nx,
                ny,
                G,
                H_DRY,
                False,
            )

        max_diff = float(np.max(np.abs(u_package - u_oracle)))
        assert max_diff < EQUIV_TOL


class TestFlatBedMassConservation:
    """Constant rain on a flat dry bed conserves integrated mass."""

    def test_rainfall_volume_matches_analytical_integral(self):
        z, manning, lx, ly, dx, dy, nx, ny = _flat_domain()
        u_init = np.zeros((ny, nx, 3), dtype=np.float64)
        rain_rate = 1e-3
        duration = 10.0

        _, u_final, _ = run_shallow_water_simulation(
            u_init,
            z,
            manning,
            rain_rate,
            0.0,
            {"location": "none"},
            duration,
            0.01,
            lx,
            ly,
            dx,
            dy,
            nx,
            ny,
            G,
            H_DRY,
            False,
        )

        domain_area = nx * ny * dx * dy
        expected_volume = domain_area * rain_rate * duration
        actual_volume = float(np.sum(u_final[:, :, 0]) * dx * dy)

        assert abs(actual_volume - expected_volume) < MASS_TOL


class TestInfiltrationNonNegativity:
    """Infiltration cannot drive water depth below zero."""

    def test_depth_remains_non_negative_under_extreme_infiltration(self):
        z, manning, lx, ly, dx, dy, nx, ny = _flat_domain()
        u_init = np.zeros((ny, nx, 3), dtype=np.float64)
        u_init[:, :, 0] = 0.01
        infiltration_rate = 1.0
        duration = 10.0

        _, u_final, _ = run_shallow_water_simulation(
            u_init,
            z,
            manning,
            0.0,
            infiltration_rate,
            {"location": "none"},
            duration,
            0.01,
            lx,
            ly,
            dx,
            dy,
            nx,
            ny,
            G,
            H_DRY,
            False,
        )

        assert np.min(u_final[:, :, 0]) >= 0.0
        assert np.all(u_final[:, :, 0] >= 0.0)
