"""Public core API for FloodLens-X."""

from floodlens.core.config import BoundaryCondition, SimulationConfig
from floodlens.core.diagnostics import DiagnosticsReport
from floodlens.core.grid import GridData
from floodlens.core.result import SimulationResult
from floodlens.core.simulator import (
    ShallowWaterSimulator,
    ShallowWaterSimulatorWithDiagnostics,
)
from floodlens.core.state import SimulationState

__all__ = [
    "BoundaryCondition",
    "SimulationConfig",
    "GridData",
    "SimulationState",
    "SimulationResult",
    "DiagnosticsReport",
    "ShallowWaterSimulator",
    "ShallowWaterSimulatorWithDiagnostics",
]
