"""Checks that make the REAL photos comparable with the simulation (nothing is retuned).

1. Measure the camera geometry from the photos themselves: at 12 and 20 cm the laptop's LCD lattice is resolved, so a
   template fit of the lattice (known layout, free r and theta) gives r. With the laptop pitch, r gives the effective camera
   pixel:  r = px (d - f) / (pitch f).  Compare with the EXIF-based estimate.
2. Compute r for every condition from the real pixel pitches (HP Victus 15 FHD 15.6", Moto G32 405 ppi LCD).
3. Overlay the real photos' peakiness on the simulation's (same feature code) -> figs/real_vs_sim.png
4. Draw the theory-predicted peaks on real spectra and count how many land on bright spots -> figs/real_peaks.png

    python analyze_real.py       (run after score_real.py)       -> cache/real_geometry.json
"""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageOps
from scipy.ndimage import maximum_filter

import config as C
from core import masks
from core.colour import luma
from core.features import detrended, F_PEAK
from core.theory import predicted_peaks, r_from_geometry, distance_from_r

N = C.OUT
REAL_DIR = C.DATA_DIR / "real"
# Real pixel pitches (mm)
PITCH = {"laptop": 25.4 * np.hypot(16, 9) / np.hypot(1920, 1080) * 0 + (15.6 * 25.4 / np.hypot(1920, 1080)),   # 15.6" 1920x1080 (HP Victus 15-fa2xxx IPS)
         "phone": 25.4 / 405.0}                                                                               # Moto G32, 6.5" 1080x2400 IPS LCD, ~405 ppi
F_MM = 5.56          # EXIF focal length of the main camera (Motorola Edge)
PX_EXIF_UM = 1.95    # sensor pixel estimated from EXIF (35 mm equivalent 24 mm -> 10 mm sensor diagonal; 4096 columns): an estimate
R_GRID = np.round(np.arange(0.10, 0.76, 0.01), 3)
TH_GRID = np.arange(-10, 10.01, 0.5)
_VALID = np.flatnonzero(masks.VALID.ravel())


def load_rows():
    rows = list(csv.DictReader(open(C.CACHE_DIR / "real_results.csv", encoding="utf-8")))
    for r in rows:
        for k in ("distance_cm", "peakiness", "chroma_peak", "p_screen"):
            r[k] = float(r[k])
    return rows


def crop_list(row, n, rng):
    im = ImageOps.exif_transpose(Image.open(REAL_DIR / row["file"])).convert("RGB")
    arr = np.asarray(im, dtype=np.float64) / 255.0
    y0, y1, x0, x1 = (int(v) for v in row["roi"].split("x"))
    out = []
    for _ in range(n):
        y, x = int(rng.integers(y0, y1 - N + 1)), int(rng.integers(x0, x1 - N + 1))
        out.append(arr[y:y + N, x:x + N])
    return out


def fit_lattice(RY, layout="lcd_rgb", sigma=0.4):
    """Best (score, r, theta_deg) of the predicted-peak template: free r and theta, known layout."""
    Rm = maximum_filter(RY, size=3, mode="wrap")
    base = np.median(RY.ravel()[_VALID])
    best = (-1e9, None, None)
    for r in R_GRID:
        for th in TH_GRID:
            rows, cols, _ = predicted_peaks(layout, r, np.deg2rad(th), sigma, top=12, masked=True, bayer=True)
            if len(rows) < 8:
                continue
            v = float(Rm[rows, cols].mean() - base)
            if v > best[0]:
                best = (v, float(r), float(th))
    return best


