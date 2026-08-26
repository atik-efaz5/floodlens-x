"""Simulation configuration dataclasses (notebook cell 522)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryCondition:
    """Defines boundary behavior for the domain edges."""

    location: str  # 'left', 'right', 'top', 'bottom', 'none'
    type: str = "reflective"  # 'reflective', 'inflow', 'open'
    h: float = 0.0
    hu: float = 0.0
    hv: float = 0.0


@dataclass(frozen=True)
class SimulationConfig:
    """Immutable configuration with physical and numerical constraints."""

    Nx: int
    Ny: int
    Lx: float
    Ly: float
    g: float = 9.81
    h_dry_threshold: float = 1e-4
    CFL: float = 0.9
    T_end: float = 1.0
    name: str = "FloodLens_Simulation"

    def __post_init__(self):
        if not isinstance(self.Nx, int) or self.Nx <= 0:
            raise ValueError(f"Nx must be a positive integer, got {self.Nx}")
        if not isinstance(self.Ny, int) or self.Ny <= 0:
            raise ValueError(f"Ny must be a positive integer, got {self.Ny}")
        if self.Lx <= 0 or self.Ly <= 0:
            raise ValueError("Domain dimensions Lx and Ly must be positive.")
        if not (0 < self.CFL < 1.5):
            raise ValueError(f"CFL must be in range (0, 1.5), got {self.CFL}")
