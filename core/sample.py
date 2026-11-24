"""One controlled pair: a photo of a SCREEN and a direct photo of the same content.
Both share the crop, r, theta, blur, exposure gain, JPEG quality and sharpening; they differ only in the screen."""
import numpy as np

import config as C
from .colour import srgb_to_linear, luma
from .render import required_crop, random_crop, render_screen, render_scene
from .camera import camera_pipeline
from .features import features_all
from . import scenes


def make_pair(img_srgb, layout, r, theta_deg, sigma_lens, jpeg_q, sharpen, seed, noise=True, jpeg=True, return_crop=False):
    rng = np.random.default_rng(seed)
    th = np.deg2rad(theta_deg)
    side = required_crop(r, th, sigma_lens)
    crop_srgb, pos = random_crop(img_srgb, side, rng)
    crop = srgb_to_linear(crop_srgb)                 # convert only the crop, not the whole image
    L_rec = render_screen(crop, layout, r, th, sigma_lens)
    L_dir = render_scene(crop, r, th, sigma_lens)
    # guard against the zero-band bug (camera footprint leaving the crop)
    for L in (L_rec, L_dir):
        s = L.sum(-1)
        assert (s.max(0) > 1e-9).all() and (s.max(1) > 1e-9).all(), "zero band in render"
    gain = C.EXPOSURE_MEAN / max(float(luma(L_dir).mean()), 1e-6)        # ONE gain for both (shared exposure)
    rgb_rec = camera_pipeline(L_rec * gain, np.random.default_rng([seed, 1]), jpeg_q, sharpen, noise, jpeg)
    rgb_dir = camera_pipeline(L_dir * gain, np.random.default_rng([seed, 2]), jpeg_q, sharpen, noise, jpeg)
    info = {"crop_i": pos[0], "crop_j": pos[1], "side": side, "gain": gain,
            "mean_ratio": float(luma(L_rec).mean() / max(luma(L_dir).mean(), 1e-9))}
    if return_crop:
        info["crop"] = crop
    return rgb_rec, rgb_dir, info


def random_params(rng, r, sharpen=C.SHARPEN_MAIN):
    return {"r": float(r), "theta": float(rng.uniform(*C.THETA_DEG)), "sigma": float(rng.uniform(*C.SIGMA_LENS)),
            "q": int(rng.integers(C.JPEG_Q[0], C.JPEG_Q[1] + 1)), "sharpen": float(sharpen)}


def run_task(task):
    """Pool worker. task: dict(layout, scene, r, theta, sigma, q, sharpen, seed). Returns (task, feat_rec, feat_dir)."""
    img = scenes.load_scene(task["scene"])
    rec, dr, info = make_pair(img, task["layout"], task["r"], task["theta"], task["sigma"], task["q"],
                              task["sharpen"], task["seed"])
    known = (task["r"], np.deg2rad(task["theta"]))
    return task, features_all(rec, known)[0], features_all(dr, known)[0], info["mean_ratio"]
