"""Flood extent from depth. Threshold is documented and reused from Phase-2 flood_fraction."""

from __future__ import annotations

import numpy as np

FLOOD_DEPTH_THRESHOLD_M = 0.05


def extent_from_depth(depth: np.ndarray, dx: float, dy: float) -> dict:
    wet = np.asarray(depth, dtype=np.float64) > FLOOD_DEPTH_THRESHOLD_M
    fraction = float(np.mean(wet)) if wet.size else 0.0
    cell_area = float(dx) * float(dy)
    flooded_area_m2 = float(np.sum(wet)) * cell_area
    return {
        "threshold_m": FLOOD_DEPTH_THRESHOLD_M,
        "threshold_note": (
            "A cell is flooded when depth > 0.05 m, the same cutoff already used "
            "for flood_fraction in simulation jobs."
        ),
        "flood_fraction": fraction,
        "flooded_area_m2": flooded_area_m2,
        "flooded_area_km2": flooded_area_m2 / 1.0e6,
        "max_depth_m": float(np.max(depth)) if depth.size else 0.0,
        "wet_cells": int(np.sum(wet)),
        "polygon": None,
        "polygon_note": "NOT_COMPUTED unless a contour library is wired later.",
        "mask": wet.astype(np.uint8),
    }
