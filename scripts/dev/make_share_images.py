"""Make the 1200x630 PNG share cards and the square logo (dev only).

Social sites don't show SVG previews, so every department, event hub, guide and
the home page gets a PNG card in the house style: paper, the ViewDeals
wordmark with its double rule, the page's headline, and its header photo.
Deal pages share one generic card with no photo, because a picture on a deal
must be the exact item (see the Art direction amendment in BUILD_PLAN.md).

Needs Pillow and the full variable fonts (TTF, not the subset WOFF2s):
  python scripts/dev/make_share_images.py --fonts DIR_WITH_TTFS
Writes assets/share/*.png and assets/logo-512.png. Run it again whenever a
department, event, guide or photo changes.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
PAPER, INK, RED, MUTED = (255, 255, 255), (17, 17, 17), (215, 38, 30), (85, 85, 85)
W, H, M = 1200, 630, 64


class Fonts:
    def __init__(self, folder):
        self.dir = Path(folder)

    def serif(self, size, weight=600, opsz=None, italic=False):
        f = ImageFont.truetype(str(self.dir / ("Newsreader-Italic-VF.ttf" if italic else "Newsreader-VF.ttf")), size)
        axes = {a["name"] if isinstance(a["name"], str) else a["name"].decode(): a for a in f.get_variation_axes()}
        vals = []
        for name, a in axes.items():
            n = name.lower()
            if "weight" in n:
                vals.append(weight)
            elif "optical" in n:
                vals.append(min(a["maximum"], max(a["minimum"], opsz or size)))
            else:
                vals.append(a["default"])
        f.set_variation_by_axes(vals)
        return f

    def sans(self, size, weight=500):
        f = ImageFont.truetype(str(self.dir / "HankenGrotesk-VF.ttf"), size)
        f.set_variation_by_axes([weight])
        return f


def wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def masthead(d, fonts, x, y, width):
    d.text((x, y), "ViewDeals", font=fonts.serif(60, 700, 60), fill=INK, anchor="ls")
    d.rectangle((x, y + 18, x + width, y + 21), fill=INK)
    d.rectangle((x, y + 26, x + width, y + 27), fill=INK)
    return y + 27


def headline(d, fonts, text, x, y, width, max_lines=3):
    for size in (78, 70, 62, 56, 50):
        f = fonts.serif(size, 600, 72)
        lines = wrap(d, text, f, width)
        if len(lines) <= max_lines:
            break
    lead = round(size * 1.04)
    for i, line in enumerate(lines):
        d.text((x, y + lead * (i + 1)), line, font=f, fill=INK, anchor="ls")
    return y + lead * len(lines)


def card(fonts, kicker, title, photo=None):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    text_w = 560 if photo else 660
    top = masthead(d, fonts, M, M + 44, text_w)
    d.text((M, top + 58), kicker.upper(), font=fonts.serif(21, 600, 8), fill=MUTED, anchor="ls")
    headline(d, fonts, title, M, top + 70, text_w)
    if not photo:
        d.rectangle((M + text_w, M + 62, W - M, M + 65), fill=INK)
        d.rectangle((M + text_w, M + 70, W - M, M + 71), fill=INK)
    d.text((M, H - M), "Hand-picked deals, refreshed every day.", font=fonts.serif(27, 400, 24, italic=True), fill=INK, anchor="ls")
    d.text((M, H - M - 44), "VIEWDEALS.COM", font=fonts.sans(18, 600), fill=MUTED, anchor="ls")
    if photo:
        box = (680, M, W - M, H - M)
        src = Image.open(photo).convert("RGB")
        fitted = ImageOps.fit(src, (box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        im.paste(fitted, box[:2])
        d.rectangle(box, outline=INK, width=2)
    else:
        # A die-cut tag in tag red, the site's one recurring mark.
        tx, ty = 756, 400
        d.polygon([(tx, ty + 60), (tx + 50, ty), (tx + 380, ty), (tx + 380, ty + 120), (tx + 50, ty + 120)], fill=RED)
        d.polygon([(tx + 8, ty + 60), (tx + 54, ty + 7), (tx + 373, ty + 7), (tx + 373, ty + 113), (tx + 54, ty + 113)], fill=PAPER)
        d.ellipse((tx + 40, ty + 50, tx + 60, ty + 70), fill=RED)
        d.text((tx + 225, ty + 60), "CHECKED BY HAND", font=fonts.serif(25, 700, 8), fill=INK, anchor="mm")
    return im


def logo(fonts):
    im = Image.new("RGB", (512, 512), PAPER)
    d = ImageDraw.Draw(im)
    d.text((256, 318), "VD", font=fonts.serif(230, 700, 72), fill=INK, anchor="ms")
    d.rectangle((86, 360, 426, 370), fill=INK)
    d.rectangle((86, 382, 426, 386), fill=INK)
    d.rectangle((86, 404, 426, 414), fill=RED)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True, help="folder with Newsreader-VF.ttf, Newsreader-Italic-VF.ttf, HankenGrotesk-VF.ttf")
    args = ap.parse_args()
    fonts = Fonts(args.fonts)
    cfg = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
    events = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf-8"))["events"]
    guides = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "guides").glob("*.json"))]
    photos = ROOT / "assets" / "photos"
    out = ROOT / "assets" / "share"
    out.mkdir(parents=True, exist_ok=True)

    def ph(key):
        p = photos / f"{key}@2x.webp"
        return p if p.exists() else None

    jobs = {"home": ("Today's edition", "Today's best deals", ph("cat-events")),
            "deal": ("Deal of the day", "A deal worth your time", None)}
    for slug, name in cfg["categories"].items():
        jobs[f"cat-{slug}"] = ("Department", f"Best {name} deals today", ph(f"cat-{slug}"))
    for ev in events:
        jobs[f"event-{ev['slug']}"] = ("Sale event", f"Best {ev['name']} deals", ph(f"event-{ev['slug']}"))
    for g in guides:
        jobs[f"guide-{g['slug']}"] = (g.get("kicker", "Guide"), g["title"].replace("'", "’"), ph(f"guide-{g['slug']}"))
    for key, (kicker, title, photo) in jobs.items():
        path = out / f"{key}.png"
        card(fonts, kicker, title.replace("'", "’"), photo).quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")
    logo(fonts).save(ROOT / "assets" / "logo-512.png", optimize=True)
    print("assets/logo-512.png")


if __name__ == "__main__":
    main()
