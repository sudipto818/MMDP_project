"""Static figures for the report and slides (PNG, 200 dpi) -> figs/. Reads cache/results.json and site/img/ (made by precompute.py)."""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import config as C
from core import theory
from core.layouts import LAYOUT_LABEL

plt.rcParams.update({"figure.dpi": 100, "savefig.dpi": 200, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "legend.frameon": False})
R = json.loads((C.CACHE_DIR / "results.json").read_text())
E1, E2, E3, E4, E5, E6 = (R[k] for k in ("E1", "E2", "E3", "E4", "E5", "E6"))
COL = {"lcd_rgb": "#2a6fdb", "pentile": "#e07b00", "laptop_lcd": "#2a6fdb", "monitor_lcd": "#2a9d6f", "phone_oled": "#c2307f"}
SHORT = {"laptop_lcd": "Laptop LCD", "monitor_lcd": "Monitor LCD", "phone_oled": "Phone OLED"}
OUT = C.FIGS_DIR
OUT.mkdir(exist_ok=True)
r90 = {l: E2[l]["r90_measured"] for l in C.LAYOUT_NAMES}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("  wrote", name)


def bands(ax):
    for i, (k, d) in enumerate(E1["devices"].items()):
        ax.axvspan(d["r_min"], d["r_max"], color=COL[k], alpha=0.10)
        ax.text((d["r_min"] + d["r_max"]) / 2, 1.012 + 0.03 * i, SHORT[k], ha="center", va="bottom", fontsize=8, color=COL[k])


# 1. pipeline examples ---------------------------------------------------------------------------------
def fig_examples():
    picks = [("lcd_rgb", 2), ("pentile", 2), ("pentile", 9)]
    fig, axs = plt.subplots(len(picks), 4, figsize=(11, 8.6))
    for i, (layout, k) in enumerate(picks):
        tag = f"ex_{layout}_{k:02d}"
        ex = next(e for e in json.loads(json.dumps(R.get("_examples", [])))) if False else None
        r = float(np.geomspace(0.25, 2.4, 12)[k])
        imgs = [("subpixels", f"{tag}_sub.png"), ("photo of the screen", f"{tag}_rec.png"), ("photo of the real scene", f"{tag}_dir.png"),
                ("spectrum of the screen photo", f"{tag}_spec.png")]
        for j, (title, fn) in enumerate(imgs):
            ax = axs[i, j]
            ax.imshow(Image.open(C.SITE_DIR / "img" / fn), interpolation="nearest")
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
            ax.set_title(title if i == 0 else "", fontsize=9)
            if j == 0:
                ax.set_ylabel(f"{LAYOUT_LABEL[layout]}\nr = {r:.2f}", fontsize=9)
            if j == 3:
                rows, cols, amp = theory.predicted_peaks(layout, r, np.deg2rad(2.0), 0.4, top=8)
                for p, (a, b) in enumerate(zip(rows, cols)):
                    ax.add_patch(plt.Circle((b, a), 6.5, fill=False, color="#3ee8ff", lw=1.8 if p < 3 else 1.0))
    fig.suptitle("Same simulator, same exposure: a photo of a screen against a photo of the scene (circles = predicted moiré peaks)", fontsize=11)
    save(fig, "fig1_examples.png")


# 2. layouts and reciprocal lattices -------------------------------------------------------------------
def fig_layouts():
    fig, axs = plt.subplots(2, 2, figsize=(9, 8))
    for j, layout in enumerate(C.LAYOUT_NAMES):
        ax = axs[0, j]
        from core.layouts import emission_finegrid
        E = emission_finegrid(np.ones((4, 4, 3)) * np.array([1, 1, 1]), layout, 24)
        E = E / E.max()
        ax.imshow(np.clip(E ** 0.6, 0, 1), interpolation="nearest"); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        ax.set_title(f"{LAYOUT_LABEL[layout]}: 4×4 pixels")
        H = theory.layout_harmonics(layout)
        ax = axs[1, j]
        m = (np.abs(H["fx"]) <= 3) & (np.abs(H["fy"]) <= 3)
        sc = ax.scatter(H["fx"][m], H["fy"][m], s=900 * H["amp"][m] ** 1.2 + 4, c=H["amp"][m], cmap="viridis", edgecolor="none")
        half = m & ((np.abs(H["fx"] % 1) > 1e-9) | (np.abs(H["fy"] % 1) > 1e-9)) & (H["amp"] > 0.01)
        ax.scatter(H["fx"][half], H["fy"][half], s=60, facecolor="none", edgecolor="red", lw=1.4, label="half-integer harmonic")
        ax.set_xlabel("fx (cycles per screen pixel)"); ax.set_ylabel("fy"); ax.set_aspect("equal"); ax.set_title("Fourier harmonics (marker size = amplitude)")
        if half.any():
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), fontsize=8)
    save(fig, "fig2_layouts_and_harmonics.png")


