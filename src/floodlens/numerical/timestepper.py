"""Full 2D scalar shallow-water timestepper (notebook cell 301)."""

import numpy as np

from floodlens.numerical.boundary import apply_ghost_cells
from floodlens.numerical.flux import F, G, max_wave_speed_x, max_wave_speed_y
from floodlens.numerical.reconstruction import hydrostatic_reconstruction
from floodlens.numerical.riemann import rusanov_flux
from floodlens.numerical.sources import (
    calculate_bed_slope_source_terms,
    calculate_manning_source_terms,
)
from floodlens.numerical.timestep import calculate_dt_cfl


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

        # 1. COMPUTE FLUXES WITH WELL-BALANCED DISSIPATION
        F_flux = np.zeros((Ny_sim, Nx_sim + 1, 3))
        for j in range(Ny_sim):
            for i in range(Nx_sim - 1):
                U_L_rec, U_R_rec = hydrostatic_reconstruction(U[j,i,:], U[j,i+1,:], z_field[j,i], z_field[j,i+1], h_dry_threshold)
                F_flux[j, i+1, :] = rusanov_flux(U_L_rec, U_R_rec, F, max_wave_speed_x, g, h_dry_threshold)

            z_wL = z_pad[0, j + 1]
            U_ghL = U_pad[0, j + 1, :]
            L_r, R_r = hydrostatic_reconstruction(U_ghL, U[j,0,:], z_wL, z_field[j,0], h_dry_threshold)
            F_flux[j, 0, :] = rusanov_flux(L_r, R_r, F, max_wave_speed_x, g, h_dry_threshold)

            z_wR = z_pad[-1, j + 1]
            U_ghR = U_pad[-1, j + 1, :]
            L_r, R_r = hydrostatic_reconstruction(U[j,-1,:], U_ghR, z_field[j,-1], z_wR, h_dry_threshold)
            F_flux[j, Nx_sim, :] = rusanov_flux(L_r, R_r, F, max_wave_speed_x, g, h_dry_threshold)

        G_flux = np.zeros((Ny_sim + 1, Nx_sim, 3))
        for i in range(Nx_sim):
            for j in range(Ny_sim - 1):
                U_L_rec, U_R_rec = hydrostatic_reconstruction(U[j,i,:], U[j+1,i,:], z_field[j,i], z_field[j+1,i], h_dry_threshold)
                G_flux[j+1, i, :] = rusanov_flux(U_L_rec, U_R_rec, G, max_wave_speed_y, g, h_dry_threshold)

            z_wB = z_pad[i + 1, 0]
            U_ghB = U_pad[i + 1, 0, :]
            L_r, R_r = hydrostatic_reconstruction(U_ghB, U[0,i,:], z_wB, z_field[0,i], h_dry_threshold)
            G_flux[0, i, :] = rusanov_flux(L_r, R_r, G, max_wave_speed_y, g, h_dry_threshold)

            z_wT = z_pad[i + 1, -1]
            U_ghT = U_pad[i + 1, -1, :]
            L_r, R_r = hydrostatic_reconstruction(U[-1,i,:], U_ghT, z_field[-1,i], z_wT, h_dry_threshold)
            G_flux[Ny_sim, i, :] = rusanov_flux(L_r, R_r, G, max_wave_speed_y, g, h_dry_threshold)

        # 2. SOURCE TERMS & UPDATE
        S_bed = calculate_bed_slope_source_terms(U, z_field, dx_sim, dy_sim, g)
        S_manning = calculate_manning_source_terms(U, manning_n_field, g, h_dry_threshold)

        U += dt * (-(1/dx_sim)*(F_flux[:,1:,:] - F_flux[:,:-1,:]) - (1/dy_sim)*(G_flux[1:,:,:] - G_flux[:-1,:,:]) + S_bed + S_manning)
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
