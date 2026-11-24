"""Download the Kodak Lossless True Colour Image Suite (24 images) into data/kodak/. Safe to re-run."""
import sys
import time
import urllib.request
import numpy as np
from PIL import Image

import config as C


def fetch(i, tries=3):
    path = C.KODAK_DIR / f"kodim{i:02d}.png"
    if path.exists() and path.stat().st_size > 100_000:
        return path, "cached"
    for t in range(tries):
        try:
            req = urllib.request.Request(C.KODAK_URL.format(i), headers={"User-Agent": "DA3021-course-project/0.1"})
            data = urllib.request.urlopen(req, timeout=60).read()
            path.write_bytes(data)
            return path, "downloaded"
        except Exception as e:                       # noqa: BLE001
            err = e
            time.sleep(1.5 * (t + 1))
    return None, f"FAILED ({err})"


def main():
    C.KODAK_DIR.mkdir(parents=True, exist_ok=True)
    ok, rows = 0, []
    for i in range(1, C.N_KODAK + 1):
        p, status = fetch(i)
        if p is None:
            print(f"kodim{i:02d}: {status}")
            continue
        im = Image.open(p)
        arr = np.asarray(im.convert("RGB"), dtype=np.float64) / 255
        rows.append((i, im.size, arr.mean()))
        ok += 1
        print(f"kodim{i:02d}: {status:10s} {im.size[0]}x{im.size[1]}  mean brightness {arr.mean():.3f}")
    print(f"\n{ok}/{C.N_KODAK} images in {C.KODAK_DIR}")
    if ok < C.N_KODAK:
        print("WARNING: some images are missing; re-run, or check your internet connection.")
        sys.exit(1)
    sizes = {s for _, s, _ in rows}
    print("sizes:", sorted(sizes), "| train scenes:", C.TRAIN_SCENES[0], "-", C.TRAIN_SCENES[-1],
          "| test scenes:", C.TEST_SCENES[0], "-", C.TEST_SCENES[-1])


if __name__ == "__main__":
    main()
