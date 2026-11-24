"""Diagnostic: where do the predicted moire peaks rank in the measured spectrum? (not part of the pipeline)"""
import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter

import config as C
from core.sample import make_pair
from core.features import detrended
from core.colour import luma
from core.theory import predicted_peaks

img = np.asarray(Image.open(C.KODAK_DIR / "kodim05.png").convert("RGB"), float) / 255
for r in (0.3, 0.6):
    for layout in ["pentile", "lcd_rgb"]:
        rec, _, _ = make_pair(img, layout, r, 2.0, 0.3, 90, 0.0, seed=5, noise=False, jpeg=False)
        R = detrended(luma(rec))
        Rm = maximum_filter(R, size=3)
        loc = (R == maximum_filter(R, size=5)) & (R > 0)
        vals = np.sort(R[loc])[::-1]
        rows, cols, amp = predicted_peaks(layout, r, np.deg2rad(2.0), 0.3, top=5)
        print(f"{layout} r={r}")
        for a, b, c in zip(rows, cols, amp):
            print(f"   predicted ({a:3d},{b:3d}) amp {c:.3f}: measured {Rm[a, b]:.2f}, rank {int((vals > Rm[a, b]).sum()) + 1}/{len(vals)}")
