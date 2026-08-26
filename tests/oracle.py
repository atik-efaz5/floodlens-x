"""Standalone numerical oracle (verbatim notebook cells 343, 146, 301).

Independent reference implementation for Phase B regression tests.
"""

import numpy as np

# Notebook cell 140 / 146
dt_initial = 0.01


def F(U_vec, g, h_dry_threshold):
    h, hu, hv = U_vec[0], U_vec[1], U_vec[2]
    u = np.where(h > h_dry_threshold, hu / h, 0.0)
    v = np.where(h > h_dry_threshold, hv / h, 0.0)
    return np.array([
        hu,
        hu * u + 0.5 * g * h**2,
        hu * v
    ])


def G(U_vec, g, h_dry_threshold):
    h, hu, hv = U_vec[0], U_vec[1], U_vec[2]
    u = np.where(h > h_dry_threshold, hu / h, 0.0)
    v = np.where(h > h_dry_threshold, hv / h, 0.0)
    return np.array([
        hv,
        hv * u,
        hv * v + 0.5 * g * h**2
    ])


def max_wave_speed_x(U_vec, g, h_dry_threshold):
    h, hu, _ = U_vec[0], U_vec[1], U_vec[2]
    u = np.where(h > h_dry_threshold, hu / h, 0.0)
    return np.where(h > h_dry_threshold, np.abs(u) + np.sqrt(g * h), 0.0)


def max_wave_speed_y(U_vec, g, h_dry_threshold):
    h, _, hv = U_vec[0], U_vec[1], U_vec[2]
    v = np.where(h > h_dry_threshold, hv / h, 0.0)
    return np.where(h > h_dry_threshold, np.abs(v) + np.sqrt(g * h), 0.0)


def rusanov_flux(U_L, U_R, flux_func, wave_speed_func, g, h_dry_threshold):
    F_L = flux_func(U_L, g, h_dry_threshold)
    F_R = flux_func(U_R, g, h_dry_threshold)

    alpha_L = wave_speed_func(U_L, g, h_dry_threshold)
    alpha_R = wave_speed_func(U_R, g, h_dry_threshold)
    alpha = np.maximum(alpha_L, alpha_R)

    return 0.5 * (F_L + F_R - alpha * (U_R - U_L))


def hydrostatic_reconstruction(U_L_in, U_R_in, z_L, z_R, h_dry_threshold):
    z_int = np.maximum(z_L, z_R)
    U_L_out = U_L_in.copy()
    U_R_out = U_R_in.copy()

    h_L_star = np.maximum(0.0, U_L_in[0] + z_L - z_int)
    h_R_star = np.maximum(0.0, U_R_in[0] + z_R - z_int)

    U_L_out[0] = h_L_star
    U_R_out[0] = h_R_star

    if U_L_in[0] > h_dry_threshold and h_L_star > h_dry_threshold:
        U_L_out[1:] = U_L_in[1:] * (h_L_star / U_L_in[0])
    else:
        U_L_out[1:] = 0.0

    if U_R_in[0] > h_dry_threshold and h_R_star > h_dry_threshold:
        U_R_out[1:] = U_R_in[1:] * (h_R_star / U_R_in[0])
    else:
        U_R_out[1:] = 0.0

    return U_L_out, U_R_out


def calculate_bed_slope_source_terms(U_state, z_field, dx, dy, g):
    Ny, Nx = z_field.shape
    h = U_state[:,:,0]
    WSE = h + z_field
    Source_terms = np.zeros_like(U_state)

    for j in range(Ny):
        for i in range(Nx):
            z_L_neighbor = z_field[j, i-1] if i > 0 else z_field[j, i]
            z_int_L = np.maximum(z_field[j, i], z_L_neighbor)
            h_star_L = np.maximum(0.0, WSE[j, i] - z_int_L)

            z_R_neighbor = z_field[j, i+1] if i < Nx-1 else z_field[j, i]
            z_int_R = np.maximum(z_field[j, i], z_R_neighbor)
            h_star_R = np.maximum(0.0, WSE[j, i] - z_int_R)

            Source_terms[j, i, 1] = -0.5 * g * (h_star_L**2 - h_star_R**2) / dx

    for i in range(Nx):
        for j in range(Ny):
            z_B_neighbor = z_field[j-1, i] if j > 0 else z_field[j, i]
            z_int_B = np.maximum(z_field[j, i], z_B_neighbor)
            h_star_B = np.maximum(0.0, WSE[j, i] - z_int_B)

            z_T_neighbor = z_field[j+1, i] if j < Ny-1 else z_field[j, i]
            z_int_T = np.maximum(z_field[j, i], z_T_neighbor)
            h_star_T = np.maximum(0.0, WSE[j, i] - z_int_T)

            Source_terms[j, i, 2] = -0.5 * g * (h_star_B**2 - h_star_T**2) / dy

    return Source_terms


