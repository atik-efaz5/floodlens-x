"""Simulation lifecycle orchestration (notebook cell 538)."""

from typing import Callable, Optional

import numpy as np

from floodlens.application.progress import ProgressManager
from floodlens.core.simulator import ShallowWaterSimulatorWithDiagnostics


class SimulationService:
    """Orchestrates the lifecycle of the simulator with robust error handling."""

    def __init__(self, simulator: ShallowWaterSimulatorWithDiagnostics):
        self.sim = simulator
        self.progress = ProgressManager()
        self.is_running = False

    def run_scenario(
        self,
        steps: int,
        rainfall: float = 0.0,
        callback: Optional[Callable] = None,
    ):
        """Executes a multi-step simulation cycle with telemetry."""
        self.is_running = True
        self.progress.total_steps = steps
        print(f"Initializing scenario: {self.sim.config.name}")

        try:
            for i in range(steps):
                if not self.is_running:
                    break

                # Perform computation
                self.sim.run(rainfall_rate=rainfall)

                # Sample Diagnostics
                state = self.sim.get_state()
                u, v, _ = self.sim.velocity
                max_v = np.max(np.sqrt(u**2 + v**2))
                mass0 = self.sim.diagnostics.total_mass[0]
                mass_curr = self.sim.diagnostics.total_mass[-1]
                mass_err = (mass_curr - mass0) / mass0 if mass0 != 0 else 0.0

                # Update Telemetry
                self.progress.update(state.iteration, state.time, max_v, mass_err)

                # Safety Check: Divergence Detection
                if not np.isfinite(state.U).all() or max_v > 100.0:
                    raise RuntimeError(
                        f"Numerical divergence detected at iteration {state.iteration}"
                    )

            print(f"\nScenario '{self.sim.config.name}' completed successfully.")
            self.sim.diagnostics.summary()

        except Exception as e:
            self.is_running = False
            print(f"\n[CRITICAL FAILURE]: {str(e)}")
        finally:
            self.is_running = False
