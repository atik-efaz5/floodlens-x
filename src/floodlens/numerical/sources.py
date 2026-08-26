"""Bed-slope and Manning friction source terms (notebook cell 343)."""

import numpy as np


def calculate_bed_slope_source_terms(U_state, z_field, dx, dy, g):
    Ny, Nx = z_field.shape
    h = U_state[:,:,0]
    WSE = h + z_field
    Source_terms = np.zeros_like(U_state)

    # X-direction (hu)
    for j in range(Ny):
        for i in range(Nx):
            z_L_neighbor = z_field[j, i-1] if i > 0 else z_field[j, i]
            z_int_L = np.maximum(z_field[j, i], z_L_neighbor)
            h_star_L = np.maximum(0.0, WSE[j, i] - z_int_L)

            z_R_neighbor = z_field[j, i+1] if i < Nx-1 else z_field[j, i]
            z_int_R = np.maximum(z_field[j, i], z_R_neighbor)
            h_star_R = np.maximum(0.0, WSE[j, i] - z_int_R)

            Source_terms[j, i, 1] = -0.5 * g * (h_star_L**2 - h_star_R**2) / dx

    # Y-direction (hv)
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
