"""Spectral features of a camera image. Vector layout (74 values):
    0 peakiness (luma)   1 peakiness (chroma)   2-4 free-search template LCD (score, r_hat, theta_hat_deg)
    5-7 free-search template PenTile   8-71 signature (32 luma + 32 chroma)
    72-73 known-geometry template scores (LCD, PenTile) - only filled when (r, theta) are given."""
from functools import lru_cache
import numpy as np
from scipy.ndimage import maximum_filter

import config as C
from .colour import luma, chroma
from . import masks
from .theory import layout_harmonics, to_camera_freq, fold, harmonic_amplitudes
from .render import sigma_screen

N = C.OUT
_HANN = np.outer(np.hanning(N), np.hanning(N))
F_PEAK, F_CPEAK, F_TL, F_TP, F_SIG, F_KL, F_KP = 0, 1, 2, 5, 8, 72, 73
FEATURE_NAMES = (["peak", "chroma_peak", "tmpl_lcd", "tmpl_lcd_r", "tmpl_lcd_th", "tmpl_pent", "tmpl_pent_r", "tmpl_pent_th"]
                 + [f"sigY_{i}" for i in range(32)] + [f"sigC_{i}" for i in range(32)] + ["known_lcd", "known_pent"])


_RING = masks.RING.ravel()
_RING_COUNT = np.bincount(_RING)
_RING_START = np.r_[0, np.cumsum(_RING_COUNT)[:-1]]
_MED_LO = _RING_START + (_RING_COUNT - 1) // 2          # positions of the two middle elements inside each sorted ring
_MED_HI = _RING_START + _RING_COUNT // 2


def ring_medians(L):
    """Median of L inside every radial ring with one sort (identical to np.median per ring)."""
    order = np.lexsort((L, _RING))
    s = L[order]
    return 0.5 * (s[_MED_LO] + s[_MED_HI])


def detrended(gray):
    """Log spectrum with each radial ring's median removed (natural images ~ 1/f), then masked."""
    F = np.abs(np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * _HANN)))
    L = np.log(F + 1e-9).ravel()
    med = ring_medians(L)
    R = (L - med[_RING]).reshape(N, N)
    R[masks.MASK_ALL] = 0.0
    return R


def _top_mean(R, k=20):
    return float(np.sort(R.ravel())[-k:].mean())


# ---- signature pooling: 8 angle bins (0..pi) x 4 radius bins
_ANG = np.mod(np.arctan2(masks.FY, masks.FX), np.pi)
_RBIN = np.digitize(masks.RADIUS, [4, 19, 34, 49, 64]) - 1            # 0..3 inside [4, 64)
_ABIN = np.minimum((_ANG / (np.pi / 8)).astype(int), 7)
_BIN = np.where((_RBIN >= 0) & (_RBIN <= 3), _ABIN * 4 + _RBIN, -1)
_BIN_OK = _BIN >= 0


def signature(R):
    P = np.clip(R - 2.0, 0, None)
    return np.log1p(np.bincount(_BIN[_BIN_OK], weights=P[_BIN_OK], minlength=32))


# ---- template matching in the frequency domain
R_GRID = np.round(np.arange(0.20, 3.0001, 0.02), 4)
TH_GRID = np.deg2rad(np.arange(-8.0, 8.0001, 0.5))
_NPEAK = 12
_VALID_IDX = np.flatnonzero(masks.VALID.ravel())


@lru_cache(maxsize=None)
def template_tables(layout, sigma_cam=0.4):
    """For each (r_hat, theta_hat): rows/cols of the 12 strongest predicted unmasked peaks. Image independent."""
    H = layout_harmonics(layout)
    fx, fy = H["fx"], H["fy"]
    nr, nt = len(R_GRID), len(TH_GRID)
    rows_t = np.zeros((nr, nt, _NPEAK), np.int32)
    cols_t = np.zeros((nr, nt, _NPEAK), np.int32)
    for ir, r in enumerate(R_GRID):
        ss = sigma_screen(r, sigma_cam)
        for it, th in enumerate(TH_GRID):
            fxc, fyc = to_camera_freq(fx, fy, r, th)
            fxf, fyf = fold(fxc), fold(fyc)
            amp = harmonic_amplitudes(H, fxf, fyf, ss, True)
            rr = (N // 2 + np.rint(fyf * N).astype(int)) % N
            cc = (N // 2 + np.rint(fxf * N).astype(int)) % N
            ok = ~masks.MASK_ALL[rr, cc]
            rr, cc, aa = rr[ok], cc[ok], amp[ok]
            o = np.argsort(-aa)[:60]
            key = rr[o] * N + cc[o]
            _, first = np.unique(key, return_index=True)
            first.sort()
            sel = o[first][:_NPEAK]
            pr = np.full(_NPEAK, N // 2, np.int32)                  # pad with the DC bin (masked, value 0):
            pc = np.full(_NPEAK, N // 2, np.int32)                  # e.g. r=1, theta=0: every LCD harmonic folds onto DC
            pr[:len(sel)], pc[:len(sel)] = rr[sel], cc[sel]
            rows_t[ir, it], cols_t[ir, it] = pr, pc
    return rows_t, cols_t


def template_score(RY, layout):
    """Best (score, r_hat, theta_hat_deg): mean detrended spectrum at predicted peaks minus the spectrum median."""
    rows_t, cols_t = template_tables(layout)
    Rm = maximum_filter(RY, size=3, mode="wrap")
    vals = Rm[rows_t, cols_t].mean(-1)
    base = np.median(RY.ravel()[_VALID_IDX])
    ir, it = np.unravel_index(np.argmax(vals), vals.shape)
    return float(vals[ir, it] - base), float(R_GRID[ir]), float(np.rad2deg(TH_GRID[it]))


def template_score_known(RY, layout, r, theta, sigma_cam=0.4):
    """Known-geometry template test (r and theta given, e.g. from the device specs and the distance):
    mean detrended spectrum at the 12 strongest predicted peaks minus the spectrum median. No search, no hypotheses."""
    from .theory import predicted_peaks
    rows, cols, _ = predicted_peaks(layout, r, theta, sigma_cam, top=_NPEAK, masked=True, bayer=True)
    if len(rows) == 0:
        return 0.0
    Rm = maximum_filter(RY, size=3, mode="wrap")
    vals = np.zeros(_NPEAK)
    vals[:len(rows)] = Rm[rows, cols]
    return float(vals.mean() - np.median(RY.ravel()[_VALID_IDX]))


def features_all(rgb, known=None):
    """74-vector for an sRGB image [N, N, 3] in [0, 1]. known = (r, theta_rad) adds the known-geometry template scores."""
    Y = luma(rgb)
    Cb, Cr = chroma(rgb)
    RY = detrended(Y)
    RC = detrended(Cb) + detrended(Cr)
    out = np.zeros(74)
    out[F_PEAK] = _top_mean(RY)
    out[F_CPEAK] = _top_mean(RC)
    out[F_TL:F_TL + 3] = template_score(RY, "lcd_rgb")
    out[F_TP:F_TP + 3] = template_score(RY, "pentile")
    out[F_SIG:F_SIG + 32] = signature(RY)
    out[F_SIG + 32:F_SIG + 64] = signature(RC)
    if known is not None:
        out[F_KL] = template_score_known(RY, "lcd_rgb", known[0], known[1])
        out[F_KP] = template_score_known(RY, "pentile", known[0], known[1])
    return out, RY
