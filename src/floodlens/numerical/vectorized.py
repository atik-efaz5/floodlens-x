import numpy as np


def vectorized_hydrostatic_reconstruction_x(
    U_pad: np.ndarray, z_pad: np.ndarray, h_dry_threshold: float = 1e-4
):
    """
    Vectorized hydrostatic reconstruction across all X-interfaces.
    U_pad shape: (Nx+2, Ny+2, 3), z_pad shape: (Nx+2, Ny+2)
    Interfaces: i = 0 to Nx (between pad[i] and pad[i+1])
    """
    UL = U_pad[:-1, 1:-1, :].copy()
    UR = U_pad[1:, 1:-1, :].copy()
    zL = z_pad[:-1, 1:-1]
    zR = z_pad[1:, 1:-1]

    z_int = np.maximum(zL, zR)
    etaL = zL + UL[:, :, 0]
    etaR = zR + UR[:, :, 0]

    hL_star = np.maximum(0.0, etaL - z_int)
    hR_star = np.maximum(0.0, etaR - z_int)

    maskL_mom = (UL[:, :, 0] > h_dry_threshold) & (hL_star > h_dry_threshold)
    maskR_mom = (UR[:, :, 0] > h_dry_threshold) & (hR_star > h_dry_threshold)

    UL_star = np.zeros_like(UL)
    UL_star[:, :, 0] = hL_star
    UL_star[:, :, 1] = np.where(
        maskL_mom, UL[:, :, 1] * (hL_star / UL[:, :, 0]), 0.0
    )
    UL_star[:, :, 2] = np.where(
        maskL_mom, UL[:, :, 2] * (hL_star / UL[:, :, 0]), 0.0
    )

    UR_star = np.zeros_like(UR)
    UR_star[:, :, 0] = hR_star
    UR_star[:, :, 1] = np.where(
        maskR_mom, UR[:, :, 1] * (hR_star / UR[:, :, 0]), 0.0
    )
    UR_star[:, :, 2] = np.where(
        maskR_mom, UR[:, :, 2] * (hR_star / UR[:, :, 0]), 0.0
    )

    return UL_star, UR_star, z_int


def vectorized_hydrostatic_reconstruction_y(
    U_pad: np.ndarray, z_pad: np.ndarray, h_dry_threshold: float = 1e-4
):
    """
    Vectorized hydrostatic reconstruction across all Y-interfaces.
    Interfaces: j = 0 to Ny (between pad[:, j] and pad[:, j+1])
    """
    UL = U_pad[1:-1, :-1, :].copy()
    UR = U_pad[1:-1, 1:, :].copy()
    zL = z_pad[1:-1, :-1]
    zR = z_pad[1:-1, 1:]

    z_int = np.maximum(zL, zR)
    etaL = zL + UL[:, :, 0]
    etaR = zR + UR[:, :, 0]

    hL_star = np.maximum(0.0, etaL - z_int)
    hR_star = np.maximum(0.0, etaR - z_int)

    maskL_mom = (UL[:, :, 0] > h_dry_threshold) & (hL_star > h_dry_threshold)
    maskR_mom = (UR[:, :, 0] > h_dry_threshold) & (hR_star > h_dry_threshold)

    UL_star = np.zeros_like(UL)
    UL_star[:, :, 0] = hL_star
    UL_star[:, :, 1] = np.where(
        maskL_mom, UL[:, :, 1] * (hL_star / UL[:, :, 0]), 0.0
    )
    UL_star[:, :, 2] = np.where(
        maskL_mom, UL[:, :, 2] * (hL_star / UL[:, :, 0]), 0.0
    )

    UR_star = np.zeros_like(UR)
    UR_star[:, :, 0] = hR_star
    UR_star[:, :, 1] = np.where(
        maskR_mom, UR[:, :, 1] * (hR_star / UR[:, :, 0]), 0.0
    )
    UR_star[:, :, 2] = np.where(
        maskR_mom, UR[:, :, 2] * (hR_star / UR[:, :, 0]), 0.0
    )

    return UL_star, UR_star, z_int


def vectorized_rusanov_flux_x(
    UL: np.ndarray, UR: np.ndarray, g: float = 9.81, h_dry_threshold: float = 1e-4
):
    """Vectorized Rusanov flux in X-direction."""
    hL, huL, hvL = UL[:, :, 0], UL[:, :, 1], UL[:, :, 2]
    hR, huR, hvR = UR[:, :, 0], UR[:, :, 1], UR[:, :, 2]

    maskL = hL > h_dry_threshold
    uL = np.zeros_like(hL)
    vL = np.zeros_like(hL)
    uL[maskL] = huL[maskL] / hL[maskL]
    vL[maskL] = hvL[maskL] / hL[maskL]

    maskR = hR > h_dry_threshold
    uR = np.zeros_like(hR)
    vR = np.zeros_like(hR)
    uR[maskR] = huR[maskR] / hR[maskR]
    vR[maskR] = hvR[maskR] / hR[maskR]

    FL = np.zeros_like(UL)
    FL[:, :, 0] = huL
    FL[:, :, 1] = huL * uL + 0.5 * g * (hL**2)
    FL[:, :, 2] = huL * vL

    FR = np.zeros_like(UR)
    FR[:, :, 0] = huR
    FR[:, :, 1] = huR * uR + 0.5 * g * (hR**2)
    FR[:, :, 2] = huR * vR

    sL = np.where(maskL, np.abs(uL) + np.sqrt(g * np.maximum(hL, 0.0)), 0.0)
    sR = np.where(maskR, np.abs(uR) + np.sqrt(g * np.maximum(hR, 0.0)), 0.0)
    s_max = np.maximum(sL, sR)[:, :, np.newaxis]

    return 0.5 * (FL + FR) - 0.5 * s_max * (UR - UL)


