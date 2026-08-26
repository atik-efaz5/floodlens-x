"""Multi-grid scaling benchmark suite for FloodLens-X."""

import time
from typing import Dict

import numpy as np

from floodlens.core.config import SimulationConfig
from floodlens.core.simulator import ShallowWaterSimulator


def benchmark_grid(nx: int, ny: int, num_runs: int = 3) -> Dict[str, float]:
    """
    Benchmark shallow-water solver throughput for a given grid dimension.

    Args:
        nx: Grid size in X
        ny: Grid size in Y
        num_runs: Number of simulation runs to average

    Returns:
        Dictionary with benchmark metrics
    """
    config = SimulationConfig(
        Nx=nx,
        Ny=ny,
        Lx=1000.0,
        Ly=1000.0,
        T_end=0.5,
        CFL=0.8,
        manning_n=0.03,
        boundary_condition="transmissive",
    )

    x = np.linspace(0, config.Lx, nx)
    y = np.linspace(0, config.Ly, ny)
    X, Y = np.meshgrid(x, y, indexing="ij")
    z = 0.005 * ((X - config.Lx / 2) ** 2 + (Y - config.Ly / 2) ** 2)

    times = []

    for _ in range(num_runs):
        sim = ShallowWaterSimulator(config)
        sim.set_initial_conditions(h_init=1.0, z=z)

        start = time.perf_counter()
        sim.run(rainfall_rate=0.0)
        elapsed = time.perf_counter() - start

        times.append(elapsed)

    avg_time = np.mean(times)
    total_cells = nx * ny
    cells_per_second = total_cells / avg_time

    return {
        "grid": f"{nx}x{ny}",
        "total_cells": total_cells,
        "num_runs": num_runs,
        "avg_duration_sec": avg_time,
        "min_duration_sec": np.min(times),
        "max_duration_sec": np.max(times),
        "cells_per_sec": cells_per_second,
    }


def run_benchmarks():
    """Execute multi-grid scaling benchmarks."""
    grids = [(50, 50), (100, 100), (150, 150)]

    print("\n" + "=" * 85)
    print(f"{'Grid':<12} | {'Cells':<10} | {'Avg Time (s)':<15} | {'Cells/sec':<15} | {'Speedup':<10}")
    print("=" * 85)

    baseline_cells_per_sec = None

    for nx, ny in grids:
        res = benchmark_grid(nx, ny, num_runs=3)
        cells_per_sec = res["cells_per_sec"]

        if baseline_cells_per_sec is None:
            baseline_cells_per_sec = cells_per_sec
            speedup = 1.0
        else:
            speedup = cells_per_sec / baseline_cells_per_sec

        print(
            f"{res['grid']:<12} | {res['total_cells']:<10} | {res['avg_duration_sec']:<15.4f} | "
            f"{res['cells_per_sec']:<15.1e} | {speedup:<10.2f}x"
        )

    print("=" * 85 + "\n")


if __name__ == "__main__":
    run_benchmarks()