def calculate_manning_source_terms(U_state, manning_n_field, g, h_dry_threshold):
    h = U_state[:,:,0]
    hu = U_state[:,:,1]
    hv = U_state[:,:,2]
    S = np.zeros_like(U_state)

    wet = h > h_dry_threshold
    u = np.zeros_like(h)
    v = np.zeros_like(h)
    np.divide(hu, h, out=u, where=wet)
    np.divide(hv, h, out=v, where=wet)

    speed = np.sqrt(u**2 + v**2)
    f_coeff = np.zeros_like(h)
    np.divide(manning_n_field**2 * g * speed, h**(1/3), out=f_coeff, where=wet)

    S[:,:,1] = -f_coeff * u
    S[:,:,2] = -f_coeff * v
    return S


def calculate_dt_cfl(U_state, dx, dy, g, h_dry_threshold, C=0.9):
    h_vals = U_state[:,:,0]
    hu_vals = U_state[:,:,1]
    hv_vals = U_state[:,:,2]

    u_vals = np.zeros_like(h_vals)
    v_vals = np.zeros_like(h_vals)
    wet_cells_h = h_vals > h_dry_threshold
    np.divide(hu_vals, h_vals, out=u_vals, where=wet_cells_h)
    np.divide(hv_vals, h_vals, out=v_vals, where=wet_cells_h)

    sqrt_gh = np.zeros_like(h_vals)
    wet_cells_gh = h_vals > h_dry_threshold
    np.sqrt(g * h_vals, out=sqrt_gh, where=wet_cells_gh)

    max_speed_x = np.max(np.abs(u_vals) + sqrt_gh)
    max_speed_y = np.max(np.abs(v_vals) + sqrt_gh)

    dt_cfl = dt_initial
    if max_speed_x > 1e-12 and max_speed_y > 1e-12:
        dt_cfl = C * min(dx / max_speed_x, dy / max_speed_y)
    elif max_speed_x > 1e-12:
        dt_cfl = C * (dx / max_speed_x)
    elif max_speed_y > 1e-12:
        dt_cfl = C * (dy / max_speed_y)

    cfl_x = np.where(max_speed_x > 1e-12, dt_cfl * max_speed_x / dx, 0.0)
    cfl_y = np.where(max_speed_y > 1e-12, dt_cfl * max_speed_y / dy, 0.0)

    min_cfl = np.min(np.where(wet_cells_h, cfl_x, np.inf))
    max_cfl = np.max(np.where(wet_cells_h, cfl_x, 0.0))
    min_cfl = min(min_cfl, np.min(np.where(wet_cells_h, cfl_y, np.inf)))
    max_cfl = max(max_cfl, np.max(np.where(wet_cells_h, cfl_y, 0.0)))

    return dt_cfl, min_cfl, max_cfl


