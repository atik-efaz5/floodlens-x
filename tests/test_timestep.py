"""Phase B CFL timestep regression tests."""

import numpy as np

from floodlens.numerical.timestep import calculate_dt_cfl, dt_initial

G = 9.81
H_DRY = 1e-3
DX = 0.2
DY = 0.2
C = 0.9


def _expected_dt(U, dx, dy, g, h_dry, c=C):
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
    return dt_initial


class TestCalculateDtCfl:
    def test_fallback_dt_initial_when_speeds_near_zero(self):
        U = np.zeros((10, 10, 3), dtype=np.float64)
        dt, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY)
        assert dt == dt_initial
        assert dt == 0.01

    def test_dynamic_cfl_scaling_under_active_flow(self):
        U = np.zeros((8, 8, 3), dtype=np.float64)
        U[:, :, 0] = 2.0
        U[:, :, 1] = 0.5
        U[:, :, 2] = -0.25

        dt, _, _ = calculate_dt_cfl(U, DX, DY, G, H_DRY, C=C)
        expected = _expected_dt(U, DX, DY, G, H_DRY, c=C)

        assert expected != dt_initial
        assert dt == expected
