"""Score REAL photos with the FROZEN detector (trained on simulated data only). Nothing is retuned to fit the photos.

Folder layout (data/real/):
    screen_laptop_12cm/A_1.jpg ...      photos of a screen: screen_<laptop|monitor|phone>_<distance>cm[_fullres]
    direct_none/scene1.jpg ...          ordinary photos, no screen
(or, alternatively, a data/real/meta.csv with columns file,kind,screen,distance_cm,phone_model,notes)

Photos are never resized (resizing is another sampling step and would destroy the moire). EXIF orientation is applied.
For screen photos only the displayed PICTURE region is used (found automatically, boxes checked by eye in figs/real_roi_check.png,
manual overrides possible in data/real/roi_overrides.csv: file,y0,y1,x0,x1 in full-resolution pixels). 128x128 crops are taken
inside that region at native resolution.

    python score_real.py [--dir data/real] [--n-crops 8]
Outputs: cache/real_results.csv, figs/real_scores.png, figs/real_roi_check.png, figs/real_examples.png
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageDraw
from scipy import ndimage as ndi

import config as C
from core import theory
from core.features import features_all, F_PEAK, F_CPEAK, F_TL, F_TP
from core.stats import predict_proba

DET_IDX = [F_PEAK, F_CPEAK, F_TL, F_TP]
N = C.OUT
FOLDER_RE = re.compile(r"^(screen|direct)_([a-z]+)(?:_(\d+)cm)?(_fullres)?$")


def load_detector():
    R = json.loads((C.CACHE_DIR / "results.json").read_text())
    d = R["E1"]["detector_B"]
    return np.array(d["mu"]), np.array(d["sd"]), np.array(d["w"])


# ---------------------------------------------------------------- region of interest
def _roi_at_threshold(L, dark_thr, s, shape):
    dark = ndi.binary_opening(L < dark_thr, iterations=1)
    lab, n = ndi.label(dark)
    cand = None
    if n:
        sizes = ndi.sum(dark, lab, range(1, n + 1))
        big = lab == (int(np.argmax(sizes)) + 1)
        holes = ndi.binary_fill_holes(big) & ~big
        holes = ndi.binary_opening(holes, structure=np.ones((3, 3)), iterations=3)      # drop thin structures (task bar, icons)
        if holes.sum() > 0.003 * holes.size:
            cand = holes
    if cand is None:
        cand = ndi.binary_opening((L > 0.15) & ~dark, structure=np.ones((3, 3)), iterations=3)
    lab2, n2 = ndi.label(cand)
    if n2 == 0:
        return None
    sizes = ndi.sum(cand, lab2, range(1, n2 + 1))
    ys, xs = np.where(lab2 == (int(np.argmax(sizes)) + 1))
    return ys.min() * s, (ys.max() + 1) * s, xs.min() * s, (xs.max() + 1) * s


def find_picture_roi(arr, shrink=0.12):
    """Box (y0, y1, x0, x1), full-resolution pixels, around the picture displayed on a screen.
    Idea: the screen/bezel is the largest dark region; the picture is the bright 'hole' enclosed by it. Several darkness
    thresholds are tried (screens are not equally black in every photo). A box is rejected if it is mostly red cloth
    (the bedsheet in the phone photos) or too small. Returns None if nothing plausible is found (then use roi_overrides.csv)."""
    H, W = arr.shape[:2]
    s = 16
    small = arr[:H // s * s, :W // s * s].reshape(H // s, s, W // s, s, 3).mean((1, 3))
    L = small @ np.array([0.299, 0.587, 0.114])
    for thr in (0.10, 0.14, 0.18, 0.24):
        box = _roi_at_threshold(L, thr, s, (H, W))
        if box is None:
            continue
        y0, y1, x0, x1 = box
        if (y1 - y0) < 4 * N or (x1 - x0) < 4 * N or (y1 - y0) > 0.85 * H:
            continue
        inner = arr[y0:y1, x0:x1].reshape(-1, 3)
        redness = 2 * inner[:, 0].mean() / (inner[:, 1].mean() + inner[:, 2].mean() + 1e-6)
        if redness > 1.9:                       # red bedsheet, not the displayed picture
            continue
        dy, dx = int((y1 - y0) * shrink), int((x1 - x0) * shrink)
        return y0 + dy, y1 - dy, x0 + dx, x1 - dx
    return None


def crops_in(arr, box, n_crops, rng):
    y0, y1, x0, x1 = box
    if y1 - y0 < N + 8 or x1 - x0 < N + 8:
        raise ValueError(f"region {x1 - x0}x{y1 - y0} too small for {N}x{N} crops")
    for _ in range(n_crops):
        y, x = int(rng.integers(y0, y1 - N + 1)), int(rng.integers(x0, x1 - N + 1))
        yield arr[y:y + N, x:x + N], (y, x)


def central_box(arr, frac=0.6):
    H, W = arr.shape[:2]
    return int(H * (1 - frac) / 2), int(H * (1 + frac) / 2), int(W * (1 - frac) / 2), int(W * (1 + frac) / 2)


def read_overrides(folder):
    p = folder / "roi_overrides.csv"
    if not p.exists():
        return {}
    return {r["file"]: (int(r["y0"]), int(r["y1"]), int(r["x0"]), int(r["x1"])) for r in csv.DictReader(open(p, newline=""))}


# ---------------------------------------------------------------- scoring
def tree_rows(folder):
    rows = []
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        m = FOLDER_RE.match(d.name)
        if not m:
            continue
        kind, dev, dist, full = m.groups()
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg"):
                rows.append({"file": str(f.relative_to(folder)).replace("\\", "/"), "kind": kind, "screen": dev if kind == "screen" else "none",
                             "distance_cm": dist or "", "fullres": "1" if full else "", "phone_model": "", "notes": ""})
    return rows


def score_rows(folder, rows, n_crops=8, use_roi=True):
    mu, sd, w = load_detector()
    rng = np.random.default_rng(C.SEED)
    over = read_overrides(folder)
    out = []
    for row in rows:
        im = ImageOps.exif_transpose(Image.open(folder / row["file"])).convert("RGB")
        arr = np.asarray(im, dtype=np.float64) / 255.0
        box = over.get(row["file"]) or (find_picture_roi(arr) if (use_roi and row["kind"] == "screen") else None) or central_box(arr)
        feats = np.stack([features_all(c)[0] for c, _ in crops_in(arr, box, n_crops, rng)])
        f = feats.mean(0)
        ps = predict_proba(w, ((feats[:, DET_IDX] - mu) / sd))
        dist = float(row["distance_cm"]) if row.get("distance_cm") not in (None, "") else float("nan")
        out.append({**row, "distance_cm": dist, "peakiness": f[F_PEAK], "chroma_peak": f[F_CPEAK], "tmpl_lcd": f[F_TL], "tmpl_pent": f[F_TP],
                    "p_screen": float(ps.mean()), "p_screen_min": float(ps.min()), "p_screen_max": float(ps.max()),
                    "roi": "x".join(str(v) for v in box), "width": im.width, "height": im.height})
    return out


def score_folder(folder, px_um, n_crops=5):
    """Backward-compatible entry (used by the test): meta.csv driven, central 60% region."""
    rows = list(csv.DictReader(open(folder / "meta.csv", newline="", encoding="utf-8")))
    res = score_rows(folder, rows, n_crops, use_roi=False)
    for r in res:
        dev = r.get("screen", "none")
        r["r_predicted"] = (theory.r_from_geometry(C.DEVICES[dev]["pitch_mm"], C.CAMERA["f_mm"], r["distance_cm"] * 10, px_um)
                            if dev in C.DEVICES and np.isfinite(r["distance_cm"]) else float("nan"))
    return res


def roi_check_figure(folder, res, path):
    """Whole frames (after EXIF rotation) with the region used for the crops drawn in green. Check this by eye."""
    fs = [r for r in res if r["kind"] == "screen"]
    cols, th = 8, 330
    rows_n = (len(fs) + cols - 1) // cols
    cells = []
    for r in fs:
        im = ImageOps.exif_transpose(Image.open(folder / r["file"])).convert("RGB")
        sc = th / im.height
        cells.append((r, im.resize((max(1, int(im.width * sc)), th)), sc))
    tw = max(c[1].width for c in cells)
    sheet = Image.new("RGB", (cols * (tw + 4), rows_n * (th + 16)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (r, sm, sc) in enumerate(cells):
        y0, y1, x0, x1 = (int(v) for v in r["roi"].split("x"))
        ImageDraw.Draw(sm).rectangle([x0 * sc, y0 * sc, x1 * sc, y1 * sc], outline=(0, 255, 0), width=3)
        x, y = (i % cols) * (tw + 4), (i // cols) * (th + 16)
        sheet.paste(sm, (x, y + 16))
        d.text((x + 2, y + 2), r["file"].replace("screen_", "").replace(".jpg", "")[:26], fill="black")
    sheet.save(path)


def examples_figure(folder, res, path, wanted=None, figw=2.3, figh=5.0):
    """Native-resolution 128x128 crops (no resizing) and their detrended spectra for one photo per condition."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from core.colour import luma
    from core.features import detrended
    byfile = {r["file"]: r for r in res}
    # direct example: a BRIGHT, textured photo whose peakiness is closest to the median of the direct photos (not a dark, blank crop)
    dpk = [r["peakiness"] for r in res if r["kind"] == "direct"]
    best, bestd = None, 1e9
    for r in res:
        if r["kind"] != "direct":
            continue
        im0 = ImageOps.exif_transpose(Image.open(folder / r["file"])).convert("RGB")
        a0 = np.asarray(im0, dtype=np.float64) / 255.0
        y0, y1, x0, x1 = (int(v) for v in r["roi"].split("x"))
        c0 = a0[(y0 + y1) // 2 - N // 2:(y0 + y1) // 2 + N // 2, (x0 + x1) // 2 - N // 2:(x0 + x1) // 2 + N // 2]
        if c0.mean() > 0.3 and abs(r["peakiness"] - np.median(dpk)) < bestd:
            best, bestd = r["file"], abs(r["peakiness"] - np.median(dpk))
    direct_pick = best or "direct_none/scene1.jpg"
    if wanted is None:
        wanted = ["DIRECT", "screen_laptop_12cm/A_1.jpg", "screen_laptop_20cm/A_1.jpg", "screen_laptop_35cm/A_1.jpg",
                  "screen_phone_12cm/A_1.jpg", "screen_phone_20cm/A_1.jpg", "screen_phone_35cm/A_1.jpg"]
    wanted = [direct_pick if w == "DIRECT" else w for w in wanted]
    wanted = [w for w in wanted if w in byfile]
    fig, axs = plt.subplots(2, len(wanted), figsize=(figw * len(wanted), figh))
    for j, fn in enumerate(wanted):
        r = byfile[fn]
        im = ImageOps.exif_transpose(Image.open(folder / fn)).convert("RGB")
        arr = np.asarray(im, dtype=np.float64) / 255.0
        y0, y1, x0, x1 = (int(v) for v in r["roi"].split("x"))
        cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
        crop = arr[cy - N // 2:cy + N // 2, cx - N // 2:cx + N // 2]
        axs[0, j].imshow(crop, interpolation="nearest"); axs[0, j].set_xticks([]); axs[0, j].set_yticks([])
        axs[0, j].set_title(fn.split("/")[0].replace("screen_laptop", "laptop (141 ppi)").replace("screen_phone", "Moto G32 (405 ppi)").replace("direct_none", "ordinary photo").replace("_", " ") + f"\npeakiness {r['peakiness']:.2f}", fontsize=8)
        axs[1, j].imshow(detrended(luma(crop)), cmap="magma", vmin=-1, vmax=6, interpolation="nearest"); axs[1, j].set_xticks([]); axs[1, j].set_yticks([])
    axs[0, 0].set_ylabel("native 128x128 crop", fontsize=8); axs[1, 0].set_ylabel("spectrum (detrended)", fontsize=8)
    fig.suptitle("Real photos (Motorola Edge main camera): bright isolated spots = screen lattice (moire)", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(C.DATA_DIR / "real"))
    ap.add_argument("--n-crops", type=int, default=8)
    ap.add_argument("--no-roi", action="store_true")
    a = ap.parse_args()
    folder = Path(a.dir) if Path(a.dir).is_absolute() else C.ROOT / a.dir
    rows = list(csv.DictReader(open(folder / "meta.csv", newline="", encoding="utf-8"))) if (folder / "meta.csv").exists() else tree_rows(folder)
    if not rows:
        sys.exit(f"no photos found in {folder}")
    res = score_rows(folder, rows, a.n_crops, use_roi=not a.no_roi)
    C.CACHE_DIR.mkdir(exist_ok=True); C.FIGS_DIR.mkdir(exist_ok=True)
    with open(C.CACHE_DIR / "real_results.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(res[0])); wr.writeheader(); wr.writerows(res)
    roi_check_figure(folder, res, C.FIGS_DIR / "real_roi_check.png")
    print(f"{'file':44s} {'dist':>4s} {'peak':>6s} {'chroma':>6s} {'P(screen)':>9s}  [min-max over crops]")
    for r in res:
        print(f"{r['file'][:44]:44s} {r['distance_cm']:4.0f} {r['peakiness']:6.2f} {r['chroma_peak']:6.2f} {r['p_screen']:9.2f}  [{r['p_screen_min']:.2f}-{r['p_screen_max']:.2f}]")
    print("\nmean P(screen) by group (0.5 = cannot tell; higher = looks like a screen photo):")
    groups = sorted({(r["kind"], r["screen"], r["distance_cm"]) for r in res}, key=lambda g: (g[0] != "direct", g[1], g[2] if np.isfinite(g[2]) else -1))
    for kind, dev, dist in groups:
        g = [r for r in res if (r["kind"], r["screen"], r["distance_cm"]) == (kind, dev, dist) or (kind == "direct" and r["kind"] == "direct")]
        if kind == "direct" and dev != "none":
            continue
        print(f"  {kind:7s} {dev:8s} {('%gcm' % dist) if np.isfinite(dist) else '   -':>6s}  n={len(g):2d}  mean P = {np.mean([r['p_screen'] for r in g]):.2f}   mean peakiness = {np.mean([r['peakiness'] for r in g]):.2f}")
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        col = {"laptop": "#2a6fdb", "monitor": "#2a9d6f", "phone": "#c2307f"}
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
        for ax, key, ylab, ttl in ((axs[0], "peakiness", "spectral peakiness of the picture region", "Raw feature (what the theory is about)"),
                                   (axs[1], "p_screen", "detector P(screen photo)", "Frozen detector trained only on simulation")):
            dd = [r[key] for r in res if r["kind"] == "direct"]
            if dd:
                ax.axhspan(min(dd), max(dd), color="gray", alpha=0.18, label="direct photos (range)")
            for dev in sorted({r["screen"] for r in res if r["kind"] == "screen"}):
                xs = [r["distance_cm"] for r in res if r["screen"] == dev and r["kind"] == "screen"]
                ys = [r[key] for r in res if r["screen"] == dev and r["kind"] == "screen"]
                ax.scatter(xs, ys, c=col.get(dev, "k"), alpha=0.8, label=("HP Victus laptop (141 ppi)" if dev == "laptop" else "Moto G32 (405 ppi LCD)") + " screen photos")
            ax.set_xlabel("distance (cm)"); ax.set_ylabel(ylab); ax.set_title(ttl, fontsize=10); ax.legend(fontsize=8)
        axs[1].axhline(0.5, ls="--", c="gray"); axs[1].set_ylim(-0.02, 1.02)
        fig.tight_layout(); fig.savefig(C.FIGS_DIR / "real_scores.png", dpi=180); plt.close(fig)
        examples_figure(folder, res, C.FIGS_DIR / "real_examples.png")
        examples_figure(folder, res, C.FIGS_DIR / "real_examples_slide.png",
                        wanted=["DIRECT", "screen_laptop_12cm/A_1.jpg", "screen_laptop_35cm/A_1.jpg", "screen_phone_12cm/A_1.jpg", "screen_phone_35cm/A_1.jpg"],
                        figw=2.7, figh=5.7)
    except Exception as e:      # noqa: BLE001
        print("figure skipped:", e)
    print("\nwrote", C.CACHE_DIR / "real_results.csv", "and figs/real_roi_check.png, real_scores.png, real_examples.png")
    print("Reminder: nothing was retuned to fit these photos. If they disagree with the simulation, report the gap.")


if __name__ == "__main__":
    main()
