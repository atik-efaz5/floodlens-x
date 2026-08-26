"""Phase B API integration tests (NUMERICAL_CONTRACT Sections 4.2–4.3)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from floodlens.application import InputManager, SimulationService
from floodlens.core import (
    ShallowWaterSimulator,
    ShallowWaterSimulatorWithDiagnostics,
    SimulationConfig,
)
from floodlens.numerical.timestepper import run_shallow_water_simulation
from floodlens.visualization import VisualizationLayer

EQUIV_TOL = 1e-15


def _parabolic_bowl_setup_phase_11d():
    """Phase 11.0D diagnostic transparency scenario (50x50 parabolic bowl)."""
    nx = ny = 50
    lx = ly = 10.0
    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=lx,
        Ly=ly,
        T_end=0.1,
        name="Diagnostic_Validation",
    )
    dx = lx / nx
    dy = ly / ny
    x = np.linspace(0.5 * dx, lx - 0.5 * dx, nx, dtype=np.float64)
    y = np.linspace(0.5 * dy, ly - 0.5 * dy, ny, dtype=np.float64)
    x_grid, y_grid = np.meshgrid(x, y)
    z = 0.02 * ((x_grid - 5.0) ** 2 + (y_grid - 5.0) ** 2)
    u_init = np.zeros((ny, nx, 3), dtype=np.float64)
    u_init[:, :, 0] = np.maximum(0.0, 1.5 - z)
    return config, z, u_init, dx, dy


class TestDiagnosticTransparency:
    """Contract Section 4.2 / Phase 11.0D diagnostic transparency."""

    def test_final_state_matches_oracle(self):
        config, z, u_init, dx, dy = _parabolic_bowl_setup_phase_11d()

        sim = ShallowWaterSimulatorWithDiagnostics(config)
        sim.set_initial_conditions(z, u_init)
        sim.run()

        _, u_oracle_final, _ = run_shallow_water_simulation(
            u_init.copy(),
            z,
            np.zeros_like(z),
            0.0,
            0.0,
            {"location": "none"},
            config.T_end,
            0.01,
            config.Lx,
            config.Ly,
            dx,
            dy,
            config.Nx,
            config.Ny,
            config.g,
            config.h_dry_threshold,
            False,
        )

        max_diff = float(np.max(np.abs(sim.get_state().U - u_oracle_final)))
        assert max_diff < EQUIV_TOL

    def test_diagnostics_report_populated(self):
        config, z, u_init, _, _ = _parabolic_bowl_setup_phase_11d()

        sim = ShallowWaterSimulatorWithDiagnostics(config)
        sim.set_initial_conditions(z, u_init)
        report = sim.run()

        assert report is sim.diagnostics
        assert report.total_iterations == 1
        assert len(report.timestamps) == 2
        assert len(report.total_mass) == 2
        assert len(report.max_velocity) == 2
        assert len(report.max_cfl) == 2
        assert len(report.min_h) == 2

        mass0, mass1 = report.total_mass[0], report.total_mass[-1]
        rel_mass_err = abs(mass1 - mass0) / mass0 if mass0 != 0 else 0.0
        assert rel_mass_err < EQUIV_TOL

        assert all(0.0 <= cfl <= 1.0 for cfl in report.max_cfl)
        assert report.max_velocity[0] >= 0.0
        assert report.min_h[0] >= 0.0


class TestPersistenceRoundTrip:
    """Contract Section 4.3 persistence round-trip."""

    @pytest.fixture
    def trained_simulator(self):
        config = SimulationConfig(Nx=20, Ny=20, Lx=10.0, Ly=10.0, T_end=0.05)
        sim = ShallowWaterSimulator(config)
        z = np.zeros((20, 20), dtype=np.float64)
        u_init = np.zeros((20, 20, 3), dtype=np.float64)
        u_init[:, :, 0] = 1.0
        sim.set_initial_conditions(z, u_init)
        for _ in range(5):
            sim.run()
        return sim

    def test_base_simulator_load_round_trip(self, trained_simulator, tmp_path):
        filepath = tmp_path / "sim.npz"
        trained_simulator.save_simulation(str(filepath))

        loaded = ShallowWaterSimulator.load_simulation(str(filepath))
        original = trained_simulator.get_state()
        restored = loaded.get_state()

        assert np.array_equal(restored.U, original.U)
        assert np.array_equal(restored.z, original.z)
        assert restored.time == original.time
        assert restored.iteration == original.iteration
        assert loaded.config == trained_simulator.config

    def test_diagnostics_simulator_load_round_trip(self, trained_simulator, tmp_path):
        filepath = tmp_path / "sim.npz"
        trained_simulator.save_simulation(str(filepath))

        loaded = ShallowWaterSimulatorWithDiagnostics.load_simulation(str(filepath))
        original = trained_simulator.get_state()
        restored = loaded.get_state()

        assert np.array_equal(restored.U, original.U)
        assert np.array_equal(restored.z, original.z)
        assert restored.time == original.time
        assert restored.iteration == original.iteration
        assert loaded.config == trained_simulator.config


class TestApplicationLayerWorkflow:
    """Application and visualization workflow smoke test."""

    def test_managed_scenario_and_metrics(self):
        config = SimulationConfig(
            Nx=30,
            Ny=30,
            Lx=20.0,
            Ly=20.0,
            T_end=0.05,
            name="App_Workflow",
        )
        z = InputManager.generate_parabolic_bowl(config)
        InputManager.validate_spatial_data(z, config.Nx, config.Ny)

        u_init = np.zeros((config.Ny, config.Nx, 3), dtype=np.float64)
        u_init[:, :, 0] = np.maximum(0.0, 1.2 - z)

        sim = ShallowWaterSimulatorWithDiagnostics(config)
        sim.set_initial_conditions(z, u_init)

        service = SimulationService(sim)
        service.run_scenario(steps=2)

        assert service.is_running is False
        assert len(service.progress.history) == 2

        viz = VisualizationLayer(h_dry_threshold=config.h_dry_threshold)
        metrics = viz.compute_metrics(sim.get_state(), config)

        assert metrics["flooded_cells"] >= 0
        assert metrics["flooded_area_m2"] >= 0.0
        assert metrics["flood_mask"].shape == (config.Ny, config.Nx)
