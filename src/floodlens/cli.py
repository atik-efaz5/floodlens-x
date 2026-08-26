"""Production CLI entrypoint for FloodLens-X."""

import argparse
import sys
from pathlib import Path

import numpy as np

from floodlens.application.service import SimulationService
from floodlens.core.config import SimulationConfig
from floodlens.visualization.layer import VisualizationLayer


def parse_args(args=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="floodlens",
        description="FloodLens 2D Hydrodynamic Flood Simulation Engine",
    )
    parser.add_argument("--nx", type=int, default=50, help="Grid points in X")
    parser.add_argument("--ny", type=int, default=50, help="Grid points in Y")
    parser.add_argument("--lx", type=float, default=1000.0, help="Domain length X (m)")
    parser.add_argument("--ly", type=float, default=1000.0, help="Domain length Y (m)")
    parser.add_argument("--t-end", type=float, default=10.0, help="Simulation duration (s)")
    parser.add_argument("--cfl", type=float, default=0.8, help="CFL safety coefficient")
    parser.add_argument(
        "--manning-n", type=float, default=0.03, help="Manning roughness coefficient"
    )
    parser.add_argument(
        "--rainfall", type=float, default=0.0, help="Uniform rainfall rate (m/s)"
    )
    parser.add_argument(
        "--bc",
        type=str,
        default="reflective",
        choices=["reflective", "transmissive"],
        help="Boundary condition",
    )
    parser.add_argument(
        "--output-dir", type=str, default="./output", help="Output directory for results"
    )
    return parser.parse_args(args)


def main(args=None):
    """Execute the CLI simulation workflow."""
    try:
        parsed = parse_args(args)
        out_dir = Path(parsed.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        config = SimulationConfig(
            Nx=parsed.nx,
            Ny=parsed.ny,
            Lx=parsed.lx,
            Ly=parsed.ly,
            T_end=parsed.t_end,
            CFL=parsed.cfl,
            manning_n=parsed.manning_n,
            boundary_condition=parsed.bc,
        )

        x = np.linspace(0, config.Lx, config.Nx)
        y = np.linspace(0, config.Ly, config.Ny)
        X, Y = np.meshgrid(x, y, indexing="ij")
        z = 0.01 * ((X - config.Lx / 2) ** 2 + (Y - config.Ly / 2) ** 2)

        service = SimulationService(config)
        result = service.run_scenario(
            dem=z, rainfall_rate=parsed.rainfall, steps=10, track_progress=False
        )

        viz = VisualizationLayer()
        plot_path = out_dir / "flood_depth_map.png"
        viz.plot_instantaneous_depth(result.final_state, z, save_path=str(plot_path))

        npz_path = out_dir / "simulation_result.npz"
        np.savez_compressed(
            npz_path,
            U=result.final_state.U,
            z=z,
            time=result.final_state.time,
        )

        print("Simulation completed successfully.")
        print(f"Results saved to: {out_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
