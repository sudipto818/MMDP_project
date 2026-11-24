"""Spectral bins that carry no moire information: DC/low frequencies, the JPEG 8x8 block grid
and the Bayer sampling frequencies (present in BOTH classes). FFT arrays are indexed (row, col) = (fy, fx),
fftshift-ed, DC at (n//2, n//2)."""
import numpy as np
import config as C

N = C.OUT
ROWS, COLS = np.indices((N, N))
FY = ROWS - N // 2
FX = COLS - N // 2
RADIUS = np.hypot(FY, FX)
RING = np.rint(RADIUS).astype(int)
RING_IDX = [np.flatnonzero(RING.ravel() == k) for k in range(RING.max() + 1)]


def _moddist(a, b):
    d = np.abs(a - b)
    return np.minimum(d, N - d)


def bin_of(fy, fx):
    """(row, col) of the FFT bin of frequency (fy, fx) in cycles/pixel (aliased into [-0.5, 0.5))."""
    return (N // 2 + int(round(fy * N))) % N, (N // 2 + int(round(fx * N))) % N


MASK_LOW = RADIUS < 4

MASK_JPEG = np.zeros((N, N), bool)
for a in range(-4, 4):
    for b in range(-4, 4):
        cr, cc = (N // 2 + a * N // 8) % N, (N // 2 + b * N // 8) % N
        MASK_JPEG |= (_moddist(ROWS, cr) <= 1) & (_moddist(COLS, cc) <= 1)

MASK_BAYER = np.zeros((N, N), bool)
for cr, cc in [(0, 0), (0, N // 2), (N // 2, 0)]:           # (-.5,-.5), (-.5,0), (0,-.5) cycles/px
    MASK_BAYER |= (_moddist(ROWS, cr) <= 2) & (_moddist(COLS, cc) <= 2)

MASK_ALL = MASK_LOW | MASK_JPEG | MASK_BAYER
VALID = ~MASK_ALL
