"""Simulation progress telemetry (notebook cell 538)."""

import logging

logger = logging.getLogger(__name__)


class ProgressManager:
    """Publishes real-time telemetry during simulation execution."""

    def __init__(self, total_steps: int = 0):
        self.history = []
        self.total_steps = total_steps
        self.current_step = 0

    def update(self, iteration: int, current_time: float, max_v: float, mass_err: float):
        self.current_step = iteration
        metrics = {
            "Iteration": iteration,
            "SimTime": f"{current_time:.2f}s",
            "PeakVelocity": f"{max_v:.4f} m/s",
            "MassError": f"{mass_err:.2e}",
        }
        self.history.append(metrics)

        logger.info(f"Step {self.current_step}/{self.total_steps}")
