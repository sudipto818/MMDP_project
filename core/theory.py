"""Sampling theory of a photographed screen.

A screen is periodic, so its emission is a Fourier series; each harmonic has a screen frequency f_s
(cycles per SCREEN pixel). The camera samples at its own lattice, so the harmonic appears at
    f_cam = r * R(-theta) f_s   (cycles per CAMERA pixel)    and is then folded into [-0.5, 0.5)  (aliasing).
The lens (+ pixel aperture) multiplies its amplitude by the MTF exp(-2 pi^2 sigma_s^2 |f_s|^2)
(the Fourier transform of a Gaussian). r = camera pixel / screen pixel as seen on the sensor.
"""
from functools import lru_cache
import numpy as np

import config as C
from .layouts import supercell
from .render import sigma_screen
from . import masks


def fold(f):
    return ((np.asarray(f, dtype=float) + 0.5) % 1.0) - 0.5


def mtf(f_mag, sigma_s):
    return np.exp(-2.0 * np.pi ** 2 * sigma_s ** 2 * np.asarray(f_mag) ** 2)


def to_camera_freq(fx, fy, r, theta):
    """Screen frequency (fx, fy) [cycles/screen px] -> camera frequency (fx_cam, fy_cam) [cycles/camera px], unfolded."""
    ct, st = np.cos(theta), np.sin(theta)
    return r * (fx * ct + fy * st), r * (-fx * st + fy * ct)


@lru_cache(maxsize=None)
def layout_harmonics(layout, kmax=6, res=60):
    """Fourier harmonics of the layout (grey input 0.5 on every channel is equivalent to input 1 after normalising by DC).
    Returns dict: fx, fy (cycles/screen px, multiples of 1/2), amp (|c_k|/|c_0| of the luma emission), rgb (|c_k|/|c_0| per channel)."""
    E = supercell(layout, res)                                # [3, 2res, 2res], mean 1 per channel
    n = 2 * res
    F = np.fft.fft2(E, axes=(1, 2)) / (n * n)                 # complex Fourier coefficients c_k, axes (y, x)
    w = np.array([0.299, 0.587, 0.114])
    lum = np.tensordot(w, F, axes=1)                          # linear in E
    dc = abs(lum[0, 0])
    fxs, fys, amp, rgb = [], [], [], []
    for ky in range(-2 * kmax, 2 * kmax + 1):
        for kx in range(-2 * kmax, 2 * kmax + 1):
            if kx == 0 and ky == 0:
                continue
            fxs.append(kx / 2.0)
            fys.append(ky / 2.0)
            amp.append(abs(lum[ky % n, kx % n]) / dc)
            rgb.append([abs(F[c, ky % n, kx % n]) for c in range(3)])
    cplx = []
    for ky in range(-2 * kmax, 2 * kmax + 1):
        for kx in range(-2 * kmax, 2 * kmax + 1):
            if kx == 0 and ky == 0:
                continue
            cplx.append([F[c, ky % n, kx % n] / F[c, 0, 0] for c in range(3)])     # per-channel complex c_k / c_0
    return {"fx": np.array(fxs), "fy": np.array(fys), "amp": np.array(amp), "rgb": np.array(rgb),
            "cplx": np.array(cplx)}


LUMA_W = np.array([0.299, 0.587, 0.114])


def demosaic_response(fx_cam, fy_cam):
    """Frequency response (main term) of bilinear demosaicing per channel R, G, B at camera frequency (cycles/px).
    R and B are sampled on every 2nd pixel in x and y and interpolated with [1 2 1]/2 per axis:
        (1 + cos 2 pi fx)(1 + cos 2 pi fy) / 4.
    G is sampled on a checkerboard:  1/2 + (cos 2 pi fx + cos 2 pi fy)/4.
    Above 0.25 cycles/px the R/B response collapses (the Bayer sampling grid is sparser than the sensor grid)."""
    cx, cy = np.cos(2 * np.pi * fx_cam), np.cos(2 * np.pi * fy_cam)
    h_rb = (1 + cx) * (1 + cy) / 4.0
    h_g = 0.5 + (cx + cy) / 4.0
    return np.stack([h_rb, h_g, h_rb], axis=-1)


def harmonic_amplitudes(H, fxf, fyf, ss, bayer=True):
    """Predicted amplitude of every harmonic at its folded camera frequency: lens MTF x (optional) Bayer demosaic response."""
    m = mtf(np.hypot(H["fx"], H["fy"]), ss)
    if not bayer:
        return H["amp"] * m
    h = demosaic_response(fxf, fyf)                                       # [K, 3]
    return np.abs(np.sum(LUMA_W * h * H["cplx"], axis=-1)) * m


def predicted_peaks(layout, r, theta, sigma_cam, top=None, masked=True, n=C.OUT, bayer=True):
    """Predicted moire peaks in the camera image's FFT: (rows, cols, amps), strongest first, duplicates merged (max)."""
    H = layout_harmonics(layout)
    fxc, fyc = to_camera_freq(H["fx"], H["fy"], r, theta)
    fxf, fyf = fold(fxc), fold(fyc)
    ss = sigma_screen(r, sigma_cam)
    amp = harmonic_amplitudes(H, fxf, fyf, ss, bayer)
    rows = (n // 2 + np.rint(fyf * n).astype(int)) % n
    cols = (n // 2 + np.rint(fxf * n).astype(int)) % n
    if masked:
        keep = ~masks.MASK_ALL[rows, cols]
        rows, cols, amp = rows[keep], cols[keep], amp[keep]
    order = np.argsort(-amp)
    rows, cols, amp = rows[order], cols[order], amp[order]
    key = rows * n + cols
    _, first = np.unique(key, return_index=True)               # first = strongest occurrence of each bin
    first.sort()
    rows, cols, amp = rows[first], cols[first], amp[first]
    if top is not None:
        rows, cols, amp = rows[:top], cols[:top], amp[:top]
    return rows, cols, amp


def theory_amp(layout, r, sigma_cam, theta=0.0, masked=True, bayer=True):
    """Strongest predicted moire amplitude that survives the lens (and demosaic) and is not hidden by the masks."""
    _, _, amp = predicted_peaks(layout, r, theta, sigma_cam, top=1, masked=masked, bayer=bayer)
    return float(amp[0]) if len(amp) else 0.0


def r_from_geometry(pitch_mm, f_mm, d_mm, cam_px_um):
    """r = camera pixel / (screen pixel x magnification), thin lens m = f / (d - f)."""
    m = f_mm / (d_mm - f_mm)
    return (cam_px_um / 1000.0) / (pitch_mm * m)


def distance_from_r(pitch_mm, f_mm, r, cam_px_um):
    """Inverse of r_from_geometry: distance (mm) that gives this r."""
    return f_mm + r * pitch_mm * f_mm / (cam_px_um / 1000.0)
