"""Physical flux functions and wave-speed estimators (notebook cell 343)."""

import numpy as np


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
