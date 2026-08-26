"""CLI entrypoint tests."""

import numpy as np
import pytest

from floodlens.cli import main, parse_args


def test_cli_argument_parsing():
    """Parse and validate CLI arguments."""
    args = parse_args(
        [
            "--nx",
            "20",
            "--ny",
            "20",
            "--t-end",
            "5.0",
            "--cfl",
            "0.5",
            "--bc",
            "transmissive",
        ]
    )
    assert args.nx == 20
    assert args.ny == 20
    assert args.t_end == 5.0
    assert args.cfl == 0.5
    assert args.bc == "transmissive"


def test_cli_default_arguments():
    """CLI arguments have sensible defaults."""
    args = parse_args([])
    assert args.nx == 50
    assert args.ny == 50
    assert args.lx == 1000.0
    assert args.ly == 1000.0
    assert args.t_end == 10.0
    assert args.cfl == 0.8
    assert args.manning_n == 0.03
    assert args.rainfall == 0.0
    assert args.bc == "reflective"


def test_cli_execution_and_file_export(tmp_path):
    """Execute CLI and verify output files."""
    out_dir = tmp_path / "cli_out"
    exit_code = main(
        [
            "--nx",
            "15",
            "--ny",
            "15",
            "--t-end",
            "1.0",
            "--output-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "flood_depth_map.png").exists()
    assert (out_dir / "simulation_result.npz").exists()

    data = np.load(out_dir / "simulation_result.npz")
    assert "U" in data
    assert "z" in data
    assert data["U"].shape == (15, 15, 3)
    assert data["z"].shape == (15, 15)
    assert "time" in data
