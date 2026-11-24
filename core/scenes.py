"""Source images (Kodak) with a train/test split by scene."""
import numpy as np
from PIL import Image
import config as C

_cache = {}


def scene_path(i):
    return C.KODAK_DIR / f"kodim{i:02d}.png"


def available_scenes():
    return [i for i in range(1, C.N_KODAK + 1) if scene_path(i).exists()]


def load_scene(i):
    """sRGB float [0,1] image, cached per process."""
    if i not in _cache:
        _cache[i] = np.asarray(Image.open(scene_path(i)).convert("RGB"), dtype=np.float64) / 255.0
    return _cache[i]


def split_of(i):
    return "train" if i in C.TRAIN_SCENES else "test"
