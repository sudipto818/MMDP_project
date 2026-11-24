"""Run experiments E1-E6 and export everything the website and the figures need.

    python precompute.py --quick            # about a third of the data, to test the pipeline
    python precompute.py --jobs 10          # full run
    python precompute.py --only E1,E2 --force

Results: cache/E*.npz (features + parameters), cache/results[_quick].json, site/data/data.js (+ images).
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")          # one BLAS thread per worker process: avoids oversubscribing the CPU
import argparse
import base64
import json
import sys
import time

import numpy as np
from multiprocessing import Pool
from PIL import Image
from tqdm import tqdm

import config as C
from core import scenes, theory
from core.colour import luma
from core.features import (F_PEAK, F_CPEAK, F_TL, F_TP, F_SIG, F_KL, F_KP, FEATURE_NAMES, features_all, detrended,
                           R_GRID)
from core.render import subpixel_preview, sigma_screen
from core.sample import run_task, random_params, make_pair
from core.stats import (logistic_irls, predict_proba, standardize_fit, standardize_apply, auc, auc_boot_ci,
                        fit_auc_curve, curve_value, curve_inverse)

DET_IDX = [F_PEAK, F_CPEAK, F_TL, F_TP]            # features of the recapture detectors in E1
DEVICE_KEYS = list(C.DEVICES)
LAYOUT_IDX = {l: i for i, l in enumerate(C.LAYOUT_NAMES)}
BASE = {"E1": 10_000, "E2": 20_000, "E6": 30_000, "EX": 40_000, "QZ": 50_000, "E7": 60_000}


# ============================================================================== infrastructure
def sz(pair, quick):
    return pair[1] if quick else pair[0]


def run_tasks(tasks, jobs, desc):
    """Run make_pair + features on all tasks in a process pool. Returns (feat_rec, feat_dir, mean_ratio)."""
    t0 = time.time()
    out = [None] * len(tasks)
    if jobs <= 1:
        for k, t in enumerate(tqdm(tasks, desc=desc, file=sys.stderr)):
            out[k] = run_task(t)
    else:
        with Pool(jobs) as pool:
            for k, res in enumerate(tqdm(pool.imap(run_task, tasks, chunksize=4), total=len(tasks), desc=desc, file=sys.stderr)):
                out[k] = res
    fr = np.stack([o[1] for o in out]); fd = np.stack([o[2] for o in out]); mr = np.array([o[3] for o in out])
    print(f"   {desc}: {len(tasks)} pairs ({2 * len(tasks)} captures) in {time.time() - t0:.0f}s "
          f"({(time.time() - t0) / (2 * len(tasks)):.3f} s per capture, wall clock)", flush=True)
    return fr, fd, mr


def cache_path(name, quick):
    return C.CACHE_DIR / f"{name}{'_quick' if quick else ''}.npz"


def save_cache(name, quick, fr, fd, mr, meta):
    np.savez_compressed(cache_path(name, quick), fr=fr, fd=fd, mr=mr, **{k: np.asarray(v) for k, v in meta.items()})


def load_cache(name, quick):
    z = np.load(cache_path(name, quick), allow_pickle=False)
    return {k: z[k] for k in z.files}


def mk_task(layout, scene, p, seed):
    return {"layout": layout, "scene": int(scene), "r": p["r"], "theta": p["theta"], "sigma": p["sigma"],
            "q": p["q"], "sharpen": p["sharpen"], "seed": int(seed)}


def pair_auc(sc_rec, sc_dir, n_boot=C.N_BOOT, rng=None):
    s = np.r_[sc_rec, sc_dir]
    y = np.r_[np.ones(len(sc_rec)), np.zeros(len(sc_dir))].astype(int)
    pid = np.r_[np.arange(len(sc_rec)), np.arange(len(sc_dir))]
    a = auc(s, y)
    lo, hi = auc_boot_ci(s, y, n_boot, rng or np.random.default_rng(0), pair_ids=pid) if len(sc_rec) >= 8 else (float("nan"),) * 2
    return float(a), float(lo), float(hi)


def det_X(fr, fd):
    X = np.vstack([fr[:, DET_IDX], fd[:, DET_IDX]])
    y = np.r_[np.ones(len(fr)), np.zeros(len(fd))]
    return X, y


# ============================================================================== E1: the OLED gap
def run_E1(quick, jobs, force):
    if cache_path("E1", quick).exists() and not force:
        return load_cache("E1", quick)
    n = sz(C.E1_PAIRS_PER_DEVICE, quick)
    tasks, meta = [], {k: [] for k in ["dev", "d_cm", "split"]}
    idx = BASE["E1"]
    f_mm, px = C.CAMERA["f_mm"], C.CAMERA["px_um"]["binned"]
    for di, dk in enumerate(DEVICE_KEYS):
        dev = C.DEVICES[dk]
        for p in range(n):
            rng = np.random.default_rng([C.SEED, 1, idx])
            scene = rng.choice(C.TRAIN_SCENES) if p % 3 < 2 else rng.choice(C.TEST_SCENES)
            d_cm = rng.uniform(*C.DIST_CM)
            r = theory.r_from_geometry(dev["pitch_mm"], f_mm, d_cm * 10, px)
            tasks.append(mk_task(dev["layout"], scene, random_params(rng, r), C.SEED * 100000 + idx))
            meta["dev"].append(di); meta["d_cm"].append(d_cm); meta["split"].append(int(scene in C.TEST_SCENES))
            idx += 1
    fr, fd, mr = run_tasks(tasks, jobs, "E1 OLED gap")
    meta.update({k: [t[k] for t in tasks] for k in ["r", "theta", "sigma", "q", "scene", "seed"]})
    save_cache("E1", quick, fr, fd, mr, meta)
    return load_cache("E1", quick)


def analyse_E1(z):
    fr, fd, dev, split = z["fr"], z["fd"], z["dev"], z["split"]
    res = {"devices": {}}
    lcd = [DEVICE_KEYS.index("laptop_lcd"), DEVICE_KEYS.index("monitor_lcd")]
    tr = split == 0

    def fit(mask):
        X, y = det_X(fr[mask], fd[mask])
        mu, sd = standardize_fit(X)
        return mu, sd, logistic_irls(standardize_apply(X, mu, sd), y, l2=1.0)

    detA = fit(tr & np.isin(dev, lcd))
    detB = fit(tr)
    res["detector_B"] = {"features": [FEATURE_NAMES[i] for i in DET_IDX], "mu": detB[0].tolist(), "sd": detB[1].tolist(),
                         "w": detB[2].tolist()}
    res["detector_A"] = {"mu": detA[0].tolist(), "sd": detA[1].tolist(), "w": detA[2].tolist()}
    for di, dk in enumerate(DEVICE_KEYS):
        te = (dev == di) & (split == 1)
        allp = dev == di
        entry = {"label": C.DEVICES[dk]["label"], "layout": C.DEVICES[dk]["layout"], "n_test": int(te.sum()),
                 "r_min": float(z["r"][allp].min()), "r_max": float(z["r"][allp].max()), "r_median": float(np.median(z["r"][allp]))}
        for tag, det in (("A", detA), ("B", detB)):
            mu, sd, w = det
            sr = predict_proba(w, standardize_apply(fr[te][:, DET_IDX], mu, sd))
            sdr = predict_proba(w, standardize_apply(fd[te][:, DET_IDX], mu, sd))
            a, lo, hi = pair_auc(sr, sdr)
            entry[f"auc_{tag}"], entry[f"ci_{tag}"] = a, [lo, hi]
        a, lo, hi = pair_auc(fr[allp, F_PEAK], fd[allp, F_PEAK])
        entry["auc_raw_all"], entry["ci_raw_all"] = a, [lo, hi]
        # AUC against distance (raw peakiness, no training)
        edges = np.linspace(C.DIST_CM[0], C.DIST_CM[1], 6)
        bins = []
        for lo_e, hi_e in zip(edges[:-1], edges[1:]):
            m = allp & (z["d_cm"] >= lo_e) & (z["d_cm"] <= hi_e)
            if m.sum() >= 8:
                a, l, h = pair_auc(fr[m, F_PEAK], fd[m, F_PEAK], n_boot=300)
                bins.append({"d_lo": float(lo_e), "d_hi": float(hi_e), "r_mid": float(np.median(z["r"][m])), "auc": a, "ci": [l, h], "n": int(m.sum())})
        entry["by_distance"] = bins
        res["devices"][dk] = entry
    return res


# ============================================================================== E2: matched r control
def run_E2(quick, jobs, force):
    if cache_path("E2", quick).exists() and not force:
        return load_cache("E2", quick)
    n = sz(C.E2_PAIRS_PER_BIN, quick)
    tasks, meta = [], {k: [] for k in ["layout_i", "bin"]}
    idx = BASE["E2"]
    for li, layout in enumerate(C.LAYOUT_NAMES):
        for b, c in enumerate(C.E2_R_CENTERS):
            for _ in range(n):
                rng = np.random.default_rng([C.SEED, 2, idx])
                scene = int(rng.integers(1, C.N_KODAK + 1))
                r = rng.uniform(c - C.E2_R_HALFWIDTH, c + C.E2_R_HALFWIDTH)
                tasks.append(mk_task(layout, scene, random_params(rng, r), C.SEED * 100000 + idx))
                meta["layout_i"].append(li); meta["bin"].append(b)
                idx += 1
    fr, fd, mr = run_tasks(tasks, jobs, "E2 matched-r control")
    meta.update({k: [t[k] for t in tasks] for k in ["r", "theta", "sigma", "q", "scene", "seed"]})
    save_cache("E2", quick, fr, fd, mr, meta)
    return load_cache("E2", quick)


def theory_amps(z, bayer):
    return np.array([theory.theory_amp(C.LAYOUT_NAMES[li], r, s, np.deg2rad(t), masked=True, bayer=bayer)
                     for li, r, s, t in zip(z["layout_i"], z["r"], z["sigma"], z["theta"])])


def first_below(r, a, thr):
    """r where the (descending) curve a(r) first drops below thr, by linear interpolation; nan if never."""
    for i in range(1, len(r)):
        if a[i - 1] >= thr > a[i]:
            return float(r[i - 1] + (a[i - 1] - thr) / (a[i - 1] - a[i]) * (r[i] - r[i - 1]))
    return float("nan") if a[-1] >= thr else float(r[0])


def analyse_E2_E3(z):
    nb = len(C.E2_R_CENTERS)
    ta_b, ta_n = theory_amps(z, True), theory_amps(z, False)
    out = {"E2": {}, "E3": {}}
    pts = []
    for li, layout in enumerate(C.LAYOUT_NAMES):
        rows = {"r": [], "auc": [], "ci_lo": [], "ci_hi": [], "auc_template": [], "theory_amp_bayer": [], "theory_amp_mtf": [], "n": []}
        for b in range(nb):
            m = (z["layout_i"] == li) & (z["bin"] == b)
            a, lo, hi = pair_auc(z["fr"][m, F_PEAK], z["fd"][m, F_PEAK])
            tm = lambda f: np.maximum(f[:, F_TL], f[:, F_TP])
            at, _, _ = pair_auc(tm(z["fr"][m]), tm(z["fd"][m]), n_boot=1)
            rows["r"].append(float(np.median(z["r"][m]))); rows["auc"].append(a); rows["ci_lo"].append(lo); rows["ci_hi"].append(hi)
            rows["auc_template"].append(at); rows["n"].append(int(m.sum()))
            rows["theory_amp_bayer"].append(float(np.median(ta_b[m]))); rows["theory_amp_mtf"].append(float(np.median(ta_n[m])))
            pts.append((li, rows["r"][-1], a, rows["theory_amp_bayer"][-1], rows["theory_amp_mtf"][-1]))
        rows["r90_measured"] = first_below(np.array(rows["r"]), np.array(rows["auc"]), 0.9)
        rows["r60_measured"] = first_below(np.array(rows["r"]), np.array(rows["auc"]), 0.6)
        out["E2"][layout] = rows
    P = np.array(pts)
    e3 = {}
    for name, x in (("theory_bayer", np.log10(np.maximum(P[:, 3], 1e-6))), ("theory_mtf", np.log10(np.maximum(P[:, 4], 1e-6))),
                    ("r_only", -P[:, 1])):
        try:
            c, s, r2 = fit_auc_curve(x, P[:, 2])
            e3[name] = {"c": c, "s": s, "r2": r2}
            for li, layout in enumerate(C.LAYOUT_NAMES):                       # does one curve describe both layouts?
                mm = P[:, 0] == li
                e3[name][f"r2_{layout}"] = float(1 - ((P[mm, 2] - curve_value(x[mm], c, s)) ** 2).sum()
                                                  / max(((P[mm, 2] - P[mm, 2].mean()) ** 2).sum(), 1e-12))
        except Exception as ex:           # noqa: BLE001
            e3[name] = {"error": str(ex)}
    # Primary theory variant = the better pooled fit (highest R^2 of the two theory axes). NOTE: this rule was chosen AFTER seeing the fits
    # (the full run flipped the winner from lens-only to lens x Bayer); r alone gives nearly the same R^2, so nothing hinges on the choice.
    cands = {k: e3[k]["r2"] for k in ("theory_bayer", "theory_mtf") if "r2" in e3.get(k, {})}
    e3["primary"] = max(cands, key=cands.get)
    e3["primary_bayer"] = e3["primary"] == "theory_bayer"
    out["E3"] = e3
    # thresholds on the r axis from each fitted theory curve (median sigma, theta = 0)
    sig_med = float(np.median(z["sigma"]))
    grid = np.round(np.arange(0.2, 3.0, 0.02), 3)
    e3["sigma_median"] = sig_med
    e3["thresholds_by_variant"] = {}
    for name, bayer in (("theory_bayer", True), ("theory_mtf", False)):
        if "c" not in e3.get(name, {}):
            continue
        c, s = e3[name]["c"], e3[name]["s"]
        thr = {}
        for target in (0.9, 0.6):
            xt = curve_inverse(target, c, s)
            for layout in C.LAYOUT_NAMES:
                amps = np.array([theory.theory_amp(layout, r, sig_med, 0.0, True, bayer) for r in grid])
                above = np.flatnonzero(np.log10(np.maximum(amps, 1e-9)) >= xt)      # last r where the peak is still strong enough
                thr[f"r_at_auc{int(target * 100)}_{layout}"] = float(grid[above[-1]]) if len(above) else float("nan")   # (ignores dips caused by masked bins)
        e3["thresholds_by_variant"][name] = thr
    e3["thresholds_from_theory"] = e3["thresholds_by_variant"].get(e3["primary"], {})
    return out


# ============================================================================== E4: which screen?
def analyse_E4(z):
    fr, li, rr, scene = z["fr"], z["layout_i"], z["r"], z["scene"]
    sig = fr[:, F_SIG:F_SIG + 64]
    # (a) logistic on the signature, 3-fold cross-validation grouped by scene (scene % 3)
    pred_a = np.zeros(len(li))
    fold_id = scene % 3
    for k in range(3):
        te, tr = fold_id == k, fold_id != k
        mu, sd = standardize_fit(sig[tr])
        w = logistic_irls(standardize_apply(sig[tr], mu, sd), li[tr].astype(float), l2=3.0)
        pred_a[te] = predict_proba(w, standardize_apply(sig[te], mu, sd))
    ok_a = (pred_a > 0.5) == (li == 1)

    def cv_acc(X):                       # same grouped CV with a sub-signature (luma-only or chroma-only)
        pr = np.zeros(len(li))
        for k in range(3):
            te, tr = fold_id == k, fold_id != k
            mu, sd = standardize_fit(X[tr])
            w = logistic_irls(standardize_apply(X[tr], mu, sd), li[tr].astype(float), l2=3.0)
            pr[te] = predict_proba(w, standardize_apply(X[te], mu, sd))
        return (pr > 0.5) == (li == 1)
    ok_luma, ok_chroma = cv_acc(sig[:, :32]), cv_acc(sig[:, 32:])
    # (b) template classifier, no training: compare the two template scores
    ok_b = (fr[:, F_TP] > fr[:, F_TL]) == (li == 1)
    # (c) known-geometry template test (r and theta from device specs): compare the two layouts' scores at the true geometry
    ok_c = (fr[:, F_KP] > fr[:, F_KL]) == (li == 1)
    # r_hat of the winning free-search template
    rhat = np.where(fr[:, F_TP] > fr[:, F_TL], fr[:, F_TP + 1], fr[:, F_TL + 1])
    bins = z["bin"]
    out = {"r": [], "acc_logistic": [], "acc_template": [], "acc_known": [], "ci_logistic": [], "ci_template": [], "ci_known": [],
           "acc_luma": [], "acc_chroma": [], "rhat_err_pct": [], "n": []}
    rng = np.random.default_rng(0)
    for b in range(len(C.E2_R_CENTERS)):
        m = bins == b
        out["r"].append(float(np.median(rr[m]))); out["n"].append(int(m.sum()))
        for tag, ok in (("logistic", ok_a), ("template", ok_b), ("known", ok_c)):
            v = ok[m].astype(float)
            boots = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(500)]
            out[f"acc_{tag}"].append(float(v.mean())); out[f"ci_{tag}"].append([float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))])
        out["acc_luma"].append(float(ok_luma[m].mean())); out["acc_chroma"].append(float(ok_chroma[m].mean()))
        mm = m & ok_b
        out["rhat_err_pct"].append(float(np.median(np.abs(rhat[mm] - rr[mm]) / rr[mm]) * 100) if mm.sum() else float("nan"))
    out["overall_logistic"] = float(ok_a.mean()); out["overall_template"] = float(ok_b.mean()); out["overall_known"] = float(ok_c.mean())
    return out


# ============================================================================== E5: defence rule
def analyse_E5(E2res):
    f_mm = C.CAMERA["f_mm"]
    res = {"r90_measured": {l: E2res["E2"][l]["r90_measured"] for l in C.LAYOUT_NAMES}, "devices": {}}
    d = np.arange(10, 61, 1.0)
    for dk, dev in C.DEVICES.items():
        r90 = res["r90_measured"][dev["layout"]]
        entry = {"label": dev["label"], "dist_cm": d.tolist()}
        for mode, px in C.CAMERA["px_um"].items():
            rs = [theory.r_from_geometry(dev["pitch_mm"], f_mm, x * 10, px) for x in d]
            dmax = theory.distance_from_r(dev["pitch_mm"], f_mm, r90, px) / 10 if np.isfinite(r90) else float("nan")
            entry[mode] = {"r": rs, "max_detect_cm": float(dmax)}
        res["devices"][dk] = entry
    return res


# ============================================================================== E6: robustness to the phone's processing
def run_E6(quick, jobs, force):
    if cache_path("E6", quick).exists() and not force:
        return load_cache("E6", quick)
    n = sz(C.E6_PAIRS_PER_BIN, quick)
    conds = [("baseline", 0.0, (75, 95)), ("sharpen", 0.5, (75, 95)), ("lowq", 0.0, (55, 70))]
    tasks, meta = [], {k: [] for k in ["layout_i", "cond", "rc"]}
    idx = BASE["E6"]
    for li, layout in enumerate(C.LAYOUT_NAMES):
        for ci, (cname, shp, qr) in enumerate(conds):
            for rci, rc in enumerate(C.E6_R_CENTERS):
                for _ in range(n):
                    rng = np.random.default_rng([C.SEED, 6, idx])
                    scene = int(rng.integers(1, C.N_KODAK + 1))
                    p = random_params(rng, rng.uniform(rc - 0.08, rc + 0.08), sharpen=shp)
                    p["q"] = int(rng.integers(qr[0], qr[1] + 1))
                    tasks.append(mk_task(layout, scene, p, C.SEED * 100000 + idx))
                    meta["layout_i"].append(li); meta["cond"].append(ci); meta["rc"].append(rci)
                    idx += 1
    fr, fd, mr = run_tasks(tasks, jobs, "E6 robustness")
    meta.update({k: [t[k] for t in tasks] for k in ["r", "theta", "sigma", "q", "scene", "seed"]})
    save_cache("E6", quick, fr, fd, mr, meta)
    return load_cache("E6", quick)


def analyse_E6(z):
    names = ["baseline", "sharpen 0.5", "JPEG q 55-70"]
    res = {"r": C.E6_R_CENTERS, "conditions": names, "auc": {}}
    for li, layout in enumerate(C.LAYOUT_NAMES):
        res["auc"][layout] = []
        for ci in range(3):
            row = []
            for rci in range(len(C.E6_R_CENTERS)):
                m = (z["layout_i"] == li) & (z["cond"] == ci) & (z["rc"] == rci)
                row.append(pair_auc(z["fr"][m, F_PEAK], z["fd"][m, F_PEAK], n_boot=1)[0])
            res["auc"][layout].append(row)
    return res



# ============================================================================== E7: does an LCD-trained detector transfer to PenTile at matched r?
def run_E7(quick, jobs, force):
    if cache_path("E7", quick).exists() and not force:
        return load_cache("E7", quick)
    n = sz(C.E2_PAIRS_PER_BIN, quick)
    tasks, meta = [], {k: [] for k in ["layout_i", "bin"]}
    idx = BASE["E7"]
    for li, layout in enumerate(C.LAYOUT_NAMES):
        for b, c in enumerate(C.E2_R_CENTERS):
            for _ in range(n):
                rng = np.random.default_rng([C.SEED, 7, idx])
                scene = int(rng.choice(C.TEST_SCENES))                       # test scenes only: no scene overlap with detector A's training set
                r = rng.uniform(c - C.E2_R_HALFWIDTH, c + C.E2_R_HALFWIDTH)
                tasks.append(mk_task(layout, scene, random_params(rng, r), C.SEED * 100000 + idx))
                meta["layout_i"].append(li); meta["bin"].append(b)
                idx += 1
    fr, fd, mr = run_tasks(tasks, jobs, "E7 detector transfer")
    meta.update({k: [t[k] for t in tasks] for k in ["r", "theta", "sigma", "q", "scene", "seed"]})
    save_cache("E7", quick, fr, fd, mr, meta)
    return load_cache("E7", quick)


def analyse_E7(z, detA):
    """AUC of detector A (trained on LCD-device photos in E1, train scenes only) on LCD and on PenTile pairs, per r bin."""
    mu, sd, w = (np.array(detA[k]) for k in ("mu", "sd", "w"))
    out = {"r": [], "n": [], "auc_A": {}, "ci_A": {}, "auc_raw": {}}
    for li, layout in enumerate(C.LAYOUT_NAMES):
        out["auc_A"][layout], out["ci_A"][layout], out["auc_raw"][layout] = [], [], []
    for b in range(len(C.E2_R_CENTERS)):
        out["r"].append(float(np.median(z["r"][z["bin"] == b])))
        out["n"].append(int(((z["bin"] == b) & (z["layout_i"] == 0)).sum()))
        for li, layout in enumerate(C.LAYOUT_NAMES):
            m = (z["layout_i"] == li) & (z["bin"] == b)
            sr = predict_proba(w, standardize_apply(z["fr"][m][:, DET_IDX], mu, sd))
            sdr = predict_proba(w, standardize_apply(z["fd"][m][:, DET_IDX], mu, sd))
            a, lo, hi = pair_auc(sr, sdr)
            out["auc_A"][layout].append(a); out["ci_A"][layout].append([lo, hi])
            out["auc_raw"][layout].append(pair_auc(z["fr"][m, F_PEAK], z["fd"][m, F_PEAK], n_boot=1)[0])
    return out

# ============================================================================== export for site and figures
def to_png(arr01, path):
    Image.fromarray((np.clip(arr01, 0, 1) * 255).round().astype(np.uint8)).save(path)


def spectrum_png(R, path):
    import matplotlib
    cm = matplotlib.colormaps["magma"]
    to_png(cm(np.clip((R + 1.0) / 7.0, 0, 1))[..., :3], path)


def export_site(res, quick):
    (C.SITE_DIR / "img").mkdir(parents=True, exist_ok=True)
    (C.SITE_DIR / "data").mkdir(parents=True, exist_ok=True)
    det = res["E1"]["detector_B"]
    mu, sd, w = np.array(det["mu"]), np.array(det["sd"]), np.array(det["w"])
    examples = []
    rs = np.geomspace(0.25, 2.4, 12)
    k = 0
    for layout in C.LAYOUT_NAMES:
        for i, r in enumerate(rs):
            seed = C.SEED * 100000 + BASE["EX"] + k
            scene = C.TEST_SCENES[k % len(C.TEST_SCENES)]
            rec, dr, info = make_pair(scenes.load_scene(scene), layout, float(r), 2.0, 0.4, 90, 0.0, seed, return_crop=True)
            fr_, Rr = features_all(rec); fd_, Rd = features_all(dr)
            tag = f"ex_{layout}_{i:02d}"
            to_png(rec, C.SITE_DIR / "img" / f"{tag}_rec.png"); to_png(dr, C.SITE_DIR / "img" / f"{tag}_dir.png")
            spectrum_png(Rr, C.SITE_DIR / "img" / f"{tag}_spec.png"); spectrum_png(Rd, C.SITE_DIR / "img" / f"{tag}_specdir.png")
            to_png(subpixel_preview(info["crop"], layout), C.SITE_DIR / "img" / f"{tag}_sub.png")
            rows, cols, amp = theory.predicted_peaks(layout, float(r), np.deg2rad(2.0), 0.4, top=12)
            p_rec = float(predict_proba(w, ((fr_[DET_IDX] - mu) / sd)[None])[0]); p_dir = float(predict_proba(w, ((fd_[DET_IDX] - mu) / sd)[None])[0])
            examples.append({"id": tag, "layout": layout, "r": float(r), "theta": 2.0, "sigma": 0.4, "scene": int(scene),
                             "peaks": [[int(a), int(b), float(c)] for a, b, c in zip(rows, cols, amp)],
                             "p_detect_screen": p_rec, "p_detect_direct": p_dir,
                             "tmpl_lcd": float(fr_[F_TL]), "tmpl_pent": float(fr_[F_TP]),
                             "peakiness_screen": float(fr_[F_PEAK]), "peakiness_direct": float(fd_[F_PEAK])})
            k += 1
    quiz = []
    for q in range(10):
        rng = np.random.default_rng([C.SEED, 9, q])
        layout = C.LAYOUT_NAMES[q % 2] if q < 4 else C.LAYOUT_NAMES[int(rng.integers(0, 2))]
        r = float(rng.uniform(0.25, 0.7))
        rec, _, _ = make_pair(scenes.load_scene(int(rng.integers(1, 25))), layout, r, float(rng.uniform(-5, 5)), 0.35, 92, 0.0,
                              C.SEED * 100000 + BASE["QZ"] + q)
        _, R = features_all(rec)
        spectrum_png(R, C.SITE_DIR / "img" / f"quiz_{q}.png")
        quiz.append({"img": f"img/quiz_{q}.png", "answer": layout, "r": r})
    order = np.random.default_rng(3).permutation(len(quiz))
    quiz = [quiz[i] for i in order]
    # harmonics for the live demo
    harm = {}
    for layout in C.LAYOUT_NAMES:
        H = theory.layout_harmonics(layout)
        harm[layout] = {"fx": H["fx"].tolist(), "fy": H["fy"].tolist(), "amp": H["amp"].tolist(),
                        "re": H["cplx"].real.tolist(), "im": H["cplx"].imag.tolist()}
    # embedded scenes for the live simulator (file:// cannot read pixels from <img>)
    live = []
    for sid in (23, 22):
        im = scenes.load_scene(sid)
        H_, W_ = im.shape[:2]
        crop = im[H_ // 2 - 192:H_ // 2 + 192, W_ // 2 - 192:W_ // 2 + 192]
        live.append({"name": f"kodim{sid:02d}", "w": 384, "h": 384,
                     "b64": base64.b64encode((crop * 255).round().astype(np.uint8).tobytes()).decode()})
    # numeric reference vectors so the JS port can be checked against Python
    ref = []
    for layout in C.LAYOUT_NAMES:
        for r, th, s in [(0.3, 2.0, 0.3), (0.6, -3.0, 0.4), (1.1, 4.0, 0.5), (1.8, 0.0, 0.6)]:
            rows, cols, amp = theory.predicted_peaks(layout, r, np.deg2rad(th), s, top=6)
            ref.append({"layout": layout, "r": r, "theta": th, "sigma": s, "rows": rows.tolist(), "cols": cols.tolist(),
                        "amp": amp.tolist(), "theory_amp": theory.theory_amp(layout, r, s, np.deg2rad(th))})
    from core.render import render_screen, required_crop, render_scene
    from core.colour import srgb_to_linear
    sc = np.frombuffer(base64.b64decode(live[0]["b64"]), np.uint8).reshape(384, 384, 3) / 255.0
    lin = srgb_to_linear(sc)
    for layout, r, th, s in [("lcd_rgb", 0.5, 3.0, 0.4), ("pentile", 1.3, -2.0, 0.5)]:
        side = required_crop(r, np.deg2rad(th), s)
        i0 = (384 - side) // 2
        crop = lin[i0:i0 + side, i0:i0 + side]
        L = render_screen(crop, layout, r, np.deg2rad(th), s)
        ref.append({"render": True, "layout": layout, "r": r, "theta": th, "sigma": s, "side": side, "i0": i0,
                    "probe": [[int(a), int(b), L[a, b].tolist()] for a, b in [(10, 10), (64, 64), (100, 30), (127, 127), (33, 90)]],
                    "mean": L.mean(axis=(0, 1)).tolist()})
    from core.layouts import LAYOUTS
    from core import masks
    layouts = {k: [{"channel": s.channel, "x0": s.x0, "x1": s.x1, "y0": s.y0, "y1": s.y1, "gain": s.gain, "parity": s.parity}
                   for s in v] for k, v in LAYOUTS.items()}
    meta = {"devices": C.DEVICES, "camera": C.CAMERA, "dist_cm": C.DIST_CM, "out": C.OUT, "sigma_aperture": C.SIGMA_APERTURE,
            "sigma_lens": C.SIGMA_LENS, "quick": bool(quick)}
    data = {"meta": meta, "results": res, "examples": examples, "quiz": quiz, "harmonics": harm, "scenes": live, "reference": ref,
            "layouts": layouts, "reference_masks": {"sum": int(masks.MASK_ALL.sum()), "n_ring": int(masks.RING.max() + 1)}}
    (C.SITE_DIR / "data" / "data.js").write_text("window.DATA = " + json.dumps(data) + ";\n", encoding="utf-8")
    (C.SITE_DIR / "data" / "curves.json").write_text(json.dumps({"meta": meta, "results": res}, indent=1), encoding="utf-8")
    print(f"   exported site data: {len(examples)} examples, {len(quiz)} quiz items")


# ============================================================================== main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=4, help="4 is the measured optimum on a 4P+4E-core laptop; more workers get slower")
    ap.add_argument("--only", default="E1,E2,E6,E7,EX")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    C.CACHE_DIR.mkdir(exist_ok=True); C.FIGS_DIR.mkdir(exist_ok=True)
    only = set(a.only.split(","))
    t0 = time.time()
    res = {}
    rpath = C.CACHE_DIR / f"results{'_quick' if a.quick else ''}.json"
    if rpath.exists():
        res = json.loads(rpath.read_text())
    print(f"mode: {'QUICK' if a.quick else 'FULL'}, jobs={a.jobs}", flush=True)
    if "E1" in only:
        res["E1"] = analyse_E1(run_E1(a.quick, a.jobs, a.force)); print("   E1 done", flush=True)
    if "E2" in only:
        z2 = run_E2(a.quick, a.jobs, a.force)
        r23 = analyse_E2_E3(z2)
        res["E2"], res["E3"] = r23["E2"], r23["E3"]
        res["E4"] = analyse_E4(z2)
        res["E5"] = analyse_E5(r23)
        print("   E2-E5 done", flush=True)
    if "E6" in only:
        res["E6"] = analyse_E6(run_E6(a.quick, a.jobs, a.force)); print("   E6 done", flush=True)
    if "E7" in only and "E1" in res:
        res["E7"] = analyse_E7(run_E7(a.quick, a.jobs, a.force), res["E1"]["detector_A"]); print("   E7 done", flush=True)
    res["_run"] = {"quick": a.quick, "jobs": a.jobs, "seconds": round(time.time() - t0, 1)}
    rpath.write_text(json.dumps(res, indent=1))
    if "EX" in only and "E1" in res and "E2" in res:
        export_site(res, a.quick)
    print(f"total {time.time() - t0:.0f}s -> {rpath}")


if __name__ == "__main__":
    main()
