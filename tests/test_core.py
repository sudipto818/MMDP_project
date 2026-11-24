"""Acceptance tests. Run from the project root:  python -m pytest -q"""
import numpy as np
import pytest
from scipy.ndimage import maximum_filter
from skimage import data as skdata

import config as C
from core.colour import srgb_to_linear, linear_to_srgb, luma
from core.layouts import LAYOUTS, supercell
from core.render import (camera_grid, required_crop, random_crop, render_screen, render_scene,
                         render_screen_finegrid, sigma_screen)
from core.camera import camera_pipeline, bayer_demosaic
from core.theory import (layout_harmonics, to_camera_freq, fold, mtf, predicted_peaks, theory_amp,
                         r_from_geometry, distance_from_r)
from core import masks
from core.features import detrended, features_all, template_tables, FEATURE_NAMES, R_GRID
from core.stats import logistic_irls, predict_proba, auc, fit_auc_curve, curve_value, curve_inverse, auc_boot_ci
from core.sample import make_pair

ASTRO = skdata.astronaut().astype(float) / 255.0


def _crop(r, theta_deg, sigma, seed=0, img=ASTRO):
    th = np.deg2rad(theta_deg)
    side = required_crop(r, th, sigma)
    crop, _ = random_crop(srgb_to_linear(img), side, np.random.default_rng(seed))
    return crop, th


# 1 ------------------------------------------------------------------------------------------ colour
def test_colour_roundtrip():
    x = np.linspace(0, 1, 1001)
    assert np.max(np.abs(linear_to_srgb(srgb_to_linear(x)) - x)) < 1e-6


# 2 ------------------------------------------------------------------------------------------ layouts
@pytest.mark.parametrize("layout", ["lcd_rgb", "lcd_bgr", "pentile"])
def test_layout_preserves_mean(layout):
    E = supercell(layout, 60)
    assert E.shape == (3, 120, 120)
    for c in range(3):
        assert E[c].mean() == pytest.approx(1.0, rel=0.01)


# 3 ------------------------------------------------------------------------------------------ renderer
@pytest.mark.parametrize("layout", ["lcd_rgb", "pentile"])
@pytest.mark.parametrize("r", [0.4, 1.2])
def test_analytic_renderer_matches_fine_grid(layout, r):
    crop, th = _crop(r, 3.0, 0.4)
    a = render_screen(crop, layout, r, th, 0.4)
    b = render_screen_finegrid(crop, layout, r, th, 0.4, S=24 if r < 1 else 10)
    rel = np.sqrt(np.mean((a - b) ** 2)) / np.sqrt(np.mean(b ** 2))
    assert rel < 0.03, rel


def test_footprint_error_is_raised():
    crop, th = _crop(1.0, 0.0, 0.4)
    with pytest.raises(ValueError):
        render_screen(crop[40:-40, 40:-40], "lcd_rgb", 2.4, th, 0.4)


# 4 ------------------------------------------------------------------------------------------ frequency convention
def test_frequency_convention_and_fft_axes():
    r, theta_deg, sigma = 1.0, 10.0, 0.3
    th = np.deg2rad(theta_deg)
    side = required_crop(r, th, sigma)
    jj = np.arange(side)
    f_scr = (1 / 8, 0.0)                                      # a grating varying along x
    pat = 0.5 + 0.4 * np.cos(2 * np.pi * (f_scr[0] * jj[None, :] + f_scr[1] * jj[:, None]))
    crop = np.repeat(pat[..., None], 3, axis=2)
    L = render_scene(crop, r, th, sigma)
    img = luma(L)
    F = np.abs(np.fft.fftshift(np.fft.fft2((img - img.mean()) * np.outer(np.hanning(128), np.hanning(128)))))
    pk = np.unravel_index(np.argmax(F), F.shape)
    fx, fy = to_camera_freq(f_scr[0], f_scr[1], r, th)
    exp_a = np.array([64 + fold(fy) * 128, 64 + fold(fx) * 128])
    exp_b = np.array([64 - fold(fy) * 128, 64 - fold(fx) * 128])
    d = min(np.linalg.norm(np.array(pk) - exp_a), np.linalg.norm(np.array(pk) - exp_b))
    assert d <= 1.0, (pk, exp_a)
    assert abs(fy * 128) > 2                                   # rotation makes row and column frequency differ: axes matter


