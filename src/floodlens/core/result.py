"""Simulation output container (notebook cell 525)."""

from dataclasses import dataclass

from floodlens.core.state import SimulationState


@dataclass(frozen=True)
class SimulationResult:
    """Container for simulation output and diagnostic metrics."""

    name: str
    final_state: SimulationState
    total_mass: float
    peak_momentum: float

    def __repr__(self):
        return (
            f"SimulationResult(name='{self.name}', "
            f"time={self.final_state.time:.4f}s, "
            f"mass={self.total_mass:.4f}m^3, "
            f"peak_mom={self.peak_momentum:.4e})"
        )
