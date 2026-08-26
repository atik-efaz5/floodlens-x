import numpy as np
from typing import Literal

BoundaryType = Literal["reflective", "transmissive", "wall", "open"]

def apply_ghost_cells(U: np.ndarray, z: np.ndarray, bc_type: str = "reflective") -> tuple[np.ndarray, np.ndarray]:
    """
    Pad state U and topography z with 1 layer of ghost cells according to bc_type.
    U shape: (nx, ny, 3) -> U_pad: (nx+2, ny+2, 3)
    z shape: (nx, ny) -> z_pad: (nx+2, ny+2)
    """
    nx, ny, _ = U.shape
    U_pad = np.zeros((nx + 2, ny + 2, 3), dtype=U.dtype)
    z_pad = np.zeros((nx + 2, ny + 2), dtype=z.dtype)

    # Interior
    U_pad[1:-1, 1:-1, :] = U
    z_pad[1:-1, 1:-1] = z

    # Topography: continuous extrapolation to ghost cells
    z_pad[0, 1:-1] = z[0, :]
    z_pad[-1, 1:-1] = z[-1, :]
    z_pad[1:-1, 0] = z[:, 0]
    z_pad[1:-1, -1] = z[:, -1]
    z_pad[0, 0] = z[0, 0]
    z_pad[0, -1] = z[0, -1]
    z_pad[-1, 0] = z[-1, 0]
    z_pad[-1, -1] = z[-1, -1]

    bc = str(bc_type).lower()
    if bc in ("reflective", "wall"):
        # X-boundaries: flip hu (channel 1), keep h and hv
        U_pad[0, 1:-1, 0] = U[0, :, 0]
        U_pad[0, 1:-1, 1] = -U[0, :, 1]
        U_pad[0, 1:-1, 2] = U[0, :, 2]

        U_pad[-1, 1:-1, 0] = U[-1, :, 0]
        U_pad[-1, 1:-1, 1] = -U[-1, :, 1]
        U_pad[-1, 1:-1, 2] = U[-1, :, 2]

        # Y-boundaries: flip hv (channel 2), keep h and hu
        U_pad[1:-1, 0, 0] = U[:, 0, 0]
        U_pad[1:-1, 0, 1] = U[:, 0, 1]
        U_pad[1:-1, 0, 2] = -U[:, 0, 2]

        U_pad[1:-1, -1, 0] = U[:, -1, 0]
        U_pad[1:-1, -1, 1] = U[:, -1, 1]
        U_pad[1:-1, -1, 2] = -U[:, -1, 2]

    elif bc in ("transmissive", "open", "outflow"):
        # Zero-gradient: direct copy of all state variables
        U_pad[0, 1:-1, :] = U[0, :, :]
        U_pad[-1, 1:-1, :] = U[-1, :, :]
        U_pad[1:-1, 0, :] = U[:, 0, :]
        U_pad[1:-1, -1, :] = U[:, -1, :]

    else:
        raise ValueError(f"Unsupported boundary condition: {bc_type}")

    return U_pad, z_pad
