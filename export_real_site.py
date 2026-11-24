"""Export the real-photo results for the website's Lesson 7: site/data/real.js (window.REAL) and small crop/spectrum PNGs in site/img/.
Only derived 128x128 crops and spectra are exported, never the original photos.   Run after score_real.py and analyze_real.py.

    python export_real_site.py
"""
import csv
import json

import numpy as np
from PIL import Image, ImageOps
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as C
from core.colour import luma
from core.features import detrended, F_PEAK

REAL = C.DATA_DIR / "real"
IMG = C.SITE_DIR / "img"
rows = list(csv.DictReader(open(C.CACHE_DIR / "real_results.csv", encoding="utf-8")))
for r in rows:
    r["peakiness"] = float(r["peakiness"]); r["distance_cm"] = float(r["distance_cm"])
G = json.loads((C.CACHE_DIR / "real_geometry.json").read_text())
R = json.loads((C.CACHE_DIR / "results.json").read_text())
cm = plt.get_cmap("magma")


def crop_of(row):
    im = ImageOps.exif_transpose(Image.open(REAL / row["file"])).convert("RGB")
    a = np.asarray(im, dtype=np.float64) / 255.0
    y0, y1, x0, x1 = (int(v) for v in row["roi"].split("x"))
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    return a[cy - 64:cy + 64, cx - 64:cx + 64]


def save_pair(row, tag):
    c = crop_of(row)
    Image.fromarray((c * 255).astype(np.uint8)).save(IMG / f"real_{tag}.png")
    sp = (cm(np.clip((detrended(luma(c)) + 1.0) / 7.0, 0, 1))[..., :3] * 255).astype(np.uint8)
    Image.fromarray(sp).save(IMG / f"real_{tag}_spec.png")


# bright ordinary photo with median peakiness as the reference example
direct = [r for r in rows if r["kind"] == "direct"]
med = np.median([r["peakiness"] for r in direct])
ref = min((r for r in direct if crop_of(r).mean() > 0.3), key=lambda r: abs(r["peakiness"] - med))
save_pair(ref, "ordinary")

conds = []
for t in G["table"]:
    dev = t["device"]
    photos = [r for r in rows if r["kind"] == "screen" and r["screen"] == dev and r["distance_cm"] == t["d_cm"]]
    first = next(r for r in photos if r["file"].endswith("A_1.jpg"))
    tag = f"{dev}_{int(t['d_cm'])}"
    save_pair(first, tag)
    conds.append({"device": dev, "d": int(t["d_cm"]), "r": t["r"], "sim_auc": t["sim_auc"], "peak": [r["peakiness"] for r in photos],
                  "mean": t["peak_mean"], "min": t["peak_min"], "max": t["peak_max"], "above": t["n_above_direct_max"], "n": t["n"], "tag": tag,
                  "calibration": dev == "laptop" and int(t["d_cm"]) in (12, 20)})

z = np.load(C.CACHE_DIR / "E2.npz")
lcd = z["layout_i"] == 0
sim = {"r": [float(np.median(z["r"][lcd & (z["bin"] == b)])) for b in range(8)],
       "median": [float(np.median(z["fr"][lcd & (z["bin"] == b), F_PEAK])) for b in range(8)],
       "lo": [float(np.percentile(z["fr"][lcd & (z["bin"] == b), F_PEAK], 10)) for b in range(8)],
       "hi": [float(np.percentile(z["fr"][lcd & (z["bin"] == b), F_PEAK], 90)) for b in range(8)],
       "direct95": [float(np.percentile(z["fd"][lcd, F_PEAK], 2.5)), float(np.percentile(z["fd"][lcd, F_PEAK], 97.5))]}

out = {"conditions": conds, "sim": sim, "ordinary": {"min": min(r["peakiness"] for r in direct), "max": max(r["peakiness"] for r in direct),
                                                      "mean": float(np.mean([r["peakiness"] for r in direct])), "n": len(direct), "peak": ref["peakiness"]},
       "px_est_um": G["px_est_um"], "px_used_um": G["px_used_um"], "px_exif_um": G["px_exif_um"],
       "devices": {"laptop": {"label": "HP Victus laptop (15.6\" FHD LCD, 141 ppi)", "pitch_mm": G["pitch_mm"]["laptop"]},
                   "phone": {"label": "Moto G32 (6.5\" LCD, about 405 ppi)", "pitch_mm": G["pitch_mm"]["phone"]}},
       "fit_baseline": G["fit_baseline"], "camera": "Motorola Edge 50 Fusion, main camera"}
(C.SITE_DIR / "data" / "real.js").write_text("window.REAL = " + json.dumps(out) + ";\n", encoding="utf-8")
print(f"wrote site/data/real.js ({len(conds)} conditions) and {2 * (len(conds) + 1)} images")
