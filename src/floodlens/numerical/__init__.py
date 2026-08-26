"""Validated numerical kernel (notebook cells 343, 146, 301)."""

from floodlens.numerical.boundary import apply_ghost_cells
from floodlens.numerical.flux import F, G, max_wave_speed_x, max_wave_speed_y
from floodlens.numerical.reconstruction import hydrostatic_reconstruction
from floodlens.numerical.riemann import rusanov_flux
from floodlens.numerical.sources import (
    calculate_bed_slope_source_terms,
    calculate_manning_source_terms,
)
from floodlens.numerical.timestep import DEFAULT_DT_FALLBACK, calculate_dt_cfl, dt_initial
from floodlens.numerical.timestepper import run_shallow_water_simulation
from floodlens.numerical.vectorized import (
    vectorized_hydrostatic_reconstruction_x,
    vectorized_hydrostatic_reconstruction_y,
    vectorized_rusanov_flux_x,
    vectorized_rusanov_flux_y,
)

__all__ = [
    "apply_ghost_cells",
    "vectorized_hydrostatic_reconstruction_x",
    "vectorized_hydrostatic_reconstruction_y",
    "vectorized_rusanov_flux_x",
    "vectorized_rusanov_flux_y",
    "F",
    "G",
    "max_wave_speed_x",
    "max_wave_speed_y",
    "hydrostatic_reconstruction",
    "rusanov_flux",
    "calculate_bed_slope_source_terms",
    "calculate_manning_source_terms",
    "calculate_dt_cfl",
    "DEFAULT_DT_FALLBACK",
    "dt_initial",
    "run_shallow_water_simulation",
]
