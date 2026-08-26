"""Spatial grid metrics (notebook cell 522)."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GridData:
    """Spatial metrics for the simulation grid."""

    dx: np.float64
    dy: np.float64
    X: np.ndarray
    Y: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "dx", np.float64(self.dx))
        object.__setattr__(self, "dy", np.float64(self.dy))
        object.__setattr__(self, "X", np.asarray(self.X, dtype=np.float64))
        object.__setattr__(self, "Y", np.asarray(self.Y, dtype=np.float64))