# 5 ------------------------------------------------------------------------------------------ blur kills the lattice
@pytest.mark.parametrize("layout", ["lcd_rgb", "pentile"])
def test_large_blur_hides_screen(layout):
    img = np.clip(0.5 + 0.2 * np.sin(np.arange(512)[None, :] / 40.0) * np.cos(np.arange(512)[:, None] / 55.0), 0, 1)
    crop, th = _crop(0.5, 2.0, 3.0, img=np.repeat(img[..., None], 3, axis=2))
    a = render_screen(crop, layout, 0.5, th, 3.0)
    b = render_scene(crop, 0.5, th, 3.0)
    rel = np.sqrt(np.mean((a - b) ** 2)) / np.sqrt(np.mean(b ** 2))
    assert rel < 0.01, rel


# 6 / 7 --------------------------------------------------------------------------------------- harmonics
def test_lcd_harmonics_are_integer_only():
    H = layout_harmonics("lcd_rgb")
    half = (np.abs(H["fx"] % 1) > 1e-9) | (np.abs(H["fy"] % 1) > 1e-9)
    assert H["amp"][half].max() < 1e-6


def test_pentile_has_half_integer_peak():
    H = layout_harmonics("pentile")
    idx = np.flatnonzero((np.abs(H["fx"]) == 0.5) & (np.abs(H["fy"]) == 0.5))
    assert len(idx) == 4
    assert H["amp"][idx].min() > 0.01 * H["amp"].max()


# 8 ------------------------------------------------------------------------------------------ predicted peaks
@pytest.mark.parametrize("layout", ["pentile", "lcd_rgb"])
def test_predicted_peaks_match_measurement(layout):
    img = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(C.KODAK_DIR / "kodim05.png").convert("RGB"), float) / 255
    rec, _, _ = make_pair(img, layout, 0.3, 2.0, 0.3, 90, 0.0, seed=5, noise=False, jpeg=False)
    R = detrended(luma(rec))
    loc = (R == maximum_filter(R, size=5)) & (R > 0)
    cand = np.argwhere(loc)
    top = cand[np.argsort(-R[loc])[:5]]
    rows, cols, _ = predicted_peaks(layout, 0.3, np.deg2rad(2.0), 0.3, top=3)
    dmin = min(np.hypot(rows[i] - t[0], cols[i] - t[1]) for i in range(len(rows)) for t in top)
    assert dmin <= 1.5, dmin


# 9 ------------------------------------------------------------------------------------------ theory amplitude
@pytest.mark.parametrize("layout", ["lcd_rgb", "pentile"])
def test_theory_amp_decreases_with_r(layout):
    rs = np.linspace(0.3, 2.5, 23)
    a = np.array([theory_amp(layout, r, 0.4, masked=False, bayer=False) for r in rs])
    assert np.all(np.diff(a) < 0)                              # pure lens MTF: strictly decreasing
    am = np.array([theory_amp(layout, r, 0.4, masked=True, bayer=False) for r in rs])
    assert np.all(am <= a + 1e-12)
    ab = np.array([theory_amp(layout, r, 0.4, masked=False, bayer=True) for r in rs])
    assert np.all(ab <= a + 1e-9)                              # demosaic never adds amplitude (response <= 1)


def test_mtf_formula():
    assert mtf(0.0, 1.0) == 1.0
    assert mtf(0.5, 0.2) == pytest.approx(np.exp(-2 * np.pi ** 2 * 0.04 * 0.25))


# 10 ----------------------------------------------------------------------------------------- geometry
def test_geometry():
    assert r_from_geometry(0.179, 6, 250, 2.0) == pytest.approx(0.002 / (0.179 * 6 / 244), rel=1e-9)
    assert r_from_geometry(0.179, 6, 250, 2.0) == pytest.approx(0.456, rel=0.01)
    d = distance_from_r(0.179, 6.0, 0.7, 2.0)
    assert r_from_geometry(0.179, 6.0, d, 2.0) == pytest.approx(0.7)


# 11 ----------------------------------------------------------------------------------------- camera
def test_flat_scene_stays_flat():
    L = np.full((64, 64, 3), 0.18)
    out = camera_pipeline(L, np.random.default_rng(0), 90, 0.0, noise=False, jpeg=False)
    assert out.std() < 1e-6
    assert bayer_demosaic(L).std() < 1e-9


