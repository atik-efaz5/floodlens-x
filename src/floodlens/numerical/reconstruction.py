"""Hydrostatic reconstruction at cell interfaces (notebook cell 343)."""

import numpy as np


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
