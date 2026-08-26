import numpy as np
import pytest
from floodlens.numerical.timestepper import run_shallow_water_simulation
from floodlens.numerical.boundary import apply_ghost_cells

def test_reflective_bc_baseline_equivalence():
    nx, ny = 20, 20
    U = np.zeros((nx, ny, 3), dtype=np.float64)
    U[:, :, 0] = 1.0
    U[:, :, 1] = 0.5
    z = np.zeros((nx, ny), dtype=np.float64)
    
    U_pad, _ = apply_ghost_cells(U, z, bc_type="reflective")
    np.testing.assert_array_equal(U_pad[0, 1:-1, 1], -U[0, :, 1])
    np.testing.assert_array_equal(U_pad[-1, 1:-1, 1], -U[-1, :, 1])
    np.testing.assert_array_equal(U_pad[1:-1, 0, 2], -U[:, 0, 2])
    np.testing.assert_array_equal(U_pad[1:-1, -1, 2], -U[:, -1, 2])

def test_transmissive_bc_outflow_gradient():
    nx, ny = 20, 20
    U = np.zeros((nx, ny, 3), dtype=np.float64)
    U[:, :, 0] = 1.5
    U[:, :, 1] = 0.8
    z = np.zeros((nx, ny), dtype=np.float64)

    U_pad, _ = apply_ghost_cells(U, z, bc_type="transmissive")
    np.testing.assert_array_equal(U_pad[0, 1:-1, :], U[0, :, :])
    np.testing.assert_array_equal(U_pad[-1, 1:-1, :], U[-1, :, :])
    np.testing.assert_array_equal(U_pad[1:-1, 0, :], U[:, 0, :])
    np.testing.assert_array_equal(U_pad[1:-1, -1, :], U[:, -1, :])

def test_unsupported_bc_raises_error():
    U = np.zeros((5, 5, 3))
    z = np.zeros((5, 5))
    with pytest.raises(ValueError, match="Unsupported boundary condition"):
        apply_ghost_cells(U, z, bc_type="invalid_bc")