# 12 ----------------------------------------------------------------------------------------- masks
def test_masks():
    n = masks.N
    assert masks.MASK_BAYER[0, n // 2]
    assert masks.MASK_JPEG[n // 2 + n // 8, n // 2]
    assert masks.MASK_LOW[n // 2, n // 2]
    assert masks.VALID.sum() > 0.8 * n * n


# 13 ----------------------------------------------------------------------------------------- stats
def test_logistic_recovers_weights():
    rng = np.random.default_rng(1)
    X = rng.standard_normal((5000, 3))
    w_true = np.array([0.3, 1.5, -2.0, 0.7])
    y = (rng.random(5000) < 1 / (1 + np.exp(-(np.c_[np.ones(5000), X] @ w_true)))).astype(int)
    w = logistic_irls(X, y, l2=1e-3)
    assert np.allclose(w, w_true, rtol=0.1, atol=0.1)
    assert auc(predict_proba(w, X), y) > 0.8


def test_auc_basic():
    y = np.array([0, 0, 0, 1, 1, 1])
    assert auc(np.array([0, .1, .2, .8, .9, 1.0]), y) == 1.0
    assert auc(np.array([1.0, .9, .8, .2, .1, 0]), y) == 0.0
    rng = np.random.default_rng(0)
    assert abs(auc(rng.random(4000), (rng.random(4000) < 0.5).astype(int)) - 0.5) < 0.05
    assert auc(np.ones(6), y) == 0.5
    lo, hi = auc_boot_ci(np.array([0, .1, .2, .8, .9, 1.0]), y, 200)
    assert lo <= 1.0 <= hi + 1e-9


def test_fit_auc_curve():
    x = np.linspace(-3, 0, 20)
    y = 0.5 + 0.5 / (1 + np.exp(-(x + 1.5) / 0.3))
    c, s, r2 = fit_auc_curve(x, y)
    assert c == pytest.approx(-1.5, abs=0.02) and s == pytest.approx(0.3, abs=0.02) and r2 > 0.999
    assert curve_inverse(0.9, c, s) == pytest.approx(x[np.argmin(abs(y - 0.9))], abs=0.2)


# 14 ----------------------------------------------------------------------------------------- determinism, exposure, guard
def test_make_pair_deterministic():
    img = skdata.astronaut().astype(float) / 255
    a = make_pair(img, "pentile", 0.8, 1.0, 0.4, 85, 0.0, seed=11)
    b = make_pair(img, "pentile", 0.8, 1.0, 0.4, 85, 0.0, seed=11)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


@pytest.mark.parametrize("layout", ["lcd_rgb", "pentile"])
@pytest.mark.parametrize("r", [0.3, 0.9, 2.0])
def test_pair_exposure_matches(layout, r):
    img = skdata.astronaut().astype(float) / 255
    _, _, info = make_pair(img, layout, r, 3.0, 0.4, 90, 0.0, seed=3, noise=False, jpeg=False)
    assert info["mean_ratio"] == pytest.approx(1.0, abs=0.02)


def test_no_zero_band_at_high_r():
    img = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(C.KODAK_DIR / "kodim01.png").convert("RGB"), float) / 255
    rec, dr, _ = make_pair(img, "pentile", 2.4, 6.0, 0.6, 80, 0.0, seed=9)
    for im in (rec, dr):
        s = im.sum(-1)
        assert (s.std(0) > 1e-4).all() and (s.std(1) > 1e-4).all()


def test_features_shape_and_templates():
    img = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(C.KODAK_DIR / "kodim03.png").convert("RGB"), float) / 255
    rec, _, _ = make_pair(img, "lcd_rgb", 0.4, 2.0, 0.3, 90, 0.0, seed=2)
    f, R = features_all(rec, known=(0.4, np.deg2rad(2.0)))
    assert f.shape == (74,) and len(FEATURE_NAMES) == 74 and np.isfinite(f).all()
    assert f[72] > 1.0                      # the true-geometry LCD template finds the moire of an LCD recapture
    assert f[72] > features_all(make_pair(img, "lcd_rgb", 0.4, 2.0, 0.3, 90, 0.0, seed=2)[1], known=(0.4, np.deg2rad(2.0)))[0][72]
    rows, cols = template_tables("pentile")
    assert rows.shape == (len(R_GRID), 33, 12)
    pad = (rows == masks.N // 2) & (cols == masks.N // 2)       # empty slots are padded with the (masked) DC bin
    assert (~masks.MASK_ALL[rows, cols] | pad).all()
