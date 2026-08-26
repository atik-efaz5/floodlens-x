"""Rusanov (local Lax-Friedrichs) Riemann solver (notebook cell 343)."""

import numpy as np


def rusanov_flux(U_L, U_R, flux_func, wave_speed_func, g, h_dry_threshold):
    F_L = flux_func(U_L, g, h_dry_threshold)
    F_R = flux_func(U_R, g, h_dry_threshold)

    alpha_L = wave_speed_func(U_L, g, h_dry_threshold)
    alpha_R = wave_speed_func(U_R, g, h_dry_threshold)
    alpha = np.maximum(alpha_L, alpha_R)

    return 0.5 * (F_L + F_R - alpha * (U_R - U_L))
