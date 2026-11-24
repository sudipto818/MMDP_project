"""All constants for "Which Screen Was It?". Change numbers here, nowhere else."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
KODAK_DIR = DATA_DIR / "kodak"
CACHE_DIR = ROOT / "cache"
FIGS_DIR = ROOT / "figs"
SITE_DIR = ROOT / "site"

SEED = 0

# ---------------------------------------------------------------- data
KODAK_URL = "https://r0k.us/graphics/kodak/kodak/kodim{:02d}.png"   # http:// redirects to https://
N_KODAK = 24
TRAIN_SCENES = list(range(1, 17))      # scene ids are 1-based (kodim01 ... kodim24)
TEST_SCENES = list(range(17, 25))

# ---------------------------------------------------------------- camera model
OUT = 128                      # camera image side (pixels); also the FFT size
SIGMA_LENS = (0.20, 0.60)      # Gaussian lens PSF std, in CAMERA pixels
SIGMA_APERTURE = 0.29          # box pixel aperture ~ Gaussian, std 1/sqrt(12) camera px
THETA_DEG = (-6.0, 6.0)        # camera rotation relative to the screen
JPEG_Q = (75, 95)
NOISE_SHOT = 0.002             # noise variance = NOISE_SHOT * L + NOISE_READ**2   (linear light)
NOISE_READ = 0.002
EXPOSURE_MEAN = 0.18           # auto-exposure: mean linear luma of the DIRECT photo (mid grey)
SHARPEN_MAIN = 0.0             # unsharp amount in the main experiments (E6 varies it)

# ---------------------------------------------------------------- geometry (ALL ASSUMPTIONS: verify in the report)
# Typical products. pitch = distance between neighbouring screen pixels.
#  laptop 15.6" FHD  : 1920 px over ~345 mm   -> 0.179 mm  (141 ppi)
#  monitor 24" FHD   : 1920 px over ~531 mm   -> 0.277 mm  ( 92 ppi)
#  phone OLED ~460ppi: 25.4/460               -> 0.055 mm
DEVICES = {
    "laptop_lcd":  {"label": "Laptop LCD (141 ppi)",  "layout": "lcd_rgb", "pitch_mm": 0.179},
    "monitor_lcd": {"label": "Monitor LCD (92 ppi)",  "layout": "lcd_rgb", "pitch_mm": 0.277},
    "phone_oled":  {"label": "Phone OLED (460 ppi)",  "layout": "pentile", "pitch_mm": 0.055},
}
# Typical phone main camera: focal length ~6 mm (physical), effective pixel 1.0 um (full 50 MP) or 2.0 um (4-in-1 binned)
CAMERA = {"f_mm": 6.0, "px_um": {"binned": 2.0, "full": 1.0}}
DIST_CM = (15.0, 40.0)

# ---------------------------------------------------------------- experiment sizes: (full, quick)
E1_PAIRS_PER_DEVICE = (300, 90)
E2_R_CENTERS = [0.3, 0.5, 0.7, 0.9, 1.1, 1.4, 1.8, 2.4]
E2_R_HALFWIDTH = 0.08
E2_PAIRS_PER_BIN = (40, 14)
E6_R_CENTERS = [0.5, 0.9, 1.4]
E6_PAIRS_PER_BIN = (30, 10)
N_BOOT = 1000

LAYOUT_NAMES = ["lcd_rgb", "pentile"]
