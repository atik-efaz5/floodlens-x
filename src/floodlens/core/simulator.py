"""Shallow-water simulator API (notebook cells 525, 526, 514, 533)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Optional, Tuple

import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.diagnostics import DiagnosticsReport
from floodlens.core.grid import GridData
from floodlens.core.result import SimulationResult
from floodlens.core.state import SimulationState
from floodlens.numerical.timestep import calculate_dt_cfl
from floodlens.numerical.timestepper import run_shallow_water_simulation


def _resolve_bc_type(config: SimulationConfig) -> str:
    bc = config.boundary_condition
    return bc.value if hasattr(bc, "value") else str(bc)


class ShallowWaterSimulator:
    """High-level API for the FloodLens-X solver."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        dx = np.float64(config.Lx / config.Nx)
        dy = np.float64(config.Ly / config.Ny)
        x = np.linspace(0.5 * dx, config.Lx - 0.5 * dx, config.Nx, dtype=np.float64)
        y = np.linspace(0.5 * dy, config.Ly - 0.5 * dy, config.Ny, dtype=np.float64)
        X, Y = np.meshgrid(x, y)
        self._grid = GridData(dx=dx, dy=dy, X=X, Y=Y)
        self._state: Optional[SimulationState] = None

    @property
    def grid(self) -> GridData:
        return self._grid

    def set_initial_conditions(self, z: np.ndarray, U_initial: np.ndarray):
        expected_shape = (self.config.Ny, self.config.Nx)
        if z.shape != expected_shape:
            raise ValueError(f"Bed elevation shape {z.shape} != {expected_shape}")
        if U_initial.shape != (self.config.Ny, self.config.Nx, 3):
            raise ValueError(
                f"State vector shape {U_initial.shape} != {(self.config.Ny, self.config.Nx, 3)}"
            )
        self._state = SimulationState(
            U=U_initial.copy(),
            z=z.copy(),
            time=np.float64(0.0),
            iteration=0,
        )

    def run(
        self,
        rainfall_rate: float = 0.0,
        infiltration_rate: float = 0.0,
        manning_n: Optional[np.ndarray] = None,
    ):
        if self._state is None:
            raise RuntimeError(
                "Simulator state not initialized. Call set_initial_conditions() first."
            )

        manning_field = manning_n if manning_n is not None else np.zeros_like(self._state.z)

        _, U_next, _ = run_shallow_water_simulation(
            U_initial=self._state.U,
            z_field=self._state.z,
            manning_n_field=manning_field,
            rainfall_rate_mps_sim=rainfall_rate,
            infiltration_rate_mps_sim=infiltration_rate,
            inflow_boundary_params={"location": "none"},
            T_end_sim=self.config.T_end,
            dt_initial_sim=self.config.dt_initial,
            Lx_sim=self.config.Lx,
            Ly_sim=self.config.Ly,
            dx_sim=self._grid.dx,
            dy_sim=self._grid.dy,
            Nx_sim=self.config.Nx,
            Ny_sim=self.config.Ny,
            g=self.config.g,
            h_dry_threshold=self.config.h_dry_threshold,
            cfl_sim=self.config.CFL,
            bc_type=_resolve_bc_type(self.config),
            store_frames=False,
        )

        self._state.U = U_next
        self._state.time += self.config.T_end
        self._state.iteration += 1

    def get_state(self) -> SimulationState:
        if self._state is None:
            raise RuntimeError("State is not initialized.")
        return self._state

    def get_result(self) -> SimulationResult:
        state = self._state
        if state is None:
            raise RuntimeError("No state available.")

        mass = np.sum(state.h) * self._grid.dx * self._grid.dy
        mom = np.max(np.sqrt(state.hu**2 + state.hv**2))

        return SimulationResult(
            name=self.config.name,
            final_state=state,
            total_mass=float(mass),
            peak_momentum=float(mom),
        )

    def get_grid(self) -> GridData:
        return self.grid

    def compute_total_volume(self) -> float:
        """Calculates the integrated water volume in the domain."""
        return float(np.sum(self.get_state().h) * self._grid.dx * self._grid.dy)

    @property
    def velocity(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (u, v, speed) with dry-cell protection."""
        state = self.get_state()
        h = state.h
        h_dry = self.config.h_dry_threshold
        with np.errstate(divide="ignore", invalid="ignore"):
            u = np.where(h > h_dry, state.hu / h, 0.0)
            v = np.where(h > h_dry, state.hv / h, 0.0)
        speed = np.sqrt(u**2 + v**2)
        return u, v, speed

    def save_simulation(self, filepath: str):
        if self._state is None:
            raise RuntimeError("No simulation state to save.")

        config_json = json.dumps(asdict(self.config))
        np.savez_compressed(
            filepath,
            U=self._state.U,
            z=self._state.z,
            metadata=np.array(
                [self._state.time, self._state.iteration], dtype=np.float64
            ),
            config_json=config_json,
        )

    @staticmethod
    def load_simulation(filepath: str) -> ShallowWaterSimulator:
        data = np.load(filepath)
        config_dict = json.loads(str(data["config_json"]))
        config = SimulationConfig(**config_dict)

        simulator = ShallowWaterSimulator(config)
        simulator._state = SimulationState(
            U=data["U"],
            z=data["z"],
            time=np.float64(data["metadata"][0]),
            iteration=int(data["metadata"][1]),
        )
        return simulator


class ShallowWaterSimulatorWithDiagnostics(ShallowWaterSimulator):
    """Extended simulator with production-quality diagnostic hooks."""

    def __init__(self, config: SimulationConfig):
        super().__init__(config)
        self.diagnostics = DiagnosticsReport(name=config.name, config=asdict(config))

    def run(
        self,
        rainfall_rate: float = 0.0,
        infiltration_rate: float = 0.0,
        manning_n: Optional[np.ndarray] = None,
    ) -> DiagnosticsReport:
        if self._state is None:
            raise RuntimeError("Initial conditions not set.")

        t_start = time.time()
        manning_field = manning_n if manning_n is not None else np.zeros_like(self._state.z)

        if self._state.iteration == 0:
            self._record_diagnostics(rainfall_rate, infiltration_rate, manning_field)

        _, U_next, _ = run_shallow_water_simulation(
            self._state.U,
            self._state.z,
            manning_field,
            rainfall_rate,
            infiltration_rate,
            {"location": "none"},
            self.config.T_end,
            self.config.dt_initial,
            self.config.Lx,
            self.config.Ly,
            self._grid.dx,
            self._grid.dy,
            self.config.Nx,
            self.config.Ny,
            self.config.g,
            self.config.h_dry_threshold,
            cfl_sim=self.config.CFL,
            bc_type=_resolve_bc_type(self.config),
            store_frames=False,
        )

        self._state.U = U_next
        self._state.time += self.config.T_end
        self._state.iteration += 1

        self.diagnostics.wall_time_s += time.time() - t_start
        self.diagnostics.total_iterations += 1
        self._record_diagnostics(rainfall_rate, infiltration_rate, manning_field)
        return self.diagnostics

    @classmethod
    def load_simulation(cls, filepath: str) -> ShallowWaterSimulatorWithDiagnostics:
        base = ShallowWaterSimulator.load_simulation(filepath)
        sim = cls(base.config)
        sim._state = base._state
        return sim

    def _record_diagnostics(self, rain, infil, manning):
        state = self._state
        h = state.h
        mass = np.sum(h) * self._grid.dx * self._grid.dy
        _, _, vel_mag = self.velocity

        self.diagnostics.timestamps.append(float(state.time))
        self.diagnostics.total_mass.append(float(mass))
        self.diagnostics.max_velocity.append(float(np.max(vel_mag)))
        self.diagnostics.min_h.append(float(np.min(h)))

        _, _, max_cfl = calculate_dt_cfl(
            state.U,
            self._grid.dx,
            self._grid.dy,
            self.config.g,
            self.config.h_dry_threshold,
            C=self.config.CFL,
            dt_fallback=self.config.dt_initial,
        )
        self.diagnostics.max_cfl.append(float(max_cfl))
