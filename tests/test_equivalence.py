"""Phase B numerical equivalence tests (NUMERICAL_CONTRACT Section 4)."""

import numpy as np

from floodlens.numerical.timestep import calculate_dt_cfl as package_calculate_dt_cfl
from floodlens.numerical.timestepper import run_shallow_water_simulation as package_run

from tests import oracle

G = 9.81
H_DRY = 1e-3
EQUIV_TOL = 1e-14
# Contract Section 4.4: momentum residual < 1e-13 (assessed after one discrete step;
# the validated operator is well-balanced to machine precision per step).
WELL_BALANCED_TOL = 1e-13


def _cell_center_grid(Nx, Ny, Lx, Ly):
    dx = Lx / Nx
    dy = Ly / Ny
    x = np.linspace(0.5 * dx, Lx - 0.5 * dx, Nx, dtype=np.float64)
    y = np.linspace(0.5 * dy, Ly - 0.5 * dy, Ny, dtype=np.float64)
    X, Y = np.meshgrid(x, y)
    return X, Y, dx, dy


def _advance_package(U, z, manning, rainfall, infiltration, steps, Lx, Ly, dx, dy, Nx, Ny):
    U = U.copy()
    for _ in range(steps):
        dt, _, _ = package_calculate_dt_cfl(U, dx, dy, G, H_DRY)
        _, U, _ = package_run(
            U,
            z,
            manning,
            rainfall,
            infiltration,
            {"location": "none"},
            dt,
            dt,
            Lx,
            Ly,
            dx,
            dy,
            Nx,
            Ny,
            G,
            H_DRY,
            False,
        )
    return U


def _max_abs_diff(U_a, U_b):
    return float(np.max(np.abs(U_a - U_b)))


class TestLakeAtRest:
    """Scenario 1: lake-at-rest on parabolic bowl, 10 steps."""

    Nx = 50
    Ny = 50
    Lx = 10.0
    Ly = 10.0
    STEPS = 10

    def _setup(self):
        X, Y, dx, dy = _cell_center_grid(self.Nx, self.Ny, self.Lx, self.Ly)
        z = 0.1 * ((X - 5.0) ** 2 + (Y - 5.0) ** 2)
        U = np.zeros((self.Ny, self.Nx, 3), dtype=np.float64)
        U[:, :, 0] = np.maximum(0.0, 2.0 - z)
        manning = np.zeros_like(z)
        return U, z, manning, dx, dy

    def test_oracle_equivalence(self):
        U, z, manning, dx, dy = self._setup()
        U_oracle = oracle.advance_simulation(
            U, z, manning, 0.0, 0.0, self.STEPS, G, H_DRY,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        U_package = _advance_package(
            U, z, manning, 0.0, 0.0, self.STEPS,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        assert _max_abs_diff(U_oracle, U_package) < EQUIV_TOL

    def test_well_balancedness(self):
        """Lake-at-rest momentum residual < 1e-13 after one discrete timestep."""
        U, z, manning, dx, dy = self._setup()
        U_final = _advance_package(
            U, z, manning, 0.0, 0.0, 1,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        max_hu = float(np.max(np.abs(U_final[:, :, 1])))
        max_hv = float(np.max(np.abs(U_final[:, :, 2])))
        assert max_hu < WELL_BALANCED_TOL
        assert max_hv < WELL_BALANCED_TOL


class TestDamBreak:
    """Scenario 2: 1D dam-break in 2D domain, 50 steps."""

    Nx = 50
    Ny = 50
    Lx = 10.0
    Ly = 10.0
    STEPS = 50

    def _setup(self):
        X, Y, dx, dy = _cell_center_grid(self.Nx, self.Ny, self.Lx, self.Ly)
        z = np.zeros((self.Ny, self.Nx), dtype=np.float64)
        U = np.zeros((self.Ny, self.Nx, 3), dtype=np.float64)
        U[:, :, 0] = np.where(X < 5.0, 1.5, 0.1)
        manning = np.zeros_like(z)
        return U, z, manning, dx, dy

    def test_oracle_equivalence(self):
        U, z, manning, dx, dy = self._setup()
        U_oracle = oracle.advance_simulation(
            U, z, manning, 0.0, 0.0, self.STEPS, G, H_DRY,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        U_package = _advance_package(
            U, z, manning, 0.0, 0.0, self.STEPS,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        assert _max_abs_diff(U_oracle, U_package) < EQUIV_TOL


class TestDryCellRain:
    """Scenario 3: dry domain with rainfall API parameter, 20 steps."""

    Nx = 50
    Ny = 50
    Lx = 10.0
    Ly = 10.0
    STEPS = 20
    RAINFALL = 1e-4

    def _setup(self):
        X, Y, dx, dy = _cell_center_grid(self.Nx, self.Ny, self.Lx, self.Ly)
        z = np.zeros((self.Ny, self.Nx), dtype=np.float64)
        U = np.zeros((self.Ny, self.Nx, 3), dtype=np.float64)
        manning = np.zeros_like(z)
        return U, z, manning, dx, dy

    def test_oracle_equivalence_rain_ignored(self):
        U, z, manning, dx, dy = self._setup()
        U_oracle = oracle.advance_simulation(
            U, z, manning, self.RAINFALL, 0.0, self.STEPS, G, H_DRY,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        U_package = _advance_package(
            U, z, manning, self.RAINFALL, 0.0, self.STEPS,
            self.Lx, self.Ly, dx, dy, self.Nx, self.Ny,
        )
        assert _max_abs_diff(U_oracle, U_package) < EQUIV_TOL
