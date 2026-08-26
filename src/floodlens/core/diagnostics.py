"""Simulation diagnostics report (notebook cell 532)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DiagnosticsReport:
    """Structured container for simulation metrics and metadata."""

    name: str
    config: Dict[str, Any]
    timestamps: List[float] = field(default_factory=list)
    total_mass: List[float] = field(default_factory=list)
    max_velocity: List[float] = field(default_factory=list)
    max_cfl: List[float] = field(default_factory=list)
    min_h: List[float] = field(default_factory=list)
    wall_time_s: float = 0.0
    total_iterations: int = 0
    bit_perfect_oracle: bool = True

    def summary(self):
        """Provides a human-readable summary of the simulation performance."""
        mass_err = (
            (self.total_mass[-1] - self.total_mass[0]) / self.total_mass[0]
            if self.total_mass[0] != 0
            else 0.0
        )
        avg_step = (
            (self.wall_time_s / self.total_iterations * 1000)
            if self.total_iterations > 0
            else 0.0
        )

        print(f"=== Diagnostics Summary: {self.name} ===")
        print(f"Iterations:      {self.total_iterations}")
        print(f"Wall Time:       {self.wall_time_s:.4f} s")
        print(f"Avg Step Time:   {avg_step:.2f} ms")
        print(f"Rel. Mass Error: {mass_err:.2e}")
        print(f"Min Depth (h):   {min(self.min_h):.4e} m")
        print(f"Max Velocity:    {max(self.max_velocity):.4f} m/s")
        print(f"Max CFL reached: {max(self.max_cfl):.4f}")
        print(f"Oracle Integrity: {'PASSED' if self.bit_perfect_oracle else 'FAILED'}")
        print("=" * 35)