def run_shallow_water_simulation(
    U_initial, z_field, manning_n_field,
    rainfall_rate_mps_sim, infiltration_rate_mps_sim, inflow_boundary_params,
    T_end_sim, dt_initial_sim, Lx_sim, Ly_sim, dx_sim, dy_sim,
    Nx_sim, Ny_sim, g, h_dry_threshold,
    store_frames=True, frame_interval=10,
):
    U = U_initial.copy()
    current_time = 0.0
    iteration = 0
    frames = [U[:,:,0].copy()]
    initial_volume = np.sum(U[:,:,0]) * dx_sim * dy_sim

    while current_time < T_end_sim:
        dt, _, _ = calculate_dt_cfl(U, dx_sim, dy_sim, g, h_dry_threshold)
        if current_time + dt > T_end_sim:
            dt = T_end_sim - current_time

        F_flux = np.zeros((Ny_sim, Nx_sim + 1, 3))
        for j in range(Ny_sim):
            for i in range(Nx_sim - 1):
                U_L_rec, U_R_rec = hydrostatic_reconstruction(
                    U[j, i, :], U[j, i + 1, :], z_field[j, i], z_field[j, i + 1], h_dry_threshold)
                F_flux[j, i + 1, :] = rusanov_flux(
                    U_L_rec, U_R_rec, F, max_wave_speed_x, g, h_dry_threshold)

            z_wL = z_field[j, 0]
            U_ghL = np.array([U[j, 0, 0], -U[j, 0, 1], U[j, 0, 2]])
            L_r, R_r = hydrostatic_reconstruction(U_ghL, U[j, 0, :], z_wL, z_wL, h_dry_threshold)
            F_flux[j, 0, :] = rusanov_flux(L_r, R_r, F, max_wave_speed_x, g, h_dry_threshold)

            z_wR = z_field[j, -1]
            U_ghR = np.array([U[j, -1, 0], -U[j, -1, 1], U[j, -1, 2]])
            L_r, R_r = hydrostatic_reconstruction(U[j, -1, :], U_ghR, z_wR, z_wR, h_dry_threshold)
            F_flux[j, Nx_sim, :] = rusanov_flux(L_r, R_r, F, max_wave_speed_x, g, h_dry_threshold)

        G_flux = np.zeros((Ny_sim + 1, Nx_sim, 3))
        for i in range(Nx_sim):
            for j in range(Ny_sim - 1):
                U_L_rec, U_R_rec = hydrostatic_reconstruction(
                    U[j, i, :], U[j + 1, i, :], z_field[j, i], z_field[j + 1, i], h_dry_threshold)
                G_flux[j + 1, i, :] = rusanov_flux(
                    U_L_rec, U_R_rec, G, max_wave_speed_y, g, h_dry_threshold)

            z_wB = z_field[0, i]
            U_ghB = np.array([U[0, i, 0], U[0, i, 1], -U[0, i, 2]])
            L_r, R_r = hydrostatic_reconstruction(U_ghB, U[0, i, :], z_wB, z_wB, h_dry_threshold)
            G_flux[0, i, :] = rusanov_flux(L_r, R_r, G, max_wave_speed_y, g, h_dry_threshold)

            z_wT = z_field[-1, i]
            U_ghT = np.array([U[-1, i, 0], U[-1, i, 1], -U[-1, i, 2]])
            L_r, R_r = hydrostatic_reconstruction(U[-1, i, :], U_ghT, z_wT, z_wT, h_dry_threshold)
            G_flux[Ny_sim, i, :] = rusanov_flux(L_r, R_r, G, max_wave_speed_y, g, h_dry_threshold)

        S_bed = calculate_bed_slope_source_terms(U, z_field, dx_sim, dy_sim, g)
        S_manning = calculate_manning_source_terms(U, manning_n_field, g, h_dry_threshold)

        U += dt * (
            -(1 / dx_sim) * (F_flux[:, 1:, :] - F_flux[:, :-1, :])
            - (1 / dy_sim) * (G_flux[1:, :, :] - G_flux[:-1, :, :])
            + S_bed + S_manning
        )
        U[:,:,0] = np.maximum(U[:,:,0], 0.0)
        U[U[:,:,0] < h_dry_threshold, 1:] = 0.0

        current_time += dt
        iteration += 1
        if iteration % frame_interval == 0:
            frames.append(U[:,:,0].copy())
        if np.max(np.abs(U[:,:,1:])) > 50.0:
            break

    return frames, U, initial_volume


def advance_simulation(
    U_initial,
    z_field,
    manning_n_field,
    rainfall,
    infiltration,
    steps,
    g,
    h_dry,
    Lx,
    Ly,
    dx,
    dy,
    Nx,
    Ny,
):
    """Multi-step driver matching notebook Phase 11.0C gate (cell 530)."""
    U = U_initial.copy()
    for _ in range(steps):
        dt, _, _ = calculate_dt_cfl(U, dx, dy, g, h_dry)
        _, U, _ = run_shallow_water_simulation(
            U,
            z_field,
            manning_n_field,
            rainfall,
            infiltration,
            {"location": "none"},
            dt,
            dt,
            Lx,
            Ly,
            dx,
            dy,
            Nx,
            Ny,
            g,
            h_dry,
            False,
        )
    return U
