"""Simulation lifecycle orchestration (notebook cell 538)."""

from dataclasses import dataclass
from typing import Callable, Optional, Union

import numpy as np

from floodlens.application.progress import ProgressManager
from floodlens.core.config import SimulationConfig
from floodlens.core.simulator import ShallowWaterSimulatorWithDiagnostics
from floodlens.core.state import SimulationState


@dataclass
class PipelineResult:
    """Outcome of a managed multi-step simulation scenario."""

    success: bool
    final_state: Optional[SimulationState] = None


class SimulationService:
    """Orchestrates the lifecycle of the simulator with robust error handling."""

    def __init__(
        self, simulator_or_config: Union[ShallowWaterSimulatorWithDiagnostics, SimulationConfig]
    ):
        if isinstance(simulator_or_config, SimulationConfig):
            self.config = simulator_or_config
            self.sim = ShallowWaterSimulatorWithDiagnostics(simulator_or_config)
        else:
            self.sim = simulator_or_config
            self.config = simulator_or_config.config
        self.progress = ProgressManager()
        self.is_running = False

    def run_scenario(
        self,
        steps: int = 1,
        rainfall: float = 0.0,
        rainfall_rate: Optional[float] = None,
        dem: Optional[np.ndarray] = None,
        track_progress: bool = True,
        callback: Optional[Callable] = None,
    ) -> PipelineResult:
        """Executes a multi-step simulation cycle with telemetry."""
        self.is_running = True
        if track_progress:
            self.progress.total_steps = steps

        if dem is not None:
            expected_shape = (self.config.Ny, self.config.Nx)
            if dem.shape != expected_shape:
                raise ValueError(
                    f"DEM shape {dem.shape} does not match configuration {expected_shape}"
                )
            u_init = np.zeros(expected_shape + (3,), dtype=np.float64)
            self.sim.set_initial_conditions(dem, u_init)

        rain = rainfall_rate if rainfall_rate is not None else rainfall
        manning_field = None
        if self.config.manning_n > 0.0:
            z_ref = dem if dem is not None else self.sim.get_state().z
            manning_field = np.full_like(z_ref, self.config.manning_n, dtype=np.float64)

        if track_progress:
            print(f"Initializing scenario: {self.sim.config.name}")

        try:
            for _ in range(steps):
                if not self.is_running:
                    break

                self.sim.run(rainfall_rate=rain, manning_n=manning_field)

                state = self.sim.get_state()
                if track_progress:
                    u, v, _ = self.sim.velocity
                    max_v = np.max(np.sqrt(u**2 + v**2))
                    mass0 = self.sim.diagnostics.total_mass[0]
                    mass_curr = self.sim.diagnostics.total_mass[-1]
                    mass_err = (mass_curr - mass0) / mass0 if mass0 != 0 else 0.0
                    self.progress.update(state.iteration, state.time, max_v, mass_err)

                if callback is not None:
                    callback(self.sim)

                if not np.isfinite(state.U).all():
                    raise RuntimeError(
                        f"Numerical divergence detected at iteration {state.iteration}"
                    )
                _, _, speed = self.sim.velocity
                if np.max(speed) > 100.0:
                    raise RuntimeError(
                        f"Numerical divergence detected at iteration {state.iteration}"
                    )

            if track_progress:
                print(f"\nScenario '{self.sim.config.name}' completed successfully.")
                self.sim.diagnostics.summary()
            return PipelineResult(success=True, final_state=self.sim.get_state())

        except Exception as e:
            self.is_running = False
            if track_progress:
                print(f"\n[CRITICAL FAILURE]: {str(e)}")
            final_state = self.sim._state
            return PipelineResult(success=False, final_state=final_state)
        finally:
            self.is_running = False
