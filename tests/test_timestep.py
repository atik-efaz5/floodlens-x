"""Phase B CFL timestep regression tests."""

import numpy as np

from floodlens.numerical.timestep import DEFAULT_DT_FALLBACK, calculate_dt_cfl, dt_initial
from tests import oracle

G = 9.81
H_DRY = 1e-3
DX = 0.2
DY = 0.2
C = 0.9
EQUIV_TOL = 1e-15


def _expected_dt(U, dx, dy, g, h_dry, c=C, dt_fallback=DEFAULT_DT_FALLBACK):
    h_vals = U[:, :, 0]
    hu_vals = U[:, :, 1]
    hv_vals = U[:, :, 2]

    u_vals = np.zeros_like(h_vals)
    v_vals = np.zeros_like(h_vals)
    wet = h_vals > h_dry
    np.divide(hu_vals, h_vals, out=u_vals, where=wet)
    np.divide(hv_vals, h_vals, out=v_vals, where=wet)

    sqrt_gh = np.zeros_like(h_vals)
    np.sqrt(g * h_vals, out=sqrt_gh, where=wet)

    max_speed_x = np.max(np.abs(u_vals) + sqrt_gh)
    max_speed_y = np.max(np.abs(v_vals) + sqrt_gh)

    if max_speed_x > 1e-12 and max_speed_y > 1e-12:
        return c * min(dx / max_speed_x, dy / max_speed_y)
    if max_speed_x > 1e-12:
        return c * (dx / max_speed_x)
    if max_speed_y > 1e-12:
        return c * (dy / max_speed_y)
    return dt_fallback


def _active_flow_state():
    U = np.zeros((8, 8, 3), dtype=np.float64)
    U[:, :, 0] = 2.0
    U[:, :, 1] = 0.5
    U[:, :, 2] = -0.25
    return U


class TestCalculateDtCfl:
    def test_fallback_dt_initial_when_speeds_near_zero(self):
        U = np.zeros((10, 10, 3), dtype=np.float64)
        dt, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY)
        assert dt == dt_initial
        assert dt == DEFAULT_DT_FALLBACK
        assert dt == 0.01

    def test_dynamic_cfl_scaling_under_active_flow(self):
        U = _active_flow_state()

        dt, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY, C=C)
        expected = _expected_dt(U, DX, DY, G, H_DRY, c=C)

        assert expected != DEFAULT_DT_FALLBACK
        assert dt == expected

    def test_cfl_halves_timestep_under_active_flow(self):
        U = _active_flow_state()

        dt_half, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY, C=0.5)
        dt_full, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY, C=1.0)
        dt_default, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY, C=0.9)

        assert dt_half == 0.5 * dt_full
        assert dt_half == (0.5 / 1.0) * dt_full
        assert dt_default == 0.9 * dt_full

    def test_default_cfl_maintains_baseline_timestep(self):
        U = _active_flow_state()

        dt_default, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY)
        dt_explicit, _, _ = calculate_dt_cfl(
            U, DX, DY, G, H_DRY, C=0.9, dt_fallback=DEFAULT_DT_FALLBACK
        )
        dt_oracle, _, _ = oracle.calculate_dt_cfl(U, DX, DY, G, H_DRY, C=0.9)

        assert dt_default == dt_explicit
        assert dt_default == dt_oracle

    def test_default_cfl_maintains_baseline_simulation(self):
        """Default CFL=0.9 wiring reproduces frozen oracle on lake-at-rest."""
        nx = ny = 20
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

        dt, _, _ = calculate_dt_cfl(u_init, dx, dy, G, H_DRY)
        from floodlens.numerical.timestepper import run_shallow_water_simulation

        _, u_package, _ = run_shallow_water_simulation(
            u_init.copy(),
            z,
            manning,
            0.0,
            0.0,
            {"location": "none"},
            dt,
            DEFAULT_DT_FALLBACK,
            lx,
            ly,
            dx,
            dy,
            nx,
            ny,
            G,
            H_DRY,
        )
        u_oracle = oracle.advance_simulation(
            u_init, z, manning, 0.0, 0.0, 1, G, H_DRY, lx, ly, dx, dy, nx, ny
        )

        max_diff = float(np.max(np.abs(u_package - u_oracle)))
        assert max_diff < EQUIV_TOL
