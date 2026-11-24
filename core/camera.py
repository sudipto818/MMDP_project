"""Camera pipeline: exposure -> shot/read noise -> Bayer RGGB -> bilinear demosaic (convolution)
-> optional sharpening -> gamma -> 8 bit -> JPEG."""
import io
import numpy as np
from PIL import Image
from scipy.ndimage import convolve, gaussian_filter

import config as C
from .colour import linear_to_srgb

K_G = np.array([[0, 1, 0], [1, 4, 1], [0, 1, 0]], float) / 4.0
K_RB = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], float) / 4.0


def bayer_masks(n):
    m = np.zeros((n, n, 3))
    m[0::2, 0::2, 0] = 1                 # R at (even, even)
    m[0::2, 1::2, 1] = 1                 # G
    m[1::2, 0::2, 1] = 1                 # G
    m[1::2, 1::2, 2] = 1                 # B at (odd, odd)
    return m


def bayer_demosaic(L):
    """Mosaic L [n, n, 3] with RGGB then reconstruct by bilinear interpolation (a convolution)."""
    n = L.shape[0]
    mos = L * bayer_masks(n)
    out = np.empty_like(L)
    out[..., 0] = convolve(mos[..., 0], K_RB, mode="mirror")
    out[..., 1] = convolve(mos[..., 1], K_G, mode="mirror")
    out[..., 2] = convolve(mos[..., 2], K_RB, mode="mirror")
    return out


def jpeg_roundtrip(x8, q):
    buf = io.BytesIO()
    Image.fromarray(x8).save(buf, "JPEG", quality=int(q), subsampling=2)
    buf.seek(0)
    return np.array(Image.open(buf).convert("RGB"))


def camera_pipeline(L, rng, jpeg_q=90, sharpen=0.0, noise=True, jpeg=True):
    """L: linear radiance [n, n, 3], already scaled by the exposure gain. Returns sRGB float [0, 1]."""
    L = np.clip(L, 0, 1)
    if noise:
        sd = np.sqrt(C.NOISE_SHOT * L + C.NOISE_READ ** 2)
        L = np.clip(L + rng.standard_normal(L.shape) * sd, 0, 1)
    D = bayer_demosaic(L)
    if sharpen > 0:
        D = D + sharpen * (D - gaussian_filter(D, (1.0, 1.0, 0), mode="mirror"))
    s = linear_to_srgb(D)
    x8 = np.round(np.clip(s, 0, 1) * 255).astype(np.uint8)
    if jpeg:
        x8 = jpeg_roundtrip(x8, jpeg_q)
    return x8.astype(np.float64) / 255.0