# 3. E1 -----------------------------------------------------------------------------------------------
def fig_E1():
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    ks = list(E1["devices"]); x = np.arange(len(ks)); w = 0.36
    for off, tag, lab, col in ((-w / 2, "A", "A: trained on LCD screens only", "#2a6fdb"), (w / 2, "B", "B: trained on all three screens", "#e07b00")):
        v = np.array([E1["devices"][k][f"auc_{tag}"] for k in ks]); ci = np.array([E1["devices"][k][f"ci_{tag}"] for k in ks])
        ax.bar(x + off, v, w, color=col, label=lab, yerr=[v - ci[:, 0], ci[:, 1] - v], capsize=3)
        for xi, vi in zip(x + off, v):
            ax.text(xi, vi + 0.03, f"{vi:.2f}", ha="center", fontsize=8)
    ax.axhline(0.5, ls="--", c="gray", label="chance (0.5)")
    ax.set_xticks(x); ax.set_xticklabels([f"{SHORT[k]}\nr = {E1['devices'][k]['r_min']:.2f}-{E1['devices'][k]['r_max']:.2f}" for k in ks])
    ax.set_ylim(0.4, 1.26); ax.set_ylabel("AUC on test scenes"); ax.legend(loc="upper right", ncol=3, fontsize=7.5)
    ax.set_title(f"E1: photos at 15-40 cm. Phone-OLED screen photos stay close to chance ({E1['devices']['phone_oled']['auc_B']:.2f})", fontsize=10)
    save(fig, "fig3_E1_oled_gap.png")


# 4. E2 -----------------------------------------------------------------------------------------------
def fig_E2():
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    bands(ax)
    for l in C.LAYOUT_NAMES:
        e = E2[l]; ax.plot(e["r"], e["auc"], "o-", c=COL[l], label=LAYOUT_LABEL[l])
        ax.fill_between(e["r"], e["ci_lo"], e["ci_hi"], color=COL[l], alpha=0.18)
        ax.axvline(r90[l], c=COL[l], ls=":", lw=1.2)
    ax.axhline(0.5, ls="--", c="gray"); ax.axhline(0.9, ls="--", c="gray", lw=0.7)
    ax.set_xlim(0.1, 2.5); ax.set_ylim(0.4, 1.11); ax.set_xlabel("r = camera pixel / screen pixel"); ax.set_ylabel("AUC (screen photo vs real photo)")
    E7 = R.get("E7")
    if E7:
        for l in C.LAYOUT_NAMES:
            ax.plot(E7["r"], E7["auc_A"][l], "--", c=COL[l], lw=1.4, marker="x", ms=5, label=f"LCD-trained detector on {LAYOUT_LABEL[l]}")
    ax.legend(loc="center right", fontsize=8); ax.set_title(f"E2/E7: matched r. r90 = {r90['lcd_rgb']:.2f} (LCD), {r90['pentile']:.2f} (PenTile); dashed = LCD-trained detector", fontsize=9.5)
    save(fig, "fig4_E2_matched_r.png")


# 5. E3 -----------------------------------------------------------------------------------------------
def fig_E3():
    from core.stats import curve_value
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, (name, key, ttl) in zip(axs, (("theory_bayer", "theory_amp_bayer", "lens x Bayer demosaic theory"), ("theory_mtf", "theory_amp_mtf", "lens-only theory"))):
        xs_all = []
        for l in C.LAYOUT_NAMES:
            x = np.log10(np.maximum(E2[l][key], 1e-6)); xs_all += list(x)
            ax.scatter(x, E2[l]["auc"], c=COL[l], label=LAYOUT_LABEL[l], zorder=3)
        xx = np.linspace(min(xs_all) - 0.2, max(xs_all) + 0.2, 200)
        p = E3[name]; ax.plot(xx, curve_value(xx, p["c"], p["s"]), "k--", label=f"fit, R² = {p['r2']:.3f}")
        ax.axhline(0.5, ls=":", c="gray"); ax.set_xlabel("log10 predicted strongest moiré amplitude"); ax.set_ylabel("measured AUC"); ax.set_title(ttl); ax.legend(loc="lower right")
    fig.suptitle(f"E3: one curve for both layouts. R² with r alone: {E3['r_only']['r2']:.3f}", fontsize=11)
    save(fig, "fig5_E3_theory_vs_measurement.png")


