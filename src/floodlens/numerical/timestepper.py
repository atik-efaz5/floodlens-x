"""Full 2D scalar shallow-water timestepper (notebook cell 301)."""

import numpy as np

from floodlens.numerical.boundary import apply_ghost_cells
from floodlens.numerical.timestep import calculate_dt_cfl
from floodlens.numerical.vectorized import (
    vectorized_bed_slope_source_terms,
    vectorized_hydrostatic_reconstruction_x,
    vectorized_hydrostatic_reconstruction_y,
    vectorized_manning_source_terms,
    vectorized_rusanov_flux_x,
    vectorized_rusanov_flux_y,
)


def run_shallow_water_simulation(U_initial, z_field, manning_n_field, rainfall_rate_mps_sim, infiltration_rate_mps_sim, inflow_boundary_params, T_end_sim, dt_initial_sim, Lx_sim, Ly_sim, dx_sim, dy_sim, Nx_sim, Ny_sim, g, h_dry_threshold, store_frames=True, frame_interval=10, cfl_sim=0.9, bc_type="reflective"):
    U = U_initial.copy()
    current_time = 0.0
    iteration = 0
    frames = [U[:,:,0].copy()]
    initial_volume = np.sum(U[:,:,0]) * dx_sim * dy_sim

    while current_time < T_end_sim:
        dt, _, _ = calculate_dt_cfl(
            U,
            dx_sim,
            dy_sim,
            g,
            h_dry_threshold,
            C=cfl_sim,
            dt_fallback=dt_initial_sim,
        )
        if current_time + dt > T_end_sim: dt = T_end_sim - current_time

        U_xy = np.transpose(U, (1, 0, 2))
        z_xy = z_field.T
        U_pad, z_pad = apply_ghost_cells(U_xy, z_xy, bc_type=bc_type)

        UL_x, UR_x, _ = vectorized_hydrostatic_reconstruction_x(
            U_pad, z_pad, h_dry_threshold
        )
        F_x = vectorized_rusanov_flux_x(UL_x, UR_x, g, h_dry_threshold)

        UL_y, UR_y, _ = vectorized_hydrostatic_reconstruction_y(
            U_pad, z_pad, h_dry_threshold
        )
        G_y = vectorized_rusanov_flux_y(UL_y, UR_y, g, h_dry_threshold)

        dF_dx = np.transpose((F_x[1:, :, :] - F_x[:-1, :, :]) / dx_sim, (1, 0, 2))
        dG_dy = np.transpose((G_y[:, 1:, :] - G_y[:, :-1, :]) / dy_sim, (1, 0, 2))

        S_bed = vectorized_bed_slope_source_terms(U, z_field, dx_sim, dy_sim, g)
        S_manning = vectorized_manning_source_terms(
            U, manning_n_field, g, h_dry_threshold
        )

        U += dt * (-dF_dx - dG_dy + S_bed + S_manning)
        U[:,:,0] = np.maximum(U[:,:,0], 0.0)
        U[U[:,:,0] < h_dry_threshold, 1:] = 0.0

        net_source = (rainfall_rate_mps_sim - infiltration_rate_mps_sim) * dt
        U[:, :, 0] += net_source
        U[:, :, 0] = np.maximum(U[:, :, 0], 0.0)

        current_time += dt
        iteration += 1
        if iteration % frame_interval == 0: frames.append(U[:,:,0].copy())
        if np.max(np.abs(U[:,:,1:])) > 50.0:
            print(f"Stability limit exceeded at iter {iteration}")
            break

    return frames, U, initial_volume