def vectorized_rusanov_flux_y(
    UL: np.ndarray, UR: np.ndarray, g: float = 9.81, h_dry_threshold: float = 1e-4
):
    """Vectorized Rusanov flux in Y-direction."""
    hL, huL, hvL = UL[:, :, 0], UL[:, :, 1], UL[:, :, 2]
    hR, huR, hvR = UR[:, :, 0], UR[:, :, 1], UR[:, :, 2]

    maskL = hL > h_dry_threshold
    uL = np.zeros_like(hL)
    vL = np.zeros_like(hL)
    uL[maskL] = huL[maskL] / hL[maskL]
    vL[maskL] = hvL[maskL] / hL[maskL]

    maskR = hR > h_dry_threshold
    uR = np.zeros_like(hR)
    vR = np.zeros_like(hR)
    uR[maskR] = huR[maskR] / hR[maskR]
    vR[maskR] = hvR[maskR] / hR[maskR]

    GL = np.zeros_like(UL)
    GL[:, :, 0] = hvL
    GL[:, :, 1] = hvL * uL
    GL[:, :, 2] = hvL * vL + 0.5 * g * (hL**2)

    GR = np.zeros_like(UR)
    GR[:, :, 0] = hvR
    GR[:, :, 1] = hvR * uR
    GR[:, :, 2] = hvR * vR + 0.5 * g * (hR**2)

    sL = np.where(maskL, np.abs(vL) + np.sqrt(g * np.maximum(hL, 0.0)), 0.0)
    sR = np.where(maskR, np.abs(vR) + np.sqrt(g * np.maximum(hR, 0.0)), 0.0)
    s_max = np.maximum(sL, sR)[:, :, np.newaxis]

    return 0.5 * (GL + GR) - 0.5 * s_max * (UR - UL)


def vectorized_bed_slope_source_terms(U_state, z_field, dx, dy, g):
    """Vectorized bed-slope source terms matching scalar kernel logic."""
    h = U_state[:, :, 0]
    wse = h + z_field
    source_terms = np.zeros_like(U_state)

    z_left = np.empty_like(z_field)
    z_left[:, 0] = z_field[:, 0]
    z_left[:, 1:] = z_field[:, :-1]

    z_right = np.empty_like(z_field)
    z_right[:, -1] = z_field[:, -1]
    z_right[:, :-1] = z_field[:, 1:]

    z_int_left = np.maximum(z_field, z_left)
    z_int_right = np.maximum(z_field, z_right)
    h_star_left = np.maximum(0.0, wse - z_int_left)
    h_star_right = np.maximum(0.0, wse - z_int_right)
    source_terms[:, :, 1] = -0.5 * g * (h_star_left**2 - h_star_right**2) / dx

    z_bottom = np.empty_like(z_field)
    z_bottom[0, :] = z_field[0, :]
    z_bottom[1:, :] = z_field[:-1, :]

    z_top = np.empty_like(z_field)
    z_top[-1, :] = z_field[-1, :]
    z_top[:-1, :] = z_field[1:, :]

    z_int_bottom = np.maximum(z_field, z_bottom)
    z_int_top = np.maximum(z_field, z_top)
    h_star_bottom = np.maximum(0.0, wse - z_int_bottom)
    h_star_top = np.maximum(0.0, wse - z_int_top)
    source_terms[:, :, 2] = -0.5 * g * (h_star_bottom**2 - h_star_top**2) / dy

    return source_terms


def vectorized_manning_source_terms(U_state, manning_n_field, g, h_dry_threshold):
    """Vectorized Manning friction source terms."""
    h = U_state[:, :, 0]
    hu = U_state[:, :, 1]
    hv = U_state[:, :, 2]
    source = np.zeros_like(U_state)

    wet = h > h_dry_threshold
    u = np.zeros_like(h)
    v = np.zeros_like(h)
    np.divide(hu, h, out=u, where=wet)
    np.divide(hv, h, out=v, where=wet)

    speed = np.sqrt(u**2 + v**2)
    f_coeff = np.zeros_like(h)
    np.divide(manning_n_field**2 * g * speed, h ** (1 / 3), out=f_coeff, where=wet)

    source[:, :, 1] = -f_coeff * u
    source[:, :, 2] = -f_coeff * v
    return source
