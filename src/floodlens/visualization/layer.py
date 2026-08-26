"""Read-only visualization engine for simulation data (notebook cells 544, 545)."""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.diagnostics import DiagnosticsReport
from floodlens.core.state import SimulationState

if TYPE_CHECKING:
    from floodlens.core.simulator import ShallowWaterSimulator


class VisualizationLayer:
    """Read-only engine for simulation data visualization and spatial analysis."""

    def __init__(self, h_dry_threshold: float = 1e-3):
        self.h_dry = h_dry_threshold
        self.max_depth_map = None

    def reset_peak_tracking(self):
        self.max_depth_map = None

    def update_peak_depth(self, state: SimulationState):
        """Accumulates the maximum depth seen at each cell."""
        if self.max_depth_map is None:
            self.max_depth_map = state.h.copy()
        else:
            self.max_depth_map = np.maximum(self.max_depth_map, state.h)

    def _finalize_figure(
        self, fig: plt.Figure, save_path: Optional[str] = None
    ) -> plt.Figure:
        if save_path is not None:
            fig.savefig(save_path, bbox_inches="tight")
        return fig

    def plot_instantaneous_depth(
        self,
        state: SimulationState,
        title: str = "Water Depth",
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """Displays instantaneous water depth with dry/wet distinction."""
        fig, ax = plt.subplots(figsize=(8, 6))
        h = state.h
        # Create a masked array to hide dry cells or use a specific color
        masked_h = np.ma.masked_where(h <= self.h_dry, h)

        im = ax.imshow(
            masked_h,
            extent=[0, state.z.shape[1], 0, state.z.shape[0]],
            origin="lower",
            cmap="Blues",
            vmin=0,
        )
        ax.set_facecolor("#f0f0f0")  # Light grey for dry land
        ax.set_title(f"{title} at T={state.time:.2f}s")
        ax.set_xlabel("X Grid Index")
        ax.set_ylabel("Y Grid Index")
        fig.colorbar(im, ax=ax, label="Depth (m)")
        return self._finalize_figure(fig, save_path)

    def plot_velocity_magnitude(
        self,
        sim: ShallowWaterSimulator,
        title: str = "Velocity Magnitude",
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """Visualizes velocity magnitude |u|."""
        u, v, _ = sim.velocity
        speed = np.sqrt(u**2 + v**2)

        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(speed, origin="lower", cmap="YlOrRd", vmin=0)
        ax.set_title(f"{title} (Max: {np.max(speed):.4f} m/s)")
        fig.colorbar(im, ax=ax, label="Speed (m/s)")
        return self._finalize_figure(fig, save_path)

    def compute_metrics(
        self, state: SimulationState, config: SimulationConfig
    ) -> Dict[str, Any]:
        """Calculates binary flood extent and total flooded area."""
        h = state.h
        flood_mask = h > self.h_dry
        flooded_cells = np.sum(flood_mask)
        dx = config.Lx / config.Nx
        dy = config.Ly / config.Ny
        flooded_area = flooded_cells * dx * dy

        return {
            "flooded_cells": int(flooded_cells),
            "flooded_area_m2": float(flooded_area),
            "flood_mask": flood_mask,
        }

    def plot_flood_extent(
        self,
        state: SimulationState,
        config: SimulationConfig,
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """Renders a binary map of flooded vs dry regions."""
        metrics = self.compute_metrics(state, config)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.imshow(metrics["flood_mask"], origin="lower", cmap="binary_r")
        ax.set_title(f"Flood Extent (Area: {metrics['flooded_area_m2']:.2f} m2)")
        return self._finalize_figure(fig, save_path)

    def plot_temporal_depth(
        self, diag: DiagnosticsReport, save_path: Optional[str] = None
    ) -> plt.Figure:
        """Generates a multi-panel plot for conservation and stability metrics."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

        ax1.plot(diag.timestamps, diag.total_mass, "b-o", markersize=3, label="Total Mass")
        ax1.set_ylabel("Integrated Mass (m3)")
        ax1.set_title(f"Simulation Integrity Trace: {diag.name}")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.plot(
            diag.timestamps, diag.max_velocity, "r-s", markersize=3, label="Peak Velocity"
        )
        ax2.set_ylabel("Max Velocity (m/s)")
        ax2.set_xlabel("Simulation Time (s)")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._finalize_figure(fig, save_path)
