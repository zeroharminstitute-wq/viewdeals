"""Give free-license photos the house two-ink risograph treatment (dev only).

Reads data/photo-sources.json, downloads each original once into photos-src/
(git-ignored), and writes:
  assets/photos/<key>.webp and <key>@2x.webp   two-ink prints, 3:2 (or 16:9 for "wide")
  data/photos.json                              what the build reads: files, alt, credits

The print is made like a two-drum riso pull on cream paper:
  ink plate  (#161412)  from the photo's tones
  red plate  (#D7261E)  from the photo's saturated colors, so the subject carries the red
  both plates get grain, and the red plate is offset a few pixels (misregistration).

Needs Pillow:  pip install pillow   (the site build itself stays standard-library only)
Usage:         python scripts/dev/treat_photos.py [--only KEY] [--force]
"""
import argparse
import json
import random
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[2]
PAPER, INK, RED = (244, 239, 230), (22, 20, 18), (215, 38, 30)
SIZES = {"card": (720, 480), "wide": (880, 495)}   # 1x; 2x is double


def smooth(lo, hi, gain=1.0):
    def f(x):
        t = min(1.0, max(0.0, (x / 255 - lo) / (hi - lo)))
        return int(255 * gain * t * t * (3 - 2 * t))
    return f


def fetch(key, entry, force):
    src_dir = ROOT / "photos-src"
    src_dir.mkdir(exist_ok=True)
    path = src_dir / f"{key}.jpg"
    if force or not path.exists():
        url = f"https://images.unsplash.com/{entry['unsplash']}?w=2400&q=85&fm=jpg"
        req = urllib.request.Request(url, headers={"User-Agent": "viewdeals-dev-photo-tool"})
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return Image.open(path).convert("RGB")


def crop(im, size, fx, fy):
    w, h = size
    scale = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x = round((im.width - w) * fx)
    y = round((im.height - h) * fy)
    return im.crop((x, y, x + w, y + h))


def grain(size, sigma, seed):
    random.seed(seed)
    n = Image.effect_noise(size, sigma)
    return n


def plate(coverage, color):
    """Coverage (L, 255 = full ink) -> RGB layer to multiply onto paper."""
    return Image.composite(Image.new("RGB", coverage.size, color), Image.new("RGB", coverage.size, (255, 255, 255)), coverage)


def treat(im, size, seed):
    w, h = size
    k = w / 720  # scale effects with output size
    lum = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    # Ink plate: shadows and mid-tones; paper shows through the highlights.
    ink = ImageOps.invert(lum).point(smooth(0.10, 0.95, 0.94))
    # Red plate: warm, saturated areas (reds, oranges, yellows, pinks) so the subject carries
    # the red; plus a light red under the mid-tones, the classic duotone warmth.
    hsv = im.convert("HSV")
    hue, s, val = hsv.split()
    warm = hue.point(lambda x: 255 if (x < 48 or x > 214) else (int(255 * (64 - x) / 16) if x < 64 else 0))
    red = ImageChops.multiply(ImageChops.multiply(s.point(smooth(0.25, 0.7)), warm), val.point(smooth(0.08, 0.55, 0.88)))
    under = ink.point(lambda x: int(70 * max(0.0, 1 - abs(x / 255 - 0.45) / 0.45)))
    red = ImageChops.lighter(red, under).filter(ImageFilter.GaussianBlur(0.6 * k))
    # Grain: the drum never lays ink perfectly evenly. Grain only thins ink that is there,
    # so clean paper stays clean.
    def thin(cov, seed, sigma):
        n = Image.effect_noise(size, sigma).filter(ImageFilter.GaussianBlur(0.45 * k)).point(lambda x: min(255, x + 105))
        return ImageChops.multiply(cov, n)
    random.seed(seed)
    ink = thin(ink, seed, 40)
    red = thin(red, seed + 1, 46)
    starve = grain((max(1, w // 8), max(1, h // 8)), 60, seed + 2).resize(size, Image.BICUBIC)
    red = ImageChops.subtract(red, starve.point(lambda x: max(0, x - 160)))
    # Misregistration: the red drum sits a little off.
    dx, dy = round(3 * k), round(2 * k)
    red = ImageChops.offset(red, dx, dy)
    red.paste(0, (0, 0, w, dy))   # offset wraps around; clear the wrapped edges
    red.paste(0, (0, 0, dx, h))
    out = Image.new("RGB", size, PAPER)
    out = ImageChops.multiply(out, plate(red, RED))
    out = ImageChops.multiply(out, plate(ink, INK))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true", help="re-download originals")
    args = ap.parse_args()
    sources = json.loads((ROOT / "data" / "photo-sources.json").read_text(encoding="utf-8"))["photos"]
    out_dir = ROOT / "assets" / "photos"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "data" / "photos.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"photos": {}}
    for i, (key, entry) in enumerate(sources.items()):
        if args.only and key != args.only:
            continue
        src = fetch(key, entry, args.force)
        base = SIZES[entry.get("shape", "card")]
        files = {}
        for mult, suffix in ((1, ""), (2, "@2x")):
            size = (base[0] * mult, base[1] * mult)
            img = treat(crop(src, size, entry.get("focus_x", 0.5), entry.get("focus_y", 0.5)), size, seed=i * 10)
            name = f"assets/photos/{key}{suffix}.webp"
            img.save(ROOT / name, "WEBP", quality=68 if mult == 1 else 52, method=6)
            files[mult] = name
            print(f"{name}  {size[0]}x{size[1]}  {(ROOT / name).stat().st_size // 1024} KB")
        manifest["photos"][key] = {
            "file": files[1], "file_2x": files[2], "alt": entry["alt"],
            "credit": entry["credit"], "source": "Unsplash", "source_url": entry["source_url"],
            "license": "Unsplash License",
        }
    manifest["photos"] = dict(sorted(manifest["photos"].items()))
    manifest_path.write_bytes((json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
