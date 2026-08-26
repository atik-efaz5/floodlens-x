"""Mutable simulation state container (notebook cell 522)."""

from dataclasses import dataclass

import numpy as np


@dataclass
class SimulationState:
    """Snapshot of simulation at a specific timestamp."""

    U: np.ndarray  # (Ny, Nx, 3) -> [h, hu, hv]
    z: np.ndarray  # (Ny, Nx)
    time: np.float64 = 0.0
    iteration: int = 0

    def __post_init__(self):
        self.U = self.U.astype(np.float64)
        self.z = self.z.astype(np.float64)
        self.time = np.float64(self.time)

    @property
    def h(self) -> np.ndarray:
        return self.U[:, :, 0]

    @property
    def hu(self) -> np.ndarray:
        return self.U[:, :, 1]

    @property
    def hv(self) -> np.ndarray:
        return self.U[:, :, 2]

    @property
    def eta(self) -> np.ndarray:
        """Water surface elevation (h + z)."""
        return self.h + self.z
