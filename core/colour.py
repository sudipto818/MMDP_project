"""sRGB <-> linear light, luma and chroma."""
import numpy as np


def srgb_to_linear(x):
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114])


def chroma(rgb):
    """(Cb, Cr) = (B - Y, R - Y)."""
    y = luma(rgb)
    return rgb[..., 2] - y, rgb[..., 0] - y
