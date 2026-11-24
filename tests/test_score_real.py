"""End-to-end test of score_real.py on SIMULATED stand-ins for real photos (full-size JPEGs + meta.csv)."""
import csv
import numpy as np
from PIL import Image

import config as C
from core import scenes
from core.colour import srgb_to_linear, luma
from core.render import render_screen, render_scene, required_crop, random_crop
from core.camera import camera_pipeline
import score_real


def _photo(layout, screen, r, seed, out=300):
    rng = np.random.default_rng(seed)
    img = scenes.load_scene(5)
    th = np.deg2rad(2.0)
    side = required_crop(r, th, 0.4, out)
    crop, _ = random_crop(srgb_to_linear(img), side, rng)
    L = render_screen(crop, layout, r, th, 0.4, out) if screen else render_scene(crop, r, th, 0.4, out)
    gain = C.EXPOSURE_MEAN / luma(render_scene(crop, r, th, 0.4, out)).mean()
    return camera_pipeline(L * gain, rng, 92)


def test_score_real_on_simulated_photos(tmp_path, monkeypatch):
    rows = []
    for k, (name, layout, screen, dev, r, dist) in enumerate([
            ("lcd_screen.jpg", "lcd_rgb", True, "laptop_lcd", 0.4, 25), ("lcd_direct.jpg", "lcd_rgb", False, "none", 0.4, 25),
            ("phone_screen.jpg", "pentile", True, "phone_oled", 1.6, 25), ("phone_direct.jpg", "pentile", False, "none", 1.6, 25)]):
        Image.fromarray((_photo(layout, screen, r, k) * 255).astype(np.uint8)).save(tmp_path / name, quality=92)
        rows.append({"file": name, "kind": "screen" if screen else "direct", "screen": dev, "distance_cm": dist, "phone_model": "sim", "notes": ""})
    with open(tmp_path / "meta.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    res = {r["file"]: r for r in score_real.score_folder(tmp_path, 2.0)}
    assert res["lcd_screen.jpg"]["p_screen"] > 0.8                       # resolved LCD screen is caught
    assert res["lcd_direct.jpg"]["p_screen"] < 0.3                       # its direct photo is not
    assert abs(res["phone_screen.jpg"]["p_screen"] - res["phone_direct.jpg"]["p_screen"]) < 0.4   # phone: no separation
    assert res["lcd_screen.jpg"]["r_predicted"] == np.float64(res["lcd_screen.jpg"]["r_predicted"]) and res["lcd_screen.jpg"]["r_predicted"] > 0
