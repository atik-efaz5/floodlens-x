"""CFL timestep selection (notebook cell 146)."""

import numpy as np

# Notebook cell 140: dt_initial = 0.01 (global fallback used by cell 146)
dt_initial = 0.01


def calculate_dt_cfl(U_state, dx, dy, g, h_dry_threshold, C=0.9):
    h_vals = U_state[:,:,0]
    hu_vals = U_state[:,:,1]
    hv_vals = U_state[:,:,2]

    # Use safe division for u and v velocities
    u_vals = np.zeros_like(h_vals)
    v_vals = np.zeros_like(h_vals)
    wet_cells_h = h_vals > h_dry_threshold
    np.divide(hu_vals, h_vals, out=u_vals, where=wet_cells_h)
    np.divide(hv_vals, h_vals, out=v_vals, where=wet_cells_h)

    sqrt_gh = np.zeros_like(h_vals)
    wet_cells_gh = h_vals > h_dry_threshold # Use h_dry_threshold consistently
    np.sqrt(g * h_vals, out=sqrt_gh, where=wet_cells_gh)

    # Calculate maximum wave speeds in x and y directions across the domain
    max_speed_x = np.max(np.abs(u_vals) + sqrt_gh)
    max_speed_y = np.max(np.abs(v_vals) + sqrt_gh)

    # Calculate dt based on CFL condition
    dt_cfl = dt_initial # Fallback if no motion (dt_initial needs to be a global or passed parameter)
    if max_speed_x > 1e-12 and max_speed_y > 1e-12:
        dt_cfl = C * min(dx / max_speed_x, dy / max_speed_y)
    elif max_speed_x > 1e-12: # Only x-direction speed is significant
        dt_cfl = C * (dx / max_speed_x)
    elif max_speed_y > 1e-12: # Only y-direction speed is significant
        dt_cfl = C * (dy / max_speed_y)

    # Calculate CFL number for diagnosis
    # Avoid division by zero if dt_cfl is zero or max_speeds are zero
    cfl_x = np.where(max_speed_x > 1e-12, dt_cfl * max_speed_x / dx, 0.0)
    cfl_y = np.where(max_speed_y > 1e-12, dt_cfl * max_speed_y / dy, 0.0)

    min_cfl = np.min(np.where(wet_cells_h, cfl_x, np.inf)) # Only consider wet cells for min CFL
    max_cfl = np.max(np.where(wet_cells_h, cfl_x, 0.0)) # Only consider wet cells for max CFL
    # For 2D, CFL is typically max(cfl_x, cfl_y)
    min_cfl = min(min_cfl, np.min(np.where(wet_cells_h, cfl_y, np.inf)))
    max_cfl = max(max_cfl, np.max(np.where(wet_cells_h, cfl_y, 0.0)))

    return dt_cfl, min_cfl, max_cfl
