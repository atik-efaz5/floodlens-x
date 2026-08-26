"""Sunamganj extreme flood hindcast simulation script."""

import argparse
import sys
from pathlib import Path

import numpy as np

from floodlens.application.dem_manager import DEMManager, GeoTIFFMetadata
from floodlens.application.service import SimulationService
from floodlens.core.config import SimulationConfig
from floodlens.visualization.layer import VisualizationLayer


def generate_sunamganj_synthetic_dem(
    nx: int = 100, ny: int = 100, lx: float = 10000.0, ly: float = 10000.0
):
    """
    Generate synthetic Sunamganj-like basin topography.

    Features:
    - Low-lying haor depression in the south/center (2-4 m elevation)
    - Foothills/elevated terrain to the north (15-35 m elevation)
    - Main river drainage corridor running North to South

    Returns:
        Tuple of (elevation_array, GeoTIFFMetadata)
    """
    x = np.linspace(0, lx, nx)
    y = np.linspace(0, ly, ny)
    X, Y = np.meshgrid(x, y, indexing="ij")

    # North-to-south elevation slope
    z_regional = 30.0 * (1.0 - Y / ly) ** 1.5 + 2.0

    # Meandering channel depression
    channel_center = lx * (0.5 + 0.15 * np.sin(2 * np.pi * Y / ly))
    channel_depth = 4.0 * np.exp(-((X - channel_center) ** 2) / (2 * (lx * 0.08) ** 2))
    z = np.maximum(1.0, z_regional - channel_depth)

    # Local haor bowl in the southern section
    haor_bowl = 2.5 * np.exp(
        -((X - lx * 0.45) ** 2 + (Y - ly * 0.25) ** 2) / (2 * (lx * 0.15) ** 2)
    )
    z = np.maximum(0.8, z - haor_bowl)

    metadata = GeoTIFFMetadata(
        bounds_west=91.20,
        bounds_south=24.80,
        bounds_east=91.50,
        bounds_north=25.10,
        crs="EPSG:4326",
    )

    return z.astype(np.float64), metadata


def run_hindcast(output_dir: str = "./outputs/sunamganj_run"):
    """
    Execute Sunamganj extreme flood hindcast simulation.

    Args:
        output_dir: Target directory for outputs
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    nx, ny = 120, 120
    lx, ly = 12000.0, 12000.0

    print(
        f"[*] Initializing Sunamganj Basin Topography ({nx}x{ny}, "
        f"domain: {lx/1e3:.1f}km x {ly/1e3:.1f}km)..."
    )
    z, metadata = generate_sunamganj_synthetic_dem(nx=nx, ny=ny, lx=lx, ly=ly)

    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=lx,
        Ly=ly,
        T_end=30.0,
        CFL=0.75,
        manning_n=0.035,
        h_dry_threshold=1e-3,
        boundary_condition="transmissive",
    )

    print("[*] Configuring Hydrodynamic Simulation Engine...")

    service = SimulationService(config)

    rainfall_rate = 1.667e-5
    print(
        f"[*] Running extreme rainfall scenario ({rainfall_rate * 3600 * 1000:.1f} mm/hr) "
        f"for {config.T_end}s..."
    )

    result = service.run_scenario(
        dem=z, rainfall_rate=rainfall_rate, steps=25, track_progress=False
    )

    if not result.success:
        print("[!] Simulation encountered a numerical failure.")
        sys.exit(1)

    print("[+] Simulation completed successfully.")

    viz = VisualizationLayer()
    metrics = viz.compute_metrics(result.final_state, config)
    dx = lx / nx
    dy = ly / ny
    inundated_cells = np.sum(result.final_state.h > 0.05)
    inundated_km2 = (inundated_cells * dx * dy) / 1e6
    max_depth = np.max(result.final_state.h)

    print("\n================ Hindcast Results ================")
    print(f"  Total Inundated Area (>5cm) : {inundated_km2:.2f} km²")
    print(f"  Maximum Flood Depth         : {max_depth:.3f} m")
    print(f"  Mean Water Depth            : {np.mean(result.final_state.h):.3f} m")
    print("==================================================\n")

    depth_plot_path = out_path / "sunamganj_flood_depth.png"
    viz.plot_instantaneous_depth(result.final_state, z, save_path=str(depth_plot_path))
    print(f"[+] Saved flood depth map to: {depth_plot_path}")

    npz_path = out_path / "sunamganj_state.npz"
    np.savez_compressed(
        npz_path, U=result.final_state.U, z=z, time=result.final_state.time
    )
    print(f"[+] Saved state archive to: {npz_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sunamganj Extreme Flood Hindcast Runner"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./outputs/sunamganj_run",
        help="Target output directory",
    )
    args = parser.parse_args()
    run_hindcast(output_dir=args.output_dir)