def main():
    rng = np.random.default_rng(C.SEED)
    rows = load_rows()
    out = {"pitch_mm": PITCH, "f_mm": F_MM, "px_exif_um": PX_EXIF_UM}

    # ---- 1. camera geometry from the laptop lattice at 12 and 20 cm --------------------------------
    fits = []
    for row in rows:
        if row["screen"] == "laptop" and row["distance_cm"] in (12.0, 20.0):
            rs, ths, scs = [], [], []
            for crop in crop_list(row, 5, rng):
                RY = detrended(luma(crop))
                sc, r, th = fit_lattice(RY)
                rs.append(r); ths.append(th); scs.append(sc)
            fits.append({"file": row["file"], "d": row["distance_cm"], "r_hat": float(np.median(rs)), "r_all": rs, "theta": float(np.median(ths)), "score": float(np.median(scs))})
            print(f"{row['file']:34s} r_hat per crop {np.round(rs, 2).tolist()}  -> median {np.median(rs):.2f}  (theta {np.median(ths):+.1f}, score {np.median(scs):.2f})")
    out["lattice_fits"] = fits
    px_est = {}
    for d in (12.0, 20.0):
        rh = [f["r_hat"] for f in fits if f["d"] == d]
        px_est[d] = float(np.median(rh) * PITCH["laptop"] * F_MM / (d * 10 - F_MM) * 1000)      # um
        pred = r_from_geometry(PITCH["laptop"], F_MM, d * 10, PX_EXIF_UM)
        print(f"d = {d:.0f} cm: measured r = {np.median(rh):.3f} (spread {np.min(rh):.2f}-{np.max(rh):.2f}), predicted from EXIF pixel {PX_EXIF_UM} um: {pred:.3f} -> effective pixel {px_est[d]:.2f} um")
    out["px_est_um"] = px_est
    px_use = float(np.mean(list(px_est.values())))
    out["px_used_um"] = px_use
    print(f"effective camera pixel used for r: {px_use:.2f} um (EXIF-based estimate {PX_EXIF_UM} um)")

    # ---- 2. r for every condition, simulated AUC at that r ------------------------------------------
    R = json.loads((C.CACHE_DIR / "results.json").read_text())
    e2 = R["E2"]["lcd_rgb"]
    table = []
    direct = [r["peakiness"] for r in rows if r["kind"] == "direct"]
    dmax = max(direct)
    for dev in ("laptop", "phone"):
        for d in (12, 20, 35, 50):
            g = [r for r in rows if r["kind"] == "screen" and r["screen"] == dev and r["distance_cm"] == d]
            if not g:
                continue
            r_use = r_from_geometry(PITCH[dev], F_MM, d * 10, px_use)
            r_exif = r_from_geometry(PITCH[dev], F_MM, d * 10, PX_EXIF_UM)
            pk = np.array([x["peakiness"] for x in g])
            table.append({"device": dev, "d_cm": d, "n": len(g), "r": r_use, "r_exif": r_exif, "sim_auc": float(np.interp(r_use, e2["r"], e2["auc"])),
                          "peak_mean": float(pk.mean()), "peak_min": float(pk.min()), "peak_max": float(pk.max()),
                          "n_above_direct_max": int((pk > dmax).sum())})
    out["table"] = table
    out["direct_peak_range"] = [min(direct), max(direct)]
    print(f"\ndirect photos peakiness range {min(direct):.2f}-{max(direct):.2f}")
    print(f"{'condition':16s} {'r':>5s} {'r(EXIF)':>7s} {'sim AUC':>7s} {'peakiness mean (range)':>26s} {'> direct max':>13s}")
    for t in table:
        print(f"{t['device']+' '+str(t['d_cm'])+' cm':16s} {t['r']:5.2f} {t['r_exif']:7.2f} {t['sim_auc']:7.2f} {t['peak_mean']:8.2f} ({t['peak_min']:.2f}-{t['peak_max']:.2f})   {t['n_above_direct_max']}/{t['n']}")

    # ---- 3. real vs simulated peakiness -------------------------------------------------------------
    z = np.load(C.CACHE_DIR / "E2.npz")
    lcd = z["layout_i"] == 0
    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    ax.scatter(z["r"][lcd], z["fr"][lcd, F_PEAK], s=8, c="#2a6fdb", alpha=0.25, label="simulation: screen photos (LCD)")
    bins = np.array(C.E2_R_CENTERS)
    med = [np.median(z["fr"][lcd & (z["bin"] == b), F_PEAK]) for b in range(len(bins))]
    rb = [np.median(z["r"][lcd & (z["bin"] == b)]) for b in range(len(bins))]
    ax.plot(rb, med, "-", c="#2a6fdb", lw=2, label="simulation: median")
    dsim = z["fd"][lcd, F_PEAK]
    ax.axhspan(np.percentile(dsim, 2.5), np.percentile(dsim, 97.5), color="gray", alpha=0.15, label="simulation: direct photos (95%)")
    for dev, col, mk in (("laptop", "#c2307f", "o"), ("phone", "#e07b00", "s")):
        xs = [t["r"] for t in table if t["device"] == dev for _ in range(1)]
        for t in table:
            if t["device"] == dev:
                ys = [x["peakiness"] for x in rows if x["kind"] == "screen" and x["screen"] == dev and x["distance_cm"] == t["d_cm"]]
                ax.scatter([t["r"]] * len(ys), ys, c=col, marker=mk, s=42, edgecolor="k", linewidth=0.6, zorder=5,
                           label=("real: HP Victus laptop (141 ppi)" if dev == "laptop" else "real: Moto G32 (405 ppi LCD)") if t["d_cm"] == (12) else None)
    ax.axhline(min(direct), c="k", ls=":", lw=1); ax.axhline(max(direct), c="k", ls=":", lw=1, label="real direct photos (range)")
    ax.set_xlim(0.1, 2.3); ax.set_xlabel("r = camera pixel / screen pixel (from real pixel pitches and distances)"); ax.set_ylabel("spectral peakiness")
    ax.set_title("Real photos on the simulation's curve (same feature code)"); ax.legend(fontsize=7.5, loc="upper right")
    fig.tight_layout(); fig.savefig(C.FIGS_DIR / "real_vs_sim.png", dpi=200); plt.close(fig)

    # ---- 4. predicted peaks on real spectra --------------------------------------------------------
    fig, axs = plt.subplots(1, 4, figsize=(12.5, 3.6))
    hits = {}
    for ax, (dev, d) in zip(axs, (("laptop", 12), ("laptop", 20), ("laptop", 35), ("phone", 12))):
        row = next(x for x in rows if x["screen"] == dev and x["distance_cm"] == d and x["file"].endswith("A_1.jpg"))
        crop = crop_list(row, 1, np.random.default_rng(1))[0]
        RY = detrended(luma(crop))
        sc, rh, th = fit_lattice(RY, "lcd_rgb")
        rows_p, cols_p, amp = predicted_peaks("lcd_rgb", rh, np.deg2rad(th), 0.4, top=12, masked=True, bayer=True)
        Rm = maximum_filter(RY, size=3, mode="wrap")
        thr = np.percentile(RY.ravel()[_VALID], 99)
        n_hit = int((Rm[rows_p, cols_p] > thr).sum())
        chance = float((Rm.ravel()[_VALID] > thr).mean())
        hits[f"{dev}_{d}cm"] = {"r_hat": rh, "theta": th, "n_peaks": len(rows_p), "hits_above_p99": n_hit, "chance_rate": chance}
        ax.imshow(RY, cmap="magma", vmin=-1, vmax=6, interpolation="nearest")
        for k, (a, b) in enumerate(zip(rows_p, cols_p)):
            ax.add_patch(plt.Circle((b, a), 6, fill=False, color="#3ee8ff", lw=1.8 if k < 4 else 1.0))
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{dev} {d} cm: fitted r={rh:.2f}\n{n_hit}/{len(rows_p)} predicted peaks on a bright spot", fontsize=8.5)
        print(f"{dev} {d} cm: fitted r = {rh:.2f}, theta = {th:+.1f}, {n_hit}/{len(rows_p)} predicted peaks above the 99th percentile (a random bin: {100 * chance:.1f}% after 3x3 max)")
    out["peak_hits"] = hits
    # fair baseline: the same template fit applied to EVERY image, lattice present (laptop 12/20 cm) vs absent (everything else + direct)
    grp = {"lattice resolved (laptop 12, 20 cm)": [], "no lattice (laptop 35/50, phone, direct)": []}
    rng2 = np.random.default_rng(7)
    for row in rows:
        if row["kind"] == "direct":
            im = ImageOps.exif_transpose(Image.open(REAL_DIR / row["file"])).convert("RGB")
            arr = np.asarray(im, dtype=np.float64) / 255.0
            H, W = arr.shape[:2]
            y, x = int(rng2.integers(H // 5, H * 4 // 5 - N)), int(rng2.integers(W // 5, W * 4 // 5 - N))
            crop = arr[y:y + N, x:x + N]
        else:
            crop = crop_list(row, 1, rng2)[0]
        RY = detrended(luma(crop))
        sc, rh, th = fit_lattice(RY, "lcd_rgb")
        rows_p, cols_p, _ = predicted_peaks("lcd_rgb", rh, np.deg2rad(th), 0.4, top=12, masked=True, bayer=True)
        Rm = maximum_filter(RY, size=3, mode="wrap")
        n_hit = int((Rm[rows_p, cols_p] > np.percentile(RY.ravel()[_VALID], 99)).sum())
        key = "lattice resolved (laptop 12, 20 cm)" if (row["screen"] == "laptop" and row["distance_cm"] in (12.0, 20.0)) else "no lattice (laptop 35/50, phone, direct)"
        grp[key].append((n_hit, sc))
    out["fit_baseline"] = {k: {"n": len(v), "hits_mean": float(np.mean([a for a, _ in v])), "hits_min": int(min(a for a, _ in v)), "hits_max": int(max(a for a, _ in v)),
                               "score_mean": float(np.mean([b for _, b in v])), "score_min": float(min(b for _, b in v)), "score_max": float(max(b for _, b in v))} for k, v in grp.items()}
    for k, v in out["fit_baseline"].items():
        print(f"template fit on {k}: n={v['n']}, predicted peaks on bright bins {v['hits_mean']:.1f}/12 (range {v['hits_min']}-{v['hits_max']}), fit score mean {v['score_mean']:.2f} (range {v['score_min']:.2f}-{v['score_max']:.2f})")
    fig.suptitle("Theory-predicted moire peaks (circles) on real spectra: pattern fitted with two free numbers (r, angle)", fontsize=10)
    fig.tight_layout(); fig.savefig(C.FIGS_DIR / "real_peaks.png", dpi=200); plt.close(fig)

    (C.CACHE_DIR / "real_geometry.json").write_text(json.dumps(out, indent=1))
    print("wrote cache/real_geometry.json, figs/real_vs_sim.png, figs/real_peaks.png")


if __name__ == "__main__":
    main()
