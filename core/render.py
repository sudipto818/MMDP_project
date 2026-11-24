"""Analytic screen renderer, scene renderer and a fine-grid reference renderer.

Physics. A screen shows image I. Each pixel emits light from small rectangles (subpixels).
The lens blurs the emitted light with a Gaussian of std sigma_s (in screen-pixel units), and the
camera samples the blurred light at its own (rotated, differently spaced) pixel centres.
The blurred light at (X, Y) of one rectangle [x0,x1]x[y0,y1] of pixel (i,j) is
    (Phi((X-j-x0)/s) - Phi((X-j-x1)/s)) * (Phi((Y-i-y0)/s) - Phi((Y-i-y1)/s)),
the exact convolution of a box with a Gaussian (Phi = standard normal CDF).
"""
import numpy as np
from scipy.special import ndtr
from scipy.ndimage import gaussian_filter, map_coordinates

import config as C
from .layouts import LAYOUTS, emission_finegrid


def sigma_screen(r, sigma_cam):
    """Total blur (lens + pixel aperture) in screen-pixel units: r * hypot(sigma_lens, sigma_aperture)."""
    return r * np.hypot(sigma_cam, C.SIGMA_APERTURE)


def camera_grid(r, theta, cx, cy, out=C.OUT):
    """Screen coordinates (X, Y) of every camera pixel centre.
    X = cx + r (cos t (u-c) - sin t (v-c)),  Y = cy + r (sin t (u-c) + cos t (v-c)),  u = column, v = row."""
    c = (out - 1) / 2.0
    v, u = np.indices((out, out), dtype=np.float64)
    du, dv = u - c, v - c
    X = cx + r * (np.cos(theta) * du - np.sin(theta) * dv)
    Y = cy + r * (np.sin(theta) * du + np.cos(theta) * dv)
    return X, Y


def _halfwin(sig):
    """Half window (screen pixels). Gaussian tail beyond 3.2 sigma is < 0.1 % of the amplitude, below 8-bit precision."""
    return int(np.ceil(3.2 * sig)) + 1


def required_crop(r, theta, sigma_cam, out=C.OUT):
    """Side (screen pixels) of the square source crop the camera footprint needs, with blur margin."""
    sig = sigma_screen(r, sigma_cam)
    half = r * (out / 2.0) * (abs(np.cos(theta)) + abs(np.sin(theta))) + _halfwin(sig) + 3
    return int(np.ceil(2 * half))


def random_crop(img, side, rng):
    H, W = img.shape[:2]
    if side > min(H, W):
        raise ValueError(f"crop {side} larger than image {H}x{W}")
    i0 = int(rng.integers(0, H - side + 1))
    j0 = int(rng.integers(0, W - side + 1))
    return img[i0:i0 + side, j0:j0 + side], (i0, j0)


def render_screen(crop_lin, layout, r, theta, sigma_cam, out=C.OUT):
    """Photograph of a SCREEN showing crop_lin (linear light, [H, W, 3]); returns linear radiance [out, out, 3]."""
    H, W, _ = crop_lin.shape
    sig = sigma_screen(r, sigma_cam)
    K = _halfwin(sig)
    X, Y = camera_grid(r, theta, W / 2.0, H / 2.0, out)
    if (np.floor(X.min()) - K < 0 or np.floor(Y.min()) - K < 0 or np.floor(X.max()) + K >= W or np.floor(Y.max()) + K >= H):
        raise ValueError("camera footprint leaves the source crop (use required_crop)")
    offs = np.arange(-K, K + 1)
    ii0, jj0 = np.indices((H, W))
    # one pre-masked 2-D source per subpixel (parity rule applied once, not per camera pixel)
    sources = []
    for sp in LAYOUTS[layout]:
        s = crop_lin[..., sp.channel]
        if sp.parity is not None:
            s = s * (((ii0 + jj0) % 2) == sp.parity)
        sources.append(np.ascontiguousarray(s).ravel())
    res = np.zeros((out, out, 3))
    rows = max(1, 12288 // ((2 * K + 1) ** 2))           # chunk of camera rows: keeps the temporaries cache sized
    for v0 in range(0, out, rows):
        Xc, Yc = X[v0:v0 + rows], Y[v0:v0 + rows]
        jj = np.floor(Xc).astype(np.int64)[..., None] + offs                     # [m, out, Kw]
        ii = np.floor(Yc).astype(np.int64)[..., None] + offs                     # [m, out, Kh]
        relx, rely = Xc[..., None] - jj, Yc[..., None] - ii
        flat = ii[..., :, None] * W + jj[..., None, :]                           # [m, out, Kh, Kw]
        cache_x, cache_y = {}, {}               # separate caches: x and y intervals can be equal tuples
        for sp, src in zip(LAYOUTS[layout], sources):
            kx, ky = (sp.x0, sp.x1), (sp.y0, sp.y1)
            if kx not in cache_x:
                cache_x[kx] = ndtr((relx - sp.x0) / sig) - ndtr((relx - sp.x1) / sig)
            if ky not in cache_y:
                cache_y[ky] = ndtr((rely - sp.y0) / sig) - ndtr((rely - sp.y1) / sig)
            Ig = src[flat]                                                       # [m, out, Kh, Kw]
            tmp = np.einsum("uvhw,uvw->uvh", Ig, cache_x[kx])                    # contract x
            res[v0:v0 + rows, :, sp.channel] += sp.gain * np.einsum("uvh,uvh->uv", tmp, cache_y[ky])   # contract y
    return res


def render_scene(crop_lin, r, theta, sigma_cam, out=C.OUT):
    """Photograph of the real SCENE (no screen) whose content is crop_lin: smooth, no pixel lattice."""
    H, W, _ = crop_lin.shape
    sig = sigma_screen(r, sigma_cam)
    X, Y = camera_grid(r, theta, W / 2.0, H / 2.0, out)
    res = np.zeros((out, out, 3))
    for c in range(3):
        sm = gaussian_filter(crop_lin[..., c], sig, mode="nearest")
        res[..., c] = map_coordinates(sm, [Y - 0.5, X - 0.5], order=3, mode="nearest")
    return np.clip(res, 0, None)


def render_screen_finegrid(crop_lin, layout, r, theta, sigma_cam, S=12, out=C.OUT):
    """Slow reference: rasterise the subpixels on an S x S fine grid, blur, sample. Used only in tests."""
    H, W, _ = crop_lin.shape
    sig = sigma_screen(r, sigma_cam)
    E = emission_finegrid(crop_lin, layout, S)
    X, Y = camera_grid(r, theta, W / 2.0, H / 2.0, out)
    res = np.zeros((out, out, 3))
    for c in range(3):
        sm = gaussian_filter(E[..., c], sig * S, mode="nearest")
        res[..., c] = map_coordinates(sm, [Y * S - 0.5, X * S - 0.5], order=1, mode="nearest")
    return res


def subpixel_preview(crop_lin, layout, n_pix=14, S=14):
    """Zoomed-in picture of the screen itself (no camera): n_pix x n_pix screen pixels at S px each."""
    n = min(n_pix, crop_lin.shape[0], crop_lin.shape[1])
    i0, j0 = (crop_lin.shape[0] - n) // 2, (crop_lin.shape[1] - n) // 2
    E = emission_finegrid(crop_lin[i0:i0 + n, j0:j0 + n], layout, S)
    E = E / max(E.max(), 1e-9) * 1.0
    from .colour import linear_to_srgb
    return linear_to_srgb(np.clip(E, 0, 1))