# 6. E4 -----------------------------------------------------------------------------------------------
def fig_E4():
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for key, col, lab, ls in (("logistic", "#2a6fdb", "logistic on spectral signature (scene-grouped CV)", "-"), ("known", "#2a9d6f", "template at known geometry (no training)", "-"),
                              ("template", "#c2307f", "free-search template (negative result)", "--")):
        ax.plot(E4["r"], E4[f"acc_{key}"], "o" + ls, c=col, label=lab)
        if key != "template":
            ci = np.array(E4[f"ci_{key}"]); ax.fill_between(E4["r"], ci[:, 0], ci[:, 1], color=col, alpha=0.15)
    if "acc_chroma" in E4:
        ax.plot(E4["r"], E4["acc_chroma"], ":", c="#e07b00", lw=1.6, label="logistic, chroma signature only")
        ax.plot(E4["r"], E4["acc_luma"], ":", c="gray", lw=1.6, label="logistic, luma signature only")
    ax.axhline(0.5, ls="--", c="gray"); ax.set_xlabel("r"); ax.set_ylabel("accuracy: LCD vs PenTile"); ax.set_ylim(0.2, 1.05); ax.legend(loc="lower left", fontsize=8)
    ax.set_title("E4: which screen was it?")
    save(fig, "fig6_E4_layout_identification.png")


# 7. E5 -----------------------------------------------------------------------------------------------
def fig_E5():
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    for k, d in E5["devices"].items():
        ax.plot(d["dist_cm"], d["binned"]["r"], c=COL[k], label=f"{SHORT[k]}, binned 2 µm")
        ax.plot(d["dist_cm"], d["full"]["r"], c=COL[k], ls="--", label=f"{SHORT[k]}, full-res 1 µm")
    top = max(r90.values())
    ax.axhspan(0, top, color="#1b8a5a", alpha=0.12); ax.axhline(r90["lcd_rgb"], c=COL["lcd_rgb"], ls=":"); ax.axhline(r90["pentile"], c=COL["pentile"], ls=":")
    ax.text(59, top + 0.04, "screen photo detectable (AUC >= 0.9)", ha="right", fontsize=8)
    ax.set_ylim(0, 2.6); ax.set_xlim(10, 60); ax.set_xlabel("distance (cm)"); ax.set_ylabel("r"); ax.legend(fontsize=7, loc="upper left", ncol=2)
    dm = E5["devices"]
    ax.set_title(f"E5: max detectable distance, phone OLED {dm['phone_oled']['binned']['max_detect_cm']:.0f} / {dm['phone_oled']['full']['max_detect_cm']:.0f} cm (binned / full-res)")
    save(fig, "fig7_E5_defence_rule.png")


# 8. E6 -----------------------------------------------------------------------------------------------
def fig_E6():
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(E6["r"])); w = 0.13
    for i, (l, ci) in enumerate([(l, ci) for l in C.LAYOUT_NAMES for ci in range(3)]):
        ax.bar(x + (i - 2.5) * w, E6["auc"][l][ci], w, color=COL[l], alpha=[1.0, 0.65, 0.35][ci], label=f"{LAYOUT_LABEL[l]}, {E6['conditions'][ci]}")
    ax.axhline(0.5, ls="--", c="gray"); ax.set_xticks(x); ax.set_xticklabels([f"r = {r}" for r in E6["r"]]); ax.set_ylim(0.4, 1.05); ax.set_ylabel("AUC")
    ax.legend(fontsize=7, ncol=2, loc="upper right"); ax.set_title("E6: sharpening and strong JPEG do not resurrect traces beyond r ~ 0.9")
    save(fig, "fig8_E6_robustness.png")


if __name__ == "__main__":
    print("writing figures to", OUT)
    for f in (fig_examples, fig_layouts, fig_E1, fig_E2, fig_E3, fig_E4, fig_E5, fig_E6):
        f()
