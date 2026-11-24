"""Inspect the real photos: format, size, dimensions, EXIF (model, focal length, software, flash), JPEG quality estimate."""
import sys
from pathlib import Path
from PIL import Image, ExifTags

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "real"
TAGS = {v: k for k, v in ExifTags.TAGS.items()}


def exif_get(ex, name):
    v = ex.get(TAGS.get(name))
    return v


rows = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".heic", ".heif", ".dng"):
        continue
    im = Image.open(p)
    ex = im.getexif()
    sub = ex.get_ifd(0x8769) if hasattr(ex, "get_ifd") else {}
    q = None
    if getattr(im, "quantization", None):
        q0 = im.quantization.get(0)
        q = sum(q0) / len(q0) if q0 else None                    # mean luminance quantisation step (lower = higher quality)
    rows.append((p.relative_to(root), p.stat().st_size / 1e6, im.width, im.height, ex.get(271), ex.get(272), ex.get(305),
                 sub.get(0x920A), sub.get(0xA405), sub.get(0x9209), sub.get(0xA402), sub.get(0xA406), ex.get(274), q, "mpf" if "mpoffset" in im.info else ""))
print(f"{'file':44s} {'MB':>5s} {'size':>11s} {'make/model':24s} {'focal':>6s} {'f35':>4s} flash expmode scene orient  qstep")
for r in rows:
    name, mb, w, h, make, model, soft, focal, f35, flash, expmode, scenetype, orient, q, mpf = r
    print(f"{str(name):44s} {mb:5.2f} {w:5d}x{h:<5d} {str(make or '')[:8] + ' ' + str(model or '')[:14]:24s} {str(focal)[:5]:>6s} {str(f35):>4s} {str(flash):>5s} {str(expmode):>7s} {str(scenetype):>5s} {str(orient):>6s} {q if q is None else round(q, 2)!s:>6s} {mpf}")
print(len(rows), "images")
