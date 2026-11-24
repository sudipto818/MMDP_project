"""Subpixel layouts of screens.

A pixel (i, j) occupies [j, j+1) x [i, i+1) in screen-pixel units (x right, y down).
A layout is a list of emitting rectangles ("subpixels"). Each has:
    channel : 0=R 1=G 2=B
    x0,x1,y0,y1 : rectangle inside the pixel
    gain    : chosen so that a uniform input of 1 gives mean channel radiance 1 over the pixel
    parity  : None (every pixel) or 0/1 (only pixels with (i + j) % 2 == parity)
"""
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass(frozen=True)
class Sub:
    channel: int
    x0: float
    x1: float
    y0: float
    y1: float
    gain: float
    parity: Optional[int] = None

    @property
    def area(self):
        return (self.x1 - self.x0) * (self.y1 - self.y0)


def _lcd(order):
    """Vertical R|G|B stripes with a dark gap at the bottom of every pixel."""
    xs = [(0.02, 0.31), (0.35, 0.64), (0.68, 0.97)]
    subs = []
    for ch, (x0, x1) in zip(order, xs):
        a = (x1 - x0) * (0.88 - 0.02)
        subs.append(Sub(ch, x0, x1, 0.02, 0.88, 1.0 / a))
    return subs


def _pentile():
    """Diamond PenTile (RG/BG): G in every pixel (small dot), R and B alternate in a checkerboard (large dots)."""
    g = Sub(1, 0.55, 0.95, 0.55, 0.95, 1.0 / (0.40 * 0.40))
    a_rb = 0.45 * 0.45
    r = Sub(0, 0.05, 0.50, 0.05, 0.50, 2.0 / a_rb, parity=0)
    b = Sub(2, 0.05, 0.50, 0.05, 0.50, 2.0 / a_rb, parity=1)
    return [r, g, b]


LAYOUTS = {
    "lcd_rgb": _lcd((0, 1, 2)),
    "lcd_bgr": _lcd((2, 1, 0)),
    "pentile": _pentile(),
}

LAYOUT_LABEL = {"lcd_rgb": "LCD stripes (RGB)", "lcd_bgr": "LCD stripes (BGR)", "pentile": "OLED diamond PenTile"}


def cover_1d(a, b, S):
    """Fraction of each of the S cells of [0,1) that is covered by the interval [a, b]."""
    k = np.arange(S)
    lo = np.maximum(a, k / S)
    hi = np.minimum(b, (k + 1) / S)
    return np.clip(hi - lo, 0, None) * S


def emission_finegrid(I, layout, S):
    """Fine-grid emission density (cell averages) for per-pixel intensities I [H, W, 3].
    Returns [H*S, W*S, 3]. Used for the reference renderer, previews and the supercell."""
    H, W, _ = I.shape
    ii, jj = np.indices((H, W))
    out = np.zeros((H * S, W * S, 3))
    for sp in LAYOUTS[layout]:
        base = I[..., sp.channel]
        if sp.parity is not None:
            base = base * (((ii + jj) % 2) == sp.parity)
        tile = np.outer(cover_1d(sp.y0, sp.y1, S), cover_1d(sp.x0, sp.x1, S)) * sp.gain
        out[..., sp.channel] += np.kron(base, tile)
    return out


def supercell(layout, res=60):
    """Emission of a 2x2-pixel block for a uniform input of 1: shape (3, 2*res, 2*res)."""
    e = emission_finegrid(np.ones((2, 2, 3)), layout, res)
    return np.moveaxis(e, -1, 0)
