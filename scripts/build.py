#!/usr/bin/env python3
"""ViewDeals build script: validate the deals data, then build the static site.

Standard library only (Python 3.9+).

    python3 scripts/build.py                     validate, then build docs/ as of today
    python3 scripts/build.py --check             validate only; write nothing
    python3 scripts/build.py --prune             archive expired deals, then build
    python3 scripts/build.py --today YYYY-MM-DD  treat that date as today
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import struct
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED = ["id", "title", "retailer", "url", "category", "blurb", "added", "expires"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PRICE_RE = re.compile(r"[$€£]\s?\d|\d+\s?%|\bpercent\b", re.IGNORECASE)
BLURB_MAX = 320
WRITE_UP_MIN_WORDS = 150
TITLE_MAX = 60
DESC_MIN, DESC_MAX = 120, 155
NOINDEX_AFTER_DAYS = 60     # an ended deal page gets noindex after this many days
REDIRECT_AFTER_DAYS = 365   # ...and becomes a redirect to its department after this many
ENDING_SOON_DAYS = 3
UPDATED_TOKEN = "\x00UPDATED\x00"
VOLATILE_RE = re.compile(r"<!--v-->.*?<!--/v-->", re.S)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def load_json(path, default=None):
    if default is not None and not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_text(path, text):
    """Write UTF-8 text with LF line endings on every platform."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def parse_date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def word_count(paragraphs):
    if not isinstance(paragraphs, list):
        return 0
    return sum(len(str(p).split()) for p in paragraphs)


def eastern_today():
    """Today's date in America/New_York, with a DST fallback when tzdata is missing."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

        def nth_sunday(month, n):
            d = dt.datetime(utc.year, month, 1)
            d += dt.timedelta(days=(6 - d.weekday()) % 7)
            return d + dt.timedelta(weeks=n - 1)

        dst = nth_sunday(3, 2).replace(hour=7) <= utc < nth_sunday(11, 1).replace(hour=6)
        return (utc + dt.timedelta(hours=-4 if dst else -5)).date()


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def fmt_date(d):
    return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"


def fmt_long(d):
    return f"{DAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}, {d.year}"


def smart(s):
    """Curly quotes and real dashes for display text."""
    s = str(s)
    s = re.sub(r"(\w)'(\w)", "\\1\u2019\\2", s)
    s = re.sub(r"(\w)'", "\\1\u2019", s)
    s = re.sub(r"'(\w)", "\u2018\\1", s)
    s = re.sub(r'"(?=\w)', "\u201c", s)
    s = s.replace('"', "\u201d")
    s = s.replace(" -- ", " \u2014 ").replace("--", "\u2013")
    return s


def e(s):
    """HTML-escape a raw value (attributes, URLs)."""
    return html.escape(str(s), quote=True)


def t(s):
    """HTML-escape display text, with typographic quotes."""
    return html.escape(smart(s), quote=False)


def v(fragment):
    """Mark a fragment as volatile so it is ignored by the content hash."""
    return f"<!--v-->{fragment}<!--/v-->"


def tilt(deal_id):
    """Fixed rotation between -2 and +2 degrees, derived from the deal id."""
    h = int(hashlib.sha1(deal_id.encode("utf-8")).hexdigest()[:8], 16)
    return round((h % 401) / 100 - 2, 2)


def fit_description(sentences, filler="Every deal is picked and checked by hand at ViewDeals."):
    """Join sentences into a 120-155 character meta description."""
    out = ""
    for s in [x for x in sentences if x] + [filler, "Refreshed every morning."]:
        s = " ".join(str(s).split())
        out = f"{out} {s}".strip() if out else s
        if len(out) >= DESC_MIN:
            break
    if len(out) > DESC_MAX:
        cut = out[:DESC_MAX - 1]
        cut = cut[:cut.rfind(" ")].rstrip(",;:.- ")
        out = cut + "\u2026"
    return out


# --------------------------------------------------------------------------
# Affiliate links
# --------------------------------------------------------------------------

def affiliate_url(config, deal):
    """Return the outbound link for a deal, with the retailer's affiliate settings applied."""
    retailer = config.get("retailers", {}).get(deal.get("retailer"), {})
    url = deal["url"]
    template = retailer.get("link_template") or ""
    if template:
        return template.replace("{url}", quote(url, safe=""))
    params = {k: v for k, v in (retailer.get("query_params") or {}).items() if v}
    if params:
        parts = urlsplit(url)
        query = [(k, val) for k, val in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
        query += list(params.items())
        return urlunsplit(parts._replace(query=urlencode(query)))
    return url


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def image_size(path):
    """Return (width, height) for SVG, PNG, WebP or JPEG files, else None."""
    p = Path(path)
    if not p.is_file():
        return None
    data = p.read_bytes()
    try:
        if p.suffix.lower() == ".svg":
            head = data[:2000].decode("utf-8", "ignore")
            tag = re.search(r"<svg\b[^>]*>", head, re.S)
            if not tag:
                return None
            w = re.search(r'\bwidth="(\d+(?:\.\d+)?)', tag.group(0))
            h = re.search(r'\bheight="(\d+(?:\.\d+)?)', tag.group(0))
            if w and h:
                return int(float(w.group(1))), int(float(h.group(1)))
            vb = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', tag.group(0))
            return (int(float(vb.group(1))), int(float(vb.group(2)))) if vb else None
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if chunk == b"VP8L":
                b = int.from_bytes(data[21:25], "little")
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (struct.error, IndexError, ValueError):
        return None
    return None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

PRODUCT_IMAGE_MODES = ("none", "feed", "api")
AMAZON_IMAGE_HOSTS = ("m.media-amazon.com", "images-na.ssl-images-amazon.com", "images-eu.ssl-images-amazon.com")


def product_image_errors(config, deal):
    """Rules for a deal's product photo (deal['image']).

    A retailer's product_images setting must allow it: 'feed' means its affiliate
    program supplies images to affiliates, 'api' means Amazon Product Advertising
    API access. Images are always hotlinked from the retailer's own servers,
    never copied into the repo.
    """
    im = deal.get("image")
    if not im:
        return []
    did = deal.get("id", "?")
    rid = deal.get("retailer")
    mode = config.get("retailers", {}).get(rid, {}).get("product_images", "none")
    errs = []
    if mode not in PRODUCT_IMAGE_MODES:
        errs.append(f"retailer {rid}: product_images must be one of {', '.join(PRODUCT_IMAGE_MODES)}")
    if mode == "none":
        errs.append(f"{did}: has a product image, but {rid}'s affiliate program is not set to allow them (product_images is 'none')")
    if rid == "amazon" and mode != "api":
        errs.append(f"{did}: Amazon product images need Product Advertising API access (product_images 'api')")
    if not isinstance(im, dict):
        return errs + [f"{did}: image must be an object with url, width, height and alt"]
    url = str(im.get("url", ""))
    host = urlsplit(url).hostname or ""
    if not url.startswith("https://"):
        errs.append(f"{did}: image url must be an https link to the retailer's own server (never a copy in the repo)")
    elif rid == "amazon" and host not in AMAZON_IMAGE_HOSTS:
        errs.append(f"{did}: Amazon images must be served from Amazon's image servers, not {host}")
    if not (isinstance(im.get("width"), int) and isinstance(im.get("height"), int) and im["width"] > 0 and im["height"] > 0):
        errs.append(f"{did}: image needs integer width and height")
    if not str(im.get("alt", "")).strip():
        errs.append(f"{did}: image needs alt text")
    return errs


def photo_errors(photos, root):
    errs = []
    for key, ph in (photos or {}).items():
        if not re.fullmatch(r"(cat|event|guide)-[a-z0-9-]+", key):
            errs.append(f"photo {key}: key must be cat-<slug>, event-<slug> or guide-<slug>")
        for field in ("file", "alt", "credit", "source", "source_url", "license"):
            if not str(ph.get(field, "")).strip():
                errs.append(f"photo {key}: missing '{field}'")
        if ph.get("license") not in ("Unsplash License", "Pexels License", "Owner's own"):
            errs.append(f"photo {key}: license must be Unsplash License, Pexels License or Owner's own")
        for f in (ph.get("file"), ph.get("file_2x")):
            if f and root is not None and not image_size(Path(root) / f):
                errs.append(f"photo {key}: {f} is missing or has no width and height")
    return errs


def validate(config, deals, events=None, archive=None, guides=None, root=None, photos=None):
    """Return a list of error strings for the data files; empty means valid."""
    errors = []
    retailers = config.get("retailers", {})
    categories = config.get("categories", {})
    event_slugs = {ev["slug"] for ev in (events or {}).get("events", [])}
    archive = archive or []
    seen = set()
    known_ids = {d.get("id") for d in deals if isinstance(d, dict)} | {d.get("id") for d in archive}

    for i, deal in enumerate(deals):
        did = deal.get("id") or f"#{i + 1}"

        # Rule 1: required fields present and non-empty.
        for field in REQUIRED:
            value = deal.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{did}: missing required field '{field}'")

        # Rule 2: id format and uniqueness.
        if deal.get("id"):
            if not ID_RE.match(deal["id"]):
                errors.append(f"{did}: id must be lowercase letters, numbers and dashes")
            if deal["id"] in seen:
                errors.append(f"{did}: duplicate id")
            seen.add(deal["id"])

        # Rule 3: retailer and category exist.
        if deal.get("retailer") and deal["retailer"] not in retailers:
            errors.append(f"{did}: unknown retailer '{deal['retailer']}'")
        if deal.get("category") and deal["category"] not in categories:
            errors.append(f"{did}: unknown category '{deal['category']}'")

        # Rule 4: https URL with a host.
        url = deal.get("url") or ""
        parts = urlsplit(url)
        if url and (parts.scheme != "https" or not parts.netloc):
            errors.append(f"{did}: url must be https:// with a host")

        # Rules 5 and 6: Amazon-specific checks.
        if deal.get("retailer") == "amazon":
            host = parts.netloc.lower()
            if url and not ("amazon." in host or "amzn." in host):
                errors.append(f"{did}: Amazon url must be on an amazon. or amzn. host")
            if "tag=" in url:
                errors.append(f"{did}: url must not contain tag= (the build adds it)")
            for field in ("title", "blurb", "label"):
                if PRICE_RE.search(str(deal.get(field) or "")):
                    errors.append(f"{did}: Amazon {field} must not show a price or discount")

        # Rule 7: dates parse and expires >= added.
        added, expires = parse_date(deal.get("added")), parse_date(deal.get("expires"))
        if deal.get("added") and not added:
            errors.append(f"{did}: added is not a YYYY-MM-DD date")
        if deal.get("expires") and not expires:
            errors.append(f"{did}: expires is not a YYYY-MM-DD date")
        if added and expires and expires < added:
            errors.append(f"{did}: expires is before added")

        # Rule 8: blurb length.
        if len(deal.get("blurb") or "") > BLURB_MAX:
            errors.append(f"{did}: blurb is over {BLURB_MAX} characters")

        # SEO fields.
        if "write_up" in deal:
            words = word_count(deal["write_up"])
            if words < WRITE_UP_MIN_WORDS:
                errors.append(f"{did}: write_up has {words} words; needs {WRITE_UP_MIN_WORDS}+ for a page")
            if deal.get("retailer") == "amazon":
                extra = [deal.get("who_for", ""), deal.get("skip_if", ""), deal.get("hook", ""),
                         deal.get("short_name", ""), deal.get("seo_title", ""), deal.get("meta_description", "")]
                if any(PRICE_RE.search(str(p)) for p in list(deal["write_up"]) + extra):
                    errors.append(f"{did}: Amazon write-up must not show a price or discount")
        for rid in deal.get("related", []):
            if rid not in known_ids:
                errors.append(f"{did}: related id '{rid}' does not exist")
        if deal.get("event") and deal["event"] not in event_slugs:
            errors.append(f"{did}: unknown event '{deal['event']}'")
        errors.extend(product_image_errors(config, deal))

    for rid, r in retailers.items():
        if r.get("product_images", "none") not in PRODUCT_IMAGE_MODES:
            errors.append(f"retailer {rid}: product_images must be one of {', '.join(PRODUCT_IMAGE_MODES)}")
    if retailers.get("amazon", {}).get("product_images", "none") == "feed":
        errors.append("retailer amazon: product_images can only be 'none' or 'api' (Amazon has no image feed for affiliates)")
    errors.extend(photo_errors(photos, root))

    for g in guides or []:
        gid = g.get("slug", "?")
        for field in ("slug", "title", "dek", "author", "published", "updated", "image", "sections", "deal_ids"):
            if not g.get(field):
                errors.append(f"guide {gid}: missing required field '{field}'")
        if g.get("author") and g["author"] not in config.get("authors", {}):
            errors.append(f"guide {gid}: unknown author '{g['author']}'")
        for rid in g.get("deal_ids", []):
            if rid not in known_ids:
                errors.append(f"guide {gid}: deal_ids entry '{rid}' does not exist")

    if root is not None:
        images = [ev.get("image") for ev in (events or {}).get("events", [])]
        images += [g.get("image") for g in guides or []]
        images += [f"assets/art/cat-{c}.svg" for c in categories]
        images += [f"assets/art/event-{s}.svg" for s in event_slugs]
        for img in filter(None, images):
            if not image_size(Path(root) / img):
                errors.append(f"image {img}: missing or has no width and height")
    return errors


# --------------------------------------------------------------------------
# Prune
# --------------------------------------------------------------------------

def prune(root, today):
    """Move deals whose expires is before today into data/archive.json."""
    deals_path, archive_path = root / "data" / "deals.json", root / "data" / "archive.json"
    data = load_json(deals_path)
    archive = load_json(archive_path, {"deals": []})
    keep, moved = [], []
    for deal in data["deals"]:
        (moved if parse_date(deal["expires"]) < today else keep).append(deal)
    archived = {d["id"] for d in archive["deals"]}
    added = 0
    for deal in moved:
        if deal["id"] not in archived:
            archive["deals"].append(deal)
            archived.add(deal["id"])
            added += 1
    data["deals"] = keep
    write_json(deals_path, data)
    write_json(archive_path, archive)
    print(f"Pruned {len(moved)} expired deal(s); {added} new in archive.json.")
    return moved


# --------------------------------------------------------------------------
# Site model
# --------------------------------------------------------------------------

class Page:
    def __init__(self, path, kind, title, description, render, **kw):
        self.path = path                  # "" for home, "c/tech/", "404.html"
        self.kind = kind
        self.title = title
        self.description = description
        self.render = render              # function(site, page) -> main HTML
        self.noindex = kw.get("noindex", False)
        self.sitemap = kw.get("sitemap", "pages")  # pages | deals | guides | None
        self.crumbs = kw.get("crumbs")    # list of (label, path or None)
        self.redirect = kw.get("redirect")  # path to send readers to
        self.published = kw.get("published")
        self.image = kw.get("image")
        self.root_links = kw.get("root_links", False)
        self.entity = kw.get("entity")    # the deal / guide / event dict, category or author slug
        self.updated = None

    @property
    def depth(self):
        return self.path.count("/") if self.path.endswith("/") else 0

    @property
    def prefix(self):
        if self.root_links:
            return "/"
        return "../" * self.depth if self.depth else "./"

    @property
    def out_file(self):
        return self.path + "index.html" if self.path.endswith("/") or not self.path else self.path


class Site:
    def __init__(self, root, today):
        self.root = Path(root)
        self.today = today
        self.config = load_json(self.root / "site.config.json")
        data = load_json(self.root / "data" / "deals.json")
        self.updated_data = data.get("updated")
        self.deals = data.get("deals", [])
        self.archive = load_json(self.root / "data" / "archive.json", {"deals": []})["deals"]
        self.events = load_json(self.root / "data" / "events.json", {"events": []})
        guide_dir = self.root / "data" / "guides"
        self.guides = [load_json(p) for p in sorted(guide_dir.glob("*.json"))] if guide_dir.exists() else []
        self.state = load_json(self.root / "data" / "page-state.json", {})
        self.photos = load_json(self.root / "data" / "photos.json", {"photos": {}}).get("photos", {})
        self._img_cache = {}

    # --- data views --------------------------------------------------------

    def retailer_name(self, deal):
        return self.config["retailers"][deal["retailer"]]["name"]

    def category_name(self, slug):
        return self.config["categories"][slug]

    def live_deals(self):
        live = [d for d in self.deals if parse_date(d["expires"]) >= self.today]
        live.sort(key=lambda d: (d["expires"],))
        live.sort(key=lambda d: d["added"], reverse=True)
        live.sort(key=lambda d: not d.get("featured"))
        return live

    def all_known_deals(self):
        """Live file first, then archive; live wins on duplicate ids."""
        seen, out = set(), []
        for d in self.deals + self.archive:
            if d["id"] not in seen:
                seen.add(d["id"])
                out.append(d)
        return out

    def has_page(self, deal):
        return word_count(deal.get("write_up")) >= WRITE_UP_MIN_WORDS

    def deal_state(self, deal):
        """live | ended | stale | gone, from days since expiry."""
        days = (self.today - parse_date(deal["expires"])).days
        if days <= 0:
            return "live"
        if days > REDIRECT_AFTER_DAYS:
            return "gone"
        if days > NOINDEX_AFTER_DAYS:
            return "stale"
        return "ended"

    def page_deals(self):
        """Deals that have a page (live, ended, stale or gone)."""
        return [d for d in self.all_known_deals() if self.has_page(d)]

    def deal_link_target(self, deal):
        """Internal page path if the deal has a live page, else None."""
        if self.has_page(deal) and self.deal_state(deal) != "gone":
            return f"deals/{deal['id']}/"
        return None

    def event(self, slug):
        return next((ev for ev in self.events.get("events", []) if ev["slug"] == slug), None)

    def event_status(self, ev):
        start, end = parse_date(ev["start"]), parse_date(ev["end"])
        if self.today < start:
            return "upcoming"
        if self.today > end:
            return "past"
        return "live"

    def related_live(self, deal, n=3):
        live = [d for d in self.live_deals() if d["id"] != deal["id"]]
        by_id = {d["id"]: d for d in live}
        picks = [by_id[r] for r in deal.get("related", []) if r in by_id]
        for pool in ([d for d in live if d["category"] == deal["category"]], live):
            for d in pool:
                if len(picks) >= n:
                    break
                if d not in picks:
                    picks.append(d)
        return picks[:n]

    def edition_number(self):
        launch = parse_date(self.config.get("launch_date")) or self.today
        return max(1, (self.today - launch).days + 1)

    def img(self, rel_path):
        if rel_path not in self._img_cache:
            self._img_cache[rel_path] = image_size(self.root / rel_path) or (480, 320)
        return self._img_cache[rel_path]

    def art(self, key, alt=""):
        """Art for a slot such as 'cat-tech', 'event-black-friday' or 'guide-<slug>'.

        A treated photo from data/photos.json wins; otherwise the illustration.
        Returns a dict: src, src2x (or None), w, h, alt, remote, credit (or None).
        """
        ph = self.photos.get(key)
        if ph:
            w, h = self.img(ph["file"])
            return {"src": ph["file"], "src2x": ph.get("file_2x"), "w": w, "h": h,
                    "alt": ph.get("alt", alt), "remote": False, "credit": ph}
        path = f"assets/art/{key}.svg"
        if not (self.root / path).is_file():
            return None
        w, h = self.img(path)
        return {"src": path, "src2x": None, "w": w, "h": h, "alt": alt, "remote": False, "credit": None}

    def product_image_ok(self, deal):
        im = deal.get("image")
        return bool(im) and not product_image_errors(self.config, deal)

    def share(self, key):
        """PNG share card from scripts/dev/make_share_images.py, or None."""
        path = f"assets/share/{key}.png"
        return path if (self.root / path).is_file() else None

    def deal_share_image(self, deal):
        if deal["category"] == "events" and deal.get("event"):
            return f"assets/art/event-{deal['event']}.svg"
        return f"assets/art/cat-{deal['category']}.svg"

    def deal_art(self, deal):
        """The exact product's photo, when its retailer's program allows it; otherwise None.

        A deal never shows a stand-in picture (a department photo or drawing), because
        readers take any picture on a deal to be the item being sold.
        """
        if self.product_image_ok(deal):
            im = deal["image"]
            return {"src": im["url"], "src2x": None, "w": im["width"], "h": im["height"],
                    "alt": im["alt"], "remote": True, "credit": None, "product": True}
        return None

    def abs_url(self, path):
        return self.config["base_url"].rstrip("/") + "/" + path


# --------------------------------------------------------------------------
# Shared fragments
# --------------------------------------------------------------------------

def link(page, target):
    return page.prefix + target


def art_html(page, art, cls, lead=False, decorative=False, caption=False):
    """<img> for an art dict from Site.art / Site.deal_art, with 2x srcset and an optional photo credit."""
    if not art:
        return ""
    src = art["src"] if art["remote"] else link(page, art["src"])
    srcset = f' srcset="{src} 1x, {link(page, art["src2x"])} 2x"' if art.get("src2x") else ""
    alt = "" if decorative else art.get("alt", "")
    loading = 'fetchpriority="high"' if lead else 'loading="lazy"'
    extra = ' referrerpolicy="no-referrer"' if art["remote"] else ""
    img = (f'<img class="{cls}" src="{e(src)}"{srcset} width="{art["w"]}" height="{art["h"]}" alt="{e(alt)}" '
           f'{loading} decoding="async"{extra}>')
    cr = art.get("credit")
    if caption and cr:
        who = f'<a href="{e(cr["source_url"])}" rel="nofollow noopener">{t(cr["credit"])}</a>'
        img = (f'<figure class="art-fig {cls}-fig">{img}'
               f'<figcaption class="credit">Photo: {who} / {t(cr["source"])}</figcaption></figure>')
    return img


def time_el(d):
    return f'<time datetime="{d.isoformat()}">{fmt_date(d)}</time>'


def timing_text(site, deal):
    days = (parse_date(deal["expires"]) - site.today).days
    if days <= 0:
        return "Last day"
    if days == 1:
        return "Ends tomorrow"
    if days <= 7:
        return f"Ends in {days} days"
    return f"Through {fmt_date(parse_date(deal['expires']))}"


def out_attrs():
    return 'target="_blank" rel="sponsored nofollow noopener"'


def mark(site, name, cls=""):
    """Inline an annotation mark SVG so it can draw itself on scroll."""
    svg = (site.root / "assets" / "art" / "marks" / f"{name}.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg).strip()
    return svg.replace('class="mark ', f'class="mark {cls} ', 1) if cls else svg


def timing_html(site, deal):
    text = timing_text(site, deal)
    urgent = " card__timing--urgent" if text in ("Last day", "Ends tomorrow") else ""
    return f'<span class="card__timing{urgent}">{v(text)}</span>'


def deal_card(site, page, deal, variant="standard", lead=False, annotate=None):
    """One deal in one of four variants: lead, feature, standard, compact."""
    retailer = site.retailer_name(deal)
    category = site.category_name(deal["category"])
    out = e(affiliate_url(site.config, deal))
    internal = site.deal_link_target(deal)
    title_href = link(page, internal) if internal else out
    title_attrs = "" if internal else " " + out_attrs()
    search = " ".join([deal["title"], deal["blurb"], retailer, category]).lower()
    art = site.deal_art(deal) if variant != "compact" else None
    classes = (f"card card--{variant}" + (" card--featured" if deal.get("featured") and variant != "compact" else "")
               + ("" if art or variant == "compact" else " card--noart"))
    parts = [f'<article class="{classes}" data-search="{e(search)}">']
    if art:
        img = art_html(page, art, "card__art", lead=lead)
        if annotate == "pick":
            img = f'<div class="card__artwrap">{img}{mark(site, "editors-pick", "annot annot--pick")}</div>'
        parts.append(img)
    elif annotate == "pick" and variant != "compact":
        parts.append(mark(site, "editors-pick", "annot annot--pick"))
    parts.append('<div class="card__body">')
    parts.append(f'<p class="card__meta label"><b>{t(retailer)}</b> · {t(category)}</p>')
    tag = "h2" if variant == "lead" else "h3"
    parts.append(f'<{tag} class="card__title"><a href="{title_href}"{title_attrs}>{t(deal["title"])}</a></{tag}>')
    if variant != "compact":
        parts.append(f'<p class="card__blurb">{t(deal["blurb"])}</p>')
    if variant == "lead" and deal.get("who_for"):
        parts.append(f'<p class="card__note"><span class="label">Editor’s note</span>{t("Best for " + deal["who_for"][0].lower() + deal["who_for"][1:])}</p>')
    if variant == "compact":
        parts.append(timing_html(site, deal))
    else:
        badges = []
        if deal["added"] == site.today.isoformat():
            badges.append(v('<span class="stamp">New today</span>'))
        if deal.get("label"):
            badges.append(f'<span class="tag" style="--tilt:{tilt(deal["id"])}deg"><span>{t(deal["label"])}</span></span>')
        badges.append(timing_html(site, deal))
        parts.append(f'<div class="card__badges">{"".join(badges)}</div>')
        if internal:
            parts.append(f'<p class="card__more"><a href="{link(page, internal)}">Read our take on the {t(deal.get("short_name") or deal["title"])} deal</a></p>')
        parts.append(f'<a class="button" href="{out}" {out_attrs()}>See deal at {t(retailer)} →</a>')
    parts.append("</div></article>")
    return "\n".join(parts)


def breadcrumbs(page):
    if not page.crumbs:
        return ""
    items = []
    for label, target in page.crumbs:
        if target is None:
            items.append(f'<li aria-current="page">{t(label)}</li>')
        else:
            items.append(f'<li><a href="{link(page, target)}">{t(label)}</a></li>')
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'


def updated_line(page, label="Updated"):
    pub = ""
    if page.published:
        pub = f'Published {time_el(page.published)} · '
    return f'<p class="dateline">{pub}{label} {UPDATED_TOKEN}</p>'


HEAD_SCRIPT = ("<script>document.documentElement.classList.add('js');"
               "try{var t=localStorage.getItem('vd-theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>")


# --------------------------------------------------------------------------
# CSS: minify, and inline only what each page type needs above the fold
# --------------------------------------------------------------------------

CRITICAL_MAX = 14 * 1024
_CSS_TOKEN = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|url\([^)]*\))""")


def css_minify(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for i, part in enumerate(_CSS_TOKEN.split(css)):
        if i % 2:                       # strings and url(...) stay exactly as written
            out.append(part)
            continue
        part = re.sub(r"\s+", " ", part)
        part = re.sub(r"\s*([{};,>])\s*", r"\1", part)
        part = re.sub(r":\s+", ":", part)
        part = part.replace(";}", "}")
        out.append(part)
    return "".join(out).strip()


def css_sections(css):
    """Split style.css at its section comments. A header may say [defer] (never inlined)
    or [only: kind,kind] (inlined only on those page kinds)."""
    sections, cur = [], {"kinds": None, "defer": False, "text": []}
    for line in css.splitlines(keepends=True):
        m = re.match(r"/\*[^\n]*\*/\s*$", line)
        if m and line.startswith("/*"):
            sections.append(cur)
            only = re.search(r"\[only:\s*([a-z,\s-]+)\]", line)
            cur = {"kinds": {k.strip() for k in only.group(1).split(",")} if only else None,
                   "defer": "[defer]" in line, "text": [line]}
        else:
            cur["text"].append(line)
    sections.append(cur)
    return sections


def critical_css(site, page):
    if not hasattr(site, "_css_sections"):
        site._css_sections = css_sections((site.root / "assets" / "style.css").read_text(encoding="utf-8"))
        site._critical = {}
    kind = page.kind
    if kind not in site._critical:
        css = "".join("".join(sec["text"]) for sec in site._css_sections
                      if not sec["defer"] and (sec["kinds"] is None or kind in sec["kinds"]))
        site._critical[kind] = css_minify(css)
    css = site._critical[kind]
    # Inlined CSS lives in the page, so asset urls need the page's path to assets/.
    return re.sub(r"url\(((?:fonts|art|photos)/[^)]+)\)", lambda m: f"url({page.prefix}assets/{m.group(1)})", css)


# --------------------------------------------------------------------------
# Social tags and structured data
# --------------------------------------------------------------------------

def social_tags(site, page):
    c = site.config
    article = page.kind in ("guide", "deal")
    tags = [f'<meta property="og:type" content="{"article" if article else "website"}">']
    if page.image:
        w, h = site.img(page.image)
        alt = f"{c['site_name']}: {page.title.split(' | ')[0]}"
        tags += [f'<meta property="og:image" content="{e(site.abs_url(page.image))}">',
                 f'<meta property="og:image:width" content="{w}">',
                 f'<meta property="og:image:height" content="{h}">',
                 f'<meta property="og:image:alt" content="{e(smart(alt))}">',
                 '<meta name="twitter:card" content="summary_large_image">']
    if article and page.published:
        tags.append(f'<meta property="article:published_time" content="{page.published.isoformat()}">')
    if article and page.updated:
        tags.append(f'<meta property="article:modified_time" content="{page.updated.isoformat()}">')
    return "".join(tags)


def jsonld(site, page):
    """The JSON-LD graph for a page (spec: SEO > Structured data)."""
    c = site.config
    base = c["base_url"].rstrip("/") + "/"
    url = site.abs_url(page.path)
    org_id, site_id = base + "#organization", base + "#website"
    org = {"@type": "Organization", "@id": org_id, "name": c["site_name"], "url": base}
    if c.get("logo"):
        w, h = site.img(c["logo"])
        org["logo"] = {"@type": "ImageObject", "url": site.abs_url(c["logo"]), "width": w, "height": h}
    if c.get("social_profiles"):
        org["sameAs"] = c["social_profiles"]
    graph = [org, {
        "@type": "WebSite", "@id": site_id, "url": base, "name": c["site_name"],
        "description": c["description"], "publisher": {"@id": org_id}, "inLanguage": "en-US",
        "potentialAction": {"@type": "SearchAction",
                            "target": {"@type": "EntryPoint", "urlTemplate": base + "?q={search_term_string}"},
                            "query-input": "required name=search_term_string"}}]

    if page.crumbs:
        items = []
        for i, (label, path) in enumerate(page.crumbs, 1):
            item = {"@type": "ListItem", "position": i, "name": label}
            item["item"] = site.abs_url(path) if path is not None else url
            items.append(item)
        graph.append({"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": items})

    def item_list(deals, name):
        urls = [site.abs_url(f"deals/{d['id']}/") for d in deals if site.has_page(d)]
        if urls:
            graph.append({"@type": "ItemList", "@id": url + "#deals", "name": name, "numberOfItems": len(urls),
                          "itemListElement": [{"@type": "ListItem", "position": i, "url": u}
                                              for i, u in enumerate(urls, 1)]})

    live = site.live_deals()
    ent = page.entity
    if page.kind == "home":
        item_list(live, "Today's best deals")
    elif page.kind == "department":
        item_list([d for d in live if d["category"] == ent], f"Best {site.category_name(ent)} deals today")
    elif page.kind == "event":
        item_list([d for d in live if d.get("event") == ent["slug"]], f"Best {ent['name']} deals")

    def person(slug):
        a = c["authors"][slug]
        return {"@type": a.get("schema_type", "Person"), "name": a["name"], "url": site.abs_url(f"authors/{slug}/")}

    if page.kind == "guide":
        g = ent
        art = site.art(f"guide-{g['slug']}")
        image = site.abs_url(art["src2x"] or art["src"]) if art else site.abs_url(g["image"])
        graph.append({"@type": "Article", "@id": url + "#article", "headline": smart(g["title"])[:110],
                      "description": smart(page.description), "image": [image, site.abs_url(page.image)] if page.image else [image],
                      "author": person(g["author"]), "publisher": {"@id": org_id},
                      "datePublished": g["published"], "dateModified": page.updated.isoformat(),
                      "mainEntityOfPage": url, "isPartOf": {"@id": site_id}})
    elif page.kind == "author":
        graph.append({"@type": "ProfilePage", "@id": url, "url": url, "name": page.title,
                      "isPartOf": {"@id": site_id},
                      "mainEntity": dict(person(ent), description=smart(c["authors"][ent]["bio"]))})
    elif page.kind == "deal":
        d = ent
        # No Product/Offer: no price is shown (spec), and a Product without offers is invalid.
        graph.append({"@type": "WebPage", "@id": url, "url": url, "name": smart(page.title),
                      "description": smart(page.description), "isPartOf": {"@id": site_id},
                      "breadcrumb": {"@id": url + "#breadcrumb"},
                      "datePublished": d["added"], "dateModified": page.updated.isoformat(),
                      "author": person(d.get("author") or c.get("default_author", "viewdeals-desk")),
                      "about": {"@type": "Thing", "name": smart(d["title"])}})
    return {"@context": "https://schema.org", "@graph": graph}


def jsonld_tag(site, page):
    if page.kind == "redirect":
        return ""
    data = json.dumps(jsonld(site, page), ensure_ascii=False, separators=(",", ":"))
    return '<script type="application/ld+json">' + data.replace("</", "<\\/") + "</script>"


def layout(site, page, main):
    c = site.config
    canonical = site.abs_url(page.path)
    if page.redirect:
        canonical = site.abs_url(page.redirect)
    robots = '<meta name="robots" content="noindex">' if page.noindex else ""
    verification = ""
    if c.get("verification", {}).get("google"):
        verification += f'<meta name="google-site-verification" content="{e(c["verification"]["google"])}">'
    if c.get("verification", {}).get("bing"):
        verification += f'<meta name="msvalidate.01" content="{e(c["verification"]["bing"])}">'
    refresh = ""
    if page.redirect:
        refresh = f'<meta http-equiv="refresh" content="0; url={link(page, page.redirect)}">'
    p = page.prefix
    chips = "".join(
        f'<li><a href="{link(page, f"c/{slug}/")}"'
        + (' aria-current="page"' if page.path == f"c/{slug}/" else "")
        + f'>{t(name)}</a></li>'
        for slug, name in c["categories"].items())
    events = "".join(
        f'<li><a href="{link(page, "events/" + ev["slug"] + "/")}">{t(ev["name"])} deals</a></li>'
        for ev in site.events.get("events", []))
    count = len(site.live_deals())
    edition = v(f'No. {site.edition_number()} · {fmt_long(site.today)} · {count} deal{"s" if count != 1 else ""} today')
    body_class = f"page--{page.kind} " + ("page--home" if page.kind == "home" else "page--inner")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t(page.title)}</title>
<meta name="description" content="{e(smart(page.description))}">
<link rel="canonical" href="{e(canonical)}">
{robots}{refresh}{verification}
<meta name="theme-color" content="#F4EFE6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141210" media="(prefers-color-scheme: dark)">
<meta property="og:site_name" content="{e(c['site_name'])}">
<meta property="og:title" content="{e(smart(page.title))}">
<meta property="og:description" content="{e(smart(page.description))}">
<meta property="og:url" content="{e(canonical)}">
{social_tags(site, page)}
<link rel="icon" href="{p}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{e(c['site_name'])} deals" href="{p}feed.xml">
<link rel="alternate" type="application/feed+json" title="{e(c['site_name'])} deals" href="{p}feed.json">
<link rel="preload" href="{p}assets/fonts/newsreader-roman.woff2" as="font" type="font/woff2" crossorigin>
<style>{critical_css(site, page)}</style>
<link rel="stylesheet" href="{p}assets/style.css" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="{p}assets/style.css"></noscript>
{jsonld_tag(site, page)}
{HEAD_SCRIPT}
<script src="{p}assets/app.js" defer></script>
</head>
<body class="{body_class}">
<a class="skip" href="#main">Skip to the deals</a>
<header class="masthead wrap">
<p class="masthead__name"><a href="{p}">{t(c['site_name'])}</a></p>
<hr class="masthead__rule">
<div class="masthead__row"><p class="masthead__edition label">{edition}</p><p class="masthead__tagline">{t(c['tagline'])}</p></div>
</header>
<nav class="deptbar" aria-label="Departments"><div class="wrap deptbar__inner"><a class="deptbar__logo" href="{p}">{t(c['site_name'])}</a><ul>{chips}</ul></div></nav>
<aside class="disclosure-bar" aria-label="Affiliate disclosure"><div class="wrap"><p>{t(c['disclosure_short'])} <a href="{p}disclosure/">How we make money</a></p></div></aside>
<main id="main" class="wrap">
{breadcrumbs(page)}
{main}
</main>
<footer class="footer wrap">
<div class="footer__cols">
<nav aria-label="Sale events"><h2>Sale events</h2><ul>{events}</ul></nav>
<nav aria-label="About this site"><h2>About</h2><ul>
<li><a href="{p}about/">About ViewDeals</a></li>
<li><a href="{p}how-we-pick/">How we pick deals</a></li>
<li><a href="{p}disclosure/">Affiliate disclosure</a></li>
<li><a href="{p}privacy/">Privacy</a></li>
<li><a href="{p}feed.xml">RSS feed</a></li>
</ul></nav>
<div><h2>Edition</h2><p>Read the day edition or the night edition.</p><button class="theme-toggle" type="button" data-theme-toggle>Switch to night edition</button></div>
</div>
<div class="footer__fine">
<p>Prices and availability change often and are set by each retailer. Check the retailer’s page before you buy.</p>
<p>As an Amazon Associate, ViewDeals earns from qualifying purchases. Amazon and the Amazon logo are trademarks of Amazon.com, Inc. or its affiliates.</p>
<p>Questions or corrections: <a href="mailto:{e(c['contact_email'])}">{t(c['contact_email'])}</a></p>
</div>
</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Page bodies
# --------------------------------------------------------------------------

def page_head(site, page, h1, kicker=None, dek=None, art=None, art_alt="", extra="", dateline=True):
    """Section-front header: kicker, H1, dek, dateline, optional illustration."""
    parts = ['<header class="page-head' + (' page-head--art' if art else '') + '"><div class="page-head__text">']
    if kicker:
        parts.append(f'<p class="label page-head__kicker">{kicker}</p>')
    parts.append(f"<h1>{t(h1)}</h1>")
    if dek:
        parts.append(f'<p class="dek">{dek}</p>')
    if dateline:
        parts.append(updated_line(page))
    parts.append(extra + "</div>")
    if art:
        parts.append(art_html(page, art, "page-head__art", lead=True, decorative=not art.get("credit") and not art_alt, caption=True)
                     if isinstance(art, dict) else "")
    parts.append("</header>")
    return "".join(parts)


def deal_stream(site, page, deals, std=6, hits=4):
    """Rows of standard cards, interrupted by a compact quick-hits list so no page is a wall of tiles."""
    out, i = [], 0
    while i < len(deals):
        chunk = deals[i:i + std]
        i += len(chunk)
        out.append('<div class="grid stream">' + "".join(
            f'<div class="span-4">{deal_card(site, page, d)}</div>' for d in chunk) + "</div>")
        rest = deals[i:i + hits]
        if len(rest) >= 2 and len(deals) - i > 1:
            i += len(rest)
            out.append('<section class="quick-hits" data-search-section aria-label="Quick hits"><h3 class="quick-hits__head">Quick hits</h3>'
                       f'<div class="quick-hits__list">{"".join(deal_card(site, page, d, "compact") for d in rest)}</div></section>')
    return "".join(out)


def deals_block(site, page, deals, annotate_first=False):
    """One feature card, then the stream."""
    if not deals:
        return ""
    first, rest = deals[0], deals[1:]
    head = f'<div class="grid section-lead"><div class="span-12">{deal_card(site, page, first, "feature", lead=True, annotate="pick" if annotate_first else None)}</div></div>'
    return head + deal_stream(site, page, rest)


def render_home(site, page):
    live = site.live_deals()
    featured = [d for d in live if d.get("featured")]
    lead = featured[0] if featured else (live[0] if live else None)
    picks = [d for d in featured if d is not lead][:2]
    others = [d for d in live if d is not lead and d not in picks]
    soon = sorted([d for d in live if d is not lead], key=lambda d: d["expires"])[:5]
    count = len(live)
    out = [
        '<div class="front-index">',
        '<div><h1>Today’s best deals</h1>',
        updated_line(page),
        f'<p class="count label">{v(f"{count} live deal" + ("s" if count != 1 else ""))} · hand-checked this morning</p></div>',
        '<form class="search" role="search" action="./" method="get">'
        '<label for="q">Search today’s deals</label>'
        '<input id="q" name="q" type="search" autocomplete="off" placeholder="Try “headphones” or “gift”"></form>',
        "</div>",
        '<p id="search-empty" class="empty" hidden>No deals match that search. Try a product type, a brand or a store.</p>',
    ]
    if lead:
        out.append('<div class="grid front">')
        out.append(f'<section class="span-8 front__lead" data-search-section aria-label="Lead deal">{deal_card(site, page, lead, "lead", lead=True, annotate="pick")}</section>')
        if soon:
            out.append('<aside class="front__soon" data-search-section aria-labelledby="soon-h"><h2 id="soon-h">Ending soon</h2>'
                       + "".join(deal_card(site, page, d, "compact") for d in soon) + "</aside>")
        out.append("</div>")
    if picks:
        out.append('<section class="section" data-search-section aria-labelledby="picks-h"><h2 class="section-head" id="picks-h">Top picks</h2>'
                   '<div class="grid">' + "".join(f'<div class="span-6">{deal_card(site, page, d, "feature")}</div>' for d in picks) + "</div></section>")
    if others:
        out.append('<section class="section" data-search-section aria-labelledby="all-h">'
                   f'<h2 class="section-head" id="all-h">All live deals <span class="label">{v(str(len(others)) + " more")}</span></h2>'
                   + deal_stream(site, page, others) + "</section>")
    if not live:
        out.append('<p class="empty">No live deals right now. The next edition lands tomorrow morning.</p>')
    out.append(sale_calendar(site, page))
    return "\n".join(out)


def sale_calendar(site, page, exclude=None):
    rows = []
    for ev in site.events.get("events", []):
        if ev["slug"] == exclude:
            continue
        status = site.event_status(ev)
        start, end = parse_date(ev["start"]), parse_date(ev["end"])
        when = f"{fmt_date(start)} – {fmt_date(end)}" + ("" if ev.get("dates_confirmed") else " (expected)")
        state = {"live": "On now", "upcoming": "Coming up", "past": "Ended"}[status]
        art = art_html(page, site.art(f"event-{ev['slug']}"), "calendar__art", decorative=True)
        rows.append(f'<li class="calendar__item calendar__item--{status}">{art}'
                    f'<div><p class="label">{v(state)}</p><h3><a href="{link(page, "events/" + ev["slug"] + "/")}">{t(ev["name"])} {ev["start"][:4]} deals</a></h3>'
                    f'<p class="calendar__when">{when}</p></div></li>')
    return ('<section class="section calendar" aria-labelledby="cal-h"><h2 class="section-head" id="cal-h">Sale calendar</h2>'
            f'<ul class="calendar__list">{"".join(rows)}</ul></section>')


def render_category(slug):
    def render(site, page):
        name = site.category_name(slug)
        deals = [d for d in site.live_deals() if d["category"] == slug]
        n = len(deals)
        dek = (f"{n} live deal{'s' if n != 1 else ''} in {t(name)}, picked and checked by hand this morning."
               if n else f"Nothing in {t(name)} today. Some days a section stays quiet.")
        out = [page_head(site, page, f"Best {name} deals today", kicker="Department", dek=v(dek),
                         art=site.art(f"cat-{slug}"))]
        if deals:
            out.append(f'<section aria-labelledby="deals-h"><h2 class="visually-hidden" id="deals-h">Live {e(name)} deals</h2>'
                       f'{deals_block(site, page, deals, annotate_first=True)}</section>')
        else:
            out.append(f'<div class="empty-state"><p class="empty">We only list deals we would buy ourselves, so some days {t(name)} has nothing worth your time.</p>'
                       f'<p><a class="button button--quiet" href="{link(page, "")}">See all of today’s deals →</a></p></div>')
        return "\n".join(out)
    return render


def render_event(slug):
    def render(site, page):
        ev = site.event(slug)
        status = site.event_status(ev)
        year = ev["start"][:4]
        start, end = parse_date(ev["start"]), parse_date(ev["end"])
        when = f"{fmt_date(start)} – {fmt_date(end)}" + ("" if ev.get("dates_confirmed") else ", expected; not yet announced")
        state = {"live": "On now", "upcoming": "Coming up", "past": "Ended for " + year}[status]
        deals = [d for d in site.live_deals() if d.get("event") == slug]
        out = [page_head(site, page, f"Best {ev['name']} deals {year}", kicker=f"Sale event · {v(state)}",
                         dek=t(ev["intro"]), art=site.art(f"event-{slug}"),
                         extra=f'<p class="event-dates"><span class="label">Dates</span> {when}</p>')]
        if deals:
            out.append(f'<section aria-labelledby="deals-h"><h2 class="visually-hidden" id="deals-h">Live {e(ev["name"])} deals</h2>'
                       f'{deals_block(site, page, deals, annotate_first=True)}</section>')
        elif status == "upcoming":
            out.append(f'<div class="empty-state"><p class="empty">{t(ev["name"])} hasn’t started yet. We add deals here the day retailers do.</p>'
                       f'<p><a class="button button--quiet" href="{link(page, "")}">See today’s best deals →</a></p></div>')
        else:
            out.append(f'<div class="empty-state"><p class="empty">No {t(ev["name"])} deals are live right now.</p>'
                       f'<p><a class="button button--quiet" href="{link(page, "")}">See today’s best deals →</a></p></div>')
        out.append(sale_calendar(site, page, exclude=slug))
        return "\n".join(out)
    return render


def byline(site, page, slug=None):
    slug = slug or site.config.get("default_author")
    author = site.config.get("authors", {}).get(slug)
    if not author:
        return ""
    return f'<p class="byline">By <a href="{link(page, "authors/" + slug + "/")}">{t(author["name"])}</a></p>'


def deal_box(site, page, deal):
    retailer = site.retailer_name(deal)
    state = site.deal_state(deal)
    if state != "live":
        return (f'<div class="deal-box deal-box--ended"><p class="label">The deal</p><p class="deal-box__retailer">{t(retailer)}</p>'
                f'<p>Ended {fmt_date(parse_date(deal["expires"]))}.</p>'
                f'<a class="button button--quiet" href="{link(page, "c/" + deal["category"] + "/")}">Live {t(site.category_name(deal["category"]))} deals →</a></div>')
    tag = f'<span class="tag" style="--tilt:{tilt(deal["id"])}deg"><span>{t(deal["label"])}</span></span>' if deal.get("label") else ""
    return (f'<div class="deal-box"><p class="label">The deal</p><p class="deal-box__retailer">{t(retailer)}</p>'
            f'<div class="card__badges">{tag}{timing_html(site, deal)}</div>'
            f'<a class="button" href="{e(affiliate_url(site.config, deal))}" {out_attrs()}>See deal at {t(retailer)} →</a>'
            f'<p class="deal-box__note">Prices and stock are set by {t(retailer)} and change often. We may earn a commission.</p></div>')


def render_deal(deal):
    def render(site, page):
        state = site.deal_state(deal)
        retailer = site.retailer_name(deal)
        cat = deal["category"]
        main = []
        if state != "live":
            main.append(f'<div class="ended" role="status"><p><strong>This deal has ended.</strong> It ran until '
                        f'{fmt_date(parse_date(deal["expires"]))}. The live deals below are worth a look instead.</p></div>')
        main.append(page_head(site, page, f"{deal['title']} deal",
                              kicker=f'{t(retailer)} · <a href="{link(page, "c/" + cat + "/")}">{t(site.category_name(cat))}</a>',
                              dek=t(deal["blurb"]), extra=byline(site, page)))
        if state == "live":
            main.append(f'<p class="deal-cta--inline"><a class="button" href="{e(affiliate_url(site.config, deal))}" {out_attrs()}>See deal at {t(retailer)} →</a></p>')
        art = site.deal_art(deal)
        if art:
            main.append(art_html(page, art, "article__art"))
        main.append('<div class="prose">' + "".join(f"<p>{t(p)}</p>" for p in deal["write_up"]) + "</div>")
        if deal.get("who_for") or deal.get("skip_if"):
            fit = '<dl class="fit">'
            if deal.get("who_for"):
                fit += f'<dt>Who it’s for</dt><dd>{t(deal["who_for"])}</dd>'
            if deal.get("skip_if"):
                fit += f'<dt>Skip it if</dt><dd>{t(deal["skip_if"])}</dd>'
            main.append(fit + "</dl>")
        more = [f'<li><a href="{link(page, "c/" + cat + "/")}">More {t(site.category_name(cat))} deals</a></li>']
        ev = site.event(deal.get("event")) if deal.get("event") else None
        if ev and site.event_status(ev) == "live":
            more.append(f'<li><a href="{link(page, "events/" + ev["slug"] + "/")}">All {t(ev["name"])} deals</a></li>')
        more.append(f'<li><a href="{link(page, "how-we-pick/")}">How we pick deals</a></li>')
        side = deal_box(site, page, deal) + f'<nav class="more" aria-label="More deals"><p class="label">Keep reading</p><ul>{"".join(more)}</ul></nav>'
        out = [f'<div class="grid article"><article class="span-8 article__main">{"".join(main)}</article>'
               f'<aside class="span-4 article__side">{side}</aside></div>']
        related = site.related_live(deal)
        if related:
            out.append('<section class="section related" aria-labelledby="rel-h"><h2 class="section-head" id="rel-h">Related deals</h2>'
                       '<div class="grid">' + "".join(f'<div class="span-4">{deal_card(site, page, d)}</div>' for d in related) + "</div></section>")
        return "\n".join(out)
    return render


def render_redirect(deal):
    def render(site, page):
        return (f'<h1>This deal has ended</h1><p>The {t(deal["title"])} deal ended on {fmt_date(parse_date(deal["expires"]))}. '
                f'<a href="{link(page, page.redirect)}">See today’s {t(site.category_name(deal["category"]))} deals</a>.</p>')
    return render


def pin_link(site, page, guide):
    """A plain "Save to Pinterest" link (no Pinterest script, so no third-party request)."""
    media = page.image or guide["image"]
    q = urlencode({"url": site.abs_url(page.path), "media": site.abs_url(media), "description": smart(guide["title"])})
    return (f'<p class="pin"><a href="https://www.pinterest.com/pin/create/button/?{e(q)}" '
            f'target="_blank" rel="noopener">Save this guide to Pinterest</a></p>')


def render_guide(guide):
    def render(site, page):
        by_id = {d["id"]: d for d in site.all_known_deals()}
        picks = [by_id[i] for i in guide["deal_ids"] if i in by_id and site.deal_state(by_id[i]) == "live"]
        main = [page_head(site, page, guide["title"], kicker=t(guide.get("kicker", "Guide")), dek=t(guide["dek"]),
                          extra=byline(site, page, guide["author"]) + pin_link(site, page, guide))]
        art = site.art(f"guide-{guide['slug']}")
        if not art:
            w, h = site.img(guide["image"])
            art = {"src": guide["image"], "src2x": None, "w": w, "h": h, "alt": guide.get("image_alt", ""),
                   "remote": False, "credit": None}
        main.append(art_html(page, art, "article__art article__art--wide", lead=True, caption=True))
        body = []
        for sec in guide["sections"]:
            body.append(f"<h2>{t(sec['heading'])}</h2>")
            body.extend(f"<p>{t(p)}</p>" for p in sec.get("paragraphs", []))
        main.append('<div class="prose prose--guide">' + "".join(body) + "</div>")
        toc = "".join(f'<li><a href="{link(page, site.deal_link_target(d))}">{t(d.get("short_name") or d["title"])}</a>'
                      f' <span class="label">{t(site.retailer_name(d))}</span></li>'
                      for d in picks if site.deal_link_target(d))
        side = f'<nav class="toc" aria-label="Deals in this guide"><p class="label">In this guide</p><ol>{toc}</ol></nav>' if toc else ""
        out = [f'<div class="grid article"><article class="span-8 article__main">{"".join(main)}</article>'
               f'<aside class="span-4 article__side">{side}</aside></div>']
        if picks:
            out.append('<section class="section" aria-labelledby="g-h"><h2 class="section-head" id="g-h">The deals in this guide</h2>'
                       + deal_stream(site, page, picks, std=3, hits=0) + "</section>")
        return "\n".join(out)
    return render


def render_author(slug):
    def render(site, page):
        a = site.config["authors"][slug]
        out = [page_head(site, page, a["name"], kicker="Byline", dek=t(a["bio"]), dateline=False,
                         extra=f'<p><a href="{link(page, "how-we-pick/")}">How we pick and check every deal</a></p>')]
        mine = [d for d in site.page_deals() if site.deal_state(d) in ("live", "ended")]
        if mine:
            out.append('<section class="section" aria-labelledby="w-h"><h2 class="section-head" id="w-h">Recent write-ups</h2>'
                       '<div class="quick-hits__list">' + "".join(deal_card(site, page, d, "compact") for d in mine) + "</div></section>")
        guides = [g for g in site.guides if g["author"] == slug]
        if guides:
            out.append('<section class="section" aria-labelledby="gd-h"><h2 class="section-head" id="gd-h">Guides</h2><ul class="plain-list">'
                       + "".join(f'<li><a href="{link(page, "guides/" + g["slug"] + "/")}">{t(g["title"])}</a></li>' for g in guides) + "</ul></section>")
        return "\n".join(out)
    return render


def static_body(heading, paragraphs, kicker=None, dek=None, more=None, steps=None):
    def render(site, page):
        body = "".join(f"<p>{p}</p>" for p in paragraphs)
        if steps:
            body += '<ol class="steps">' + "".join(
                f'<li>{mark(site, "checkmark", "steps__mark")}<div><h2>{t(h)}</h2><p>{t(p)}</p></div></li>' for h, p in steps) + "</ol>"
        extra = f'<p><a href="{link(page, more[1])}">{t(more[0])}</a></p>' if more else ""
        return (page_head(site, page, heading, kicker=kicker, dek=t(dek) if dek else None)
                + f'<div class="prose prose--page">{body}{extra}</div>')
    return render


def render_404(site, page):
    live = site.live_deals()[:3]
    out = [page_head(site, page, "That page is gone", kicker="Page not found", dek=t("The deal may have ended, or the link was mistyped."),
                     dateline=False, extra=f'<p><a class="button" href="/">See today’s best deals →</a></p>')]
    if live:
        out.append('<section class="section" aria-labelledby="nf-h"><h2 class="section-head" id="nf-h">Live right now</h2><div class="grid">'
                   + "".join(f'<div class="span-4">{deal_card(site, page, d)}</div>' for d in live) + "</div></section>")
    return "\n".join(out)


def photo_credits(site):
    """One paragraph crediting every photographer, grouped by person."""
    by = {}
    for ph in site.photos.values():
        by.setdefault((ph["credit"], ph["source"]), ph["source_url"])
    names = [f'<a href="{e(url)}" rel="nofollow noopener">{t(name)}</a> ({t(src)})' for (name, src), url in sorted(by.items())]
    listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
    return (t("Photographs on department, sale and guide pages are by ") + listed +
            t(", used under the Unsplash License and printed in our two-ink style. Product photos appear only where a retailer's affiliate program supplies them."))


def static_pages(site):
    c = site.config
    email = f'<a href="mailto:{e(c["contact_email"])}">{t(c["contact_email"])}</a>'
    pages = []
    pages.append(Page("about/", "about", "About ViewDeals: Who Picks the Deals and Why",
        "ViewDeals is a small, hand-run deals site. Here is who picks the deals, how they are checked, and why we never show Amazon prices.",
        static_body("About ViewDeals", [
            t("ViewDeals is a daily edition of hand-picked deals from Amazon, Walmart, Target and Best Buy. Every morning we read the retailers' own deal pages and the deal roundups we trust, check each offer ourselves, and publish the ones worth your time."),
            t("We'd rather list fifteen good deals than a hundred so-so ones. A deal makes the cut when the product is well known or well reviewed, the discount is real according to a recent source, and the retailer is one you already shop with."),
            t("You won't see Amazon prices or percent-off figures here. Amazon only allows prices that come straight from its own systems, and a page like this one can't promise a price is still current, so we tell you why a deal is good and let the retailer show you the price."),
            f'{t("Spotted a mistake or a deal that has ended? Tell us at")} {email}.',
        ] + ([photo_credits(site)] if site.photos else []), kicker="About", dek="A daily circular of deals worth your time, picked by a person.",
           more=("How we pick and check every deal", "how-we-pick/")),
        crumbs=[("Home", ""), ("About", None)]))
    pages.append(Page("disclosure/", "disclosure", "Affiliate Disclosure | ViewDeals",
        "How ViewDeals makes money: affiliate commissions from Amazon and other retailers when you buy through our links, and why that never decides what we pick.",
        static_body("Affiliate disclosure", [
            t("ViewDeals is a participant in the Amazon Services LLC Associates Program, an affiliate advertising program designed to provide a means for sites to earn advertising fees by advertising and linking to Amazon.com. As an Amazon Associate, ViewDeals earns from qualifying purchases."),
            t("We may also earn commissions from other retailers, including Walmart, Target and Best Buy, through affiliate networks such as Impact. When you buy through a link on this site, the retailer may pay us a small share of the sale. It costs you nothing extra."),
            t("Commissions never decide what we pick. We choose deals first and check whether a retailer pays us second, and we list deals that earn us nothing when they are the better buy. Links that can earn us money are marked as sponsored in the page code, as search engines ask."),
            f'{t("Questions about this page:")} {email}.',
        ], kicker="The fine print", dek="How this site pays for itself, in plain words."),
        crumbs=[("Home", ""), ("Disclosure", None)]))
    pages.append(Page("privacy/", "privacy", "Privacy Policy | ViewDeals",
        "ViewDeals has no accounts and collects no personal data. Here is what retailers, our host GitHub Pages and our cookieless analytics can see when you visit.",
        static_body("Privacy", [
            t("ViewDeals has no accounts, no newsletter sign-up and no comments, and we don't collect or sell personal data. The search box works entirely in your browser and sends nothing anywhere. If you pick the night edition, your browser remembers that choice; it never leaves your device."),
            t("When you click through to a retailer, that retailer may set its own cookies, including affiliate cookies that tell it the visit came from us. Their privacy policies apply once you are on their sites."),
            t("The site is hosted on GitHub Pages, which may log your IP address for security, as GitHub's privacy statement describes. If we turn on Cloudflare Web Analytics, it counts visits without cookies and without tracking you across sites."),
            f'{t("Privacy questions:")} {email}.',
        ], kicker="The fine print", dek="Short version: we don’t collect anything about you."),
        crumbs=[("Home", ""), ("Privacy", None)]))
    pages.append(Page("how-we-pick/", "method", "How We Pick and Check Every Deal | ViewDeals",
        "The rules behind every ViewDeals pick: where we look, what a deal must pass before it is listed, how we write it up, and when we take it down.",
        static_body("How we pick and check every deal", [
            t("Every morning we read the retailers' own deal pages and a short list of reputable roundups, and we only consider offers reported in the last 48 hours. Then each deal has to pass four checks."),
        ], kicker="Method", dek="Fewer, better deals, checked by a person every morning.", steps=[
            ("An established retailer", "Amazon, Walmart, Target, Best Buy, or a brand's own store. No marketplace sellers we can't vouch for."),
            ("A real, recent sale", "A source from the last 48 hours confirms the discount, and any price-history claim we repeat names its source."),
            ("A product worth owning", "Well known or well reviewed. We say who it suits, who should skip it, and what to check before you buy."),
            ("Not a repeat", "If we already list it, it doesn't go up twice. When a deal ends, it comes down, and its page says so."),
        ]), crumbs=[("Home", ""), ("How we pick", None)]))
    pages.append(Page("404.html", "notfound", "Page Not Found | ViewDeals",
        "That page is gone, and the deal may have ended. Head back to today's edition of ViewDeals for the hand-picked deals that are live right now.",
        render_404, noindex=True, sitemap=None, root_links=True))
    return pages


def render_styleguide(site, page):
    """Style tile: every token and component, in day and night editions. noindex."""
    live = site.live_deals()
    by_id = {d["id"]: d for d in live}
    featured = [d for d in live if d.get("featured")]
    lead = featured[0] if featured else live[0]
    features = (featured[1:3] + [d for d in live if not d.get("featured")])[:2]
    rest = [d for d in live if d not in [lead] + features]
    soon = sorted(live, key=lambda d: d["expires"])[:5]
    plain = next((d for d in rest if not d.get("featured")), rest[0])
    marks = ["circle", "underline", "arrow", "starburst", "bracket", "checkmark", "editors-pick", "last-chance"]

    def swatch(name, var, note):
        return (f'<li class="sg-swatch"><span class="sg-chip" style="background:var({var})"></span>'
                f'<span><b>{name}</b><br><span class="sg-note">{note}</span></span></li>')

    swatches = "".join([
        swatch("Paper", "--paper", "#F4EFE6 · night #141210"),
        swatch("Ink", "--ink", "#161412 · night #EEE7DA"),
        swatch("Tag red", "--spot1", "#D7261E · night #FF5A4E"),
        swatch("Highlighter", "--spot2", "#FFD23F · night #E8C23A 85%"),
        swatch("Featured wash", "--tint", "highlighter on paper"),
        swatch("Rule", "--rule", "ink at 15% · night 18%"),
    ])

    def components(theme):
        tags = "".join(f'<span class="tag" style="--tilt:{a}deg"><span>{t(x)}</span></span>'
                       for x, a in (("Gift idea", -1.6), ("Doorbuster", 1.2), ("Ends Nov 30", -0.4), ("Editor's pick", 2)))
        return f"""<div class="sg-panel" data-theme="{theme}">
<p class="label sg-panel__name">{'Day edition' if theme == 'light' else 'Night edition'}</p>
<ul class="sg-swatches">{swatches}</ul>
<div class="sg-row">{tags}<span class="stamp">New today</span></div>
<p class="dek">Fine, it’s another air fryer. It’s also <span class="hl">the one reviewers keep recommending</span>.</p>
<div class="sg-row"><a class="button" href="#sg-cards">See deal at Amazon →</a><a class="button button--quiet" href="#sg-cards">Read our take</a></div>
<div class="sg-grid2">{deal_card(site, page, plain)}{deal_card(site, page, by_id.get(soon[0]["id"], soon[0]), "compact")}{deal_card(site, page, soon[1], "compact")}</div>
</div>"""

    type_rows = [
        ('Masthead · 64–96px · Newsreader 700, optical size 72', f'<span class="masthead__name">ViewDeals</span>'),
        ('Lead headline · 40–56px · Newsreader 600', '<span class="card--lead"><span class="card__title" style="display:block">AirPods Pro 3 are the earbuds to beat this week</span></span>'),
        ('Section head · 28px', '<span class="section-head" style="border:0;padding:0;margin:0">Ending soon</span>'),
        ('Card title · 24px', '<span class="card__title" style="display:block;font-family:var(--font-display);font-weight:600">Roborock Q7 M5+ Robot Vacuum and Mop</span>'),
        ('Dek · 21px Newsreader', '<span class="dek" style="display:block">The straight, roomy Levi’s that has outlasted most fashion trends.</span>'),
        ('Body · 17px / 1.55 · Hanken Grotesk', '<span style="display:block;max-width:68ch">The upgrades over the AirPods Pro 2 are real rather than cosmetic. Apple says the noise cancellation removes up to twice as much noise, and the buds now read your heart rate during workouts.</span>'),
        ('Label · 13px serif capitals, tabular figures', '<span class="label">No. 214 · Wednesday, November 25, 2026 · 17 deals today</span>'),
    ]
    type_html = "".join(f'<div class="sg-type"><p class="label sg-type__spec">{t(spec)}</p>{sample}</div>' for spec, sample in type_rows)
    mark_html = "".join(f'<figure class="sg-mark">{mark(site, m)}<figcaption class="label">{m.replace("-", " ")}</figcaption></figure>' for m in marks)

    stream = rest[:6]
    hits = rest[6:12]
    stream_html = "".join(f'<div class="span-4">{deal_card(site, page, d)}</div>' for d in stream)
    hits_html = ""
    if hits:
        hits_html = (f'<section class="quick-hits" aria-labelledby="qh-h"><h2 id="qh-h">Quick hits</h2>'
                     f'<div class="quick-hits__list">{"".join(deal_card(site, page, d, "compact") for d in hits)}</div></section>')

    return f"""<style>
.sg-intro{{max-width:68ch}}
.sg-section{{margin-block:var(--s8)}}
.sg-type{{padding-block:var(--s4);border-top:1px solid var(--rule)}}
.sg-type__spec{{color:var(--muted);margin-bottom:var(--s2)}}
.sg-panels{{display:grid;gap:var(--s5)}}
@media (min-width:1000px){{.sg-panels{{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}}}
.sg-panel{{padding:var(--s5);border:1px solid var(--rule);border-radius:var(--radius)}}
.sg-panel__name{{margin-bottom:var(--s4)}}
.sg-swatches{{list-style:none;padding:0;margin:0 0 var(--s5);display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:var(--s4)}}
.sg-swatch{{display:flex;gap:var(--s3);align-items:center;font-size:15px}}
.sg-note{{color:var(--muted);font-size:14px;font-variant-numeric:tabular-nums}}
.sg-chip{{width:44px;height:44px;flex:none;border:1px solid var(--rule);border-radius:var(--radius)}}
.sg-row{{display:flex;flex-wrap:wrap;gap:var(--s4);align-items:center;margin-bottom:var(--s5)}}
.sg-grid2{{display:grid;gap:var(--s4)}}
.sg-marks{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:var(--s5)}}
.sg-mark{{margin:0;display:grid;gap:var(--s2);align-content:end;min-height:120px}}
.sg-mark .mark{{max-height:96px;width:auto}}
</style>
<div class="page-head"><p class="label">Internal · not indexed</p><h1>Style guide: the Daily Circular</h1>
<p class="dek sg-intro">Two spot colors on newsprint, an editorial serif and a crisp grotesque. Every component the site uses, in the day and night editions. Art marked “placeholder” is stand-in work until the commissioned set arrives.</p></div>

<section class="sg-section" aria-labelledby="sg-type"><h2 class="section-head" id="sg-type">Type scale</h2>{type_html}</section>

<section class="sg-section" aria-labelledby="sg-ed"><h2 class="section-head" id="sg-ed">Color, tags, stamps and highlighter</h2>
<div class="sg-panels">{components("light")}{components("dark")}</div></section>

<section class="sg-section" aria-labelledby="sg-cards"><h2 class="section-head" id="sg-cards">Front page: lead, ending soon, features, standard and quick hits <span class="label">12-column grid</span></h2>
<div class="grid front"><div class="span-8">{deal_card(site, page, lead, "lead", lead=True, annotate="pick")}</div>
<aside class="front__soon" aria-labelledby="soon-h"><h2 id="soon-h">Ending soon</h2>{"".join(deal_card(site, page, d, "compact") for d in soon)}</aside></div>
<div class="grid section">{"".join(f'<div class="span-6">{deal_card(site, page, d, "feature")}</div>' for d in features)}</div>
<div class="grid section">{stream_html}<div style="grid-column:1/-1">{hits_html}</div></div>
</section>

<section class="sg-section" aria-labelledby="sg-marks"><h2 class="section-head" id="sg-marks">Annotation marks <span class="label">draw on scroll</span></h2>
<div class="sg-marks">{mark_html}</div></section>

<section class="sg-section" aria-labelledby="sg-motion"><h2 class="section-head" id="sg-motion">Motion</h2>
<p>Three touches only, all switched off for readers who ask for reduced motion: tags swing about three degrees on hover, the “New today” stamp presses in once when it first scrolls into view, and annotation marks draw themselves in. No parallax, carousels or autoplay.</p></section>
"""


# --------------------------------------------------------------------------
# Page plan
# --------------------------------------------------------------------------

def event_title(ev):
    name, year = ev.get("title_name", ev["name"]), ev["start"][:4]
    for tail in (": Hand-Checked Daily", ": Checked Daily", ""):
        title = f"Best {name} Deals {year}{tail} | ViewDeals"
        if len(title) <= TITLE_MAX:
            return title
    return title


def deal_title(deal):
    if deal.get("seo_title"):
        return deal["seo_title"]
    name = deal.get("short_name") or deal["title"]
    hook = f": {deal['hook']}" if deal.get("hook") else ""
    return f"{name} Deal{hook} | ViewDeals"


def plan_pages(site):
    c = site.config
    pages = [Page("", "home", f"{c['site_name']}: Hand-Picked Deals, Refreshed Every Day", c["description"],
                  render_home, image=site.share("home") or "assets/art/share-home.svg")]
    live = site.live_deals()
    for slug, name in c["categories"].items():
        count = sum(1 for d in live if d["category"] == slug)
        pages.append(Page(f"c/{slug}/", "department", f"Best {name} Deals Today | ViewDeals",
                          fit_description([f"The best {name.lower()} deals live today, picked and checked by hand.",
                                           f"Deals from Amazon, Walmart, Target and Best Buy, refreshed every morning."]),
                          render_category(slug), noindex=(count == 0),
                          crumbs=[("Home", ""), (name, None)], entity=slug,
                          image=site.share(f"cat-{slug}") or f"assets/art/cat-{slug}.svg"))
    for ev in site.events.get("events", []):
        pages.append(Page(f"events/{ev['slug']}/", "event", event_title(ev),
                          ev.get("meta_description") or fit_description([ev["intro"]]),
                          render_event(ev["slug"]), crumbs=[("Home", ""), (f"{ev['name']} deals", None)],
                          entity=ev, image=site.share(f"event-{ev['slug']}") or ev.get("image")))
    for deal in site.page_deals():
        state = site.deal_state(deal)
        path = f"deals/{deal['id']}/"
        dept = f"c/{deal['category']}/"
        crumbs = [("Home", ""), (site.category_name(deal["category"]), dept), (deal["title"], None)]
        if state == "gone":
            pages.append(Page(path, "redirect", deal_title(deal), fit_description([deal["blurb"]]),
                              render_redirect(deal), noindex=True, sitemap=None, redirect=dept))
            continue
        pages.append(Page(path, "deal", deal_title(deal),
                          deal.get("meta_description") or fit_description(
                              [f"{deal['title']} at {site.retailer_name(deal)}.", deal["blurb"], deal.get("who_for")]),
                          render_deal(deal), noindex=(state == "stale"),
                          sitemap=None if state == "stale" else "deals", crumbs=crumbs,
                          published=parse_date(deal["added"]), entity=deal,
                          image=site.share("deal") or site.deal_share_image(deal)))
    for g in site.guides:
        title = g["title"] if g["title"].endswith("| ViewDeals") else f"{g['title']} | ViewDeals"
        pages.append(Page(f"guides/{g['slug']}/", "guide", title,
                          g.get("meta_description") or fit_description([g["dek"]]),
                          render_guide(g), sitemap="guides", crumbs=[("Home", ""), (g["title"], None)],
                          published=parse_date(g["published"]), entity=g,
                          image=site.share(f"guide-{g['slug']}") or g["image"]))
    for slug, a in c.get("authors", {}).items():
        pages.append(Page(f"authors/{slug}/", "author", f"{a['name']}, Deals Editor | ViewDeals",
                          fit_description([a["bio"]]), render_author(slug), entity=slug,
                          crumbs=[("Home", ""), (a["name"], None)], image=site.share("home")))
    for sp in static_pages(site):
        sp.image = sp.image or site.share("home")
        pages.append(sp)
    if site.live_deals():
        pages.append(Page("styleguide/", "styleguide", "Style Guide: The Daily Circular | ViewDeals",
                          "Internal style tile for ViewDeals: type scale, palette, deal card variants, tags, stamps, highlighter and annotation marks in both editions.",
                          render_styleguide, noindex=True, sitemap=None, crumbs=[("Home", ""), ("Style guide", None)]))
    return pages


def validate_pages(site, pages):
    errors = []
    titles, descs = {}, {}
    for p in pages:
        if p.kind == "redirect":
            continue
        where = "/" + p.path
        if len(p.title) > TITLE_MAX:
            errors.append(f"page {where}: title is {len(p.title)} characters (max {TITLE_MAX}): {p.title}")
        if not DESC_MIN <= len(p.description) <= DESC_MAX:
            errors.append(f"page {where}: description is {len(p.description)} characters (needs {DESC_MIN}-{DESC_MAX})")
        if p.title in titles:
            errors.append(f"page {where}: duplicate title (also on /{titles[p.title]})")
        if p.description in descs:
            errors.append(f"page {where}: duplicate description (also on /{descs[p.description]})")
        titles.setdefault(p.title, p.path)
        descs.setdefault(p.description, p.path)
    for g in site.guides:
        by_id = {d["id"]: d for d in site.all_known_deals()}
        with_pages = [i for i in g.get("deal_ids", []) if i in by_id and site.has_page(by_id[i])]
        if len(with_pages) < 5:
            errors.append(f"guide {g['slug']}: links to {len(with_pages)} deal pages (needs at least 5)")
    return errors


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def minify(markup):
    keep = re.compile(r"(<(pre|script|textarea|style)\b.*?</\2>)", re.S | re.I)
    pieces, last = [], 0
    for m in keep.finditer(markup):
        pieces.append((False, markup[last:m.start()]))
        pieces.append((True, m.group(1)))
        last = m.end()
    pieces.append((False, markup[last:]))
    out = []
    for raw, chunk in pieces:
        if not raw:
            chunk = re.sub(r"<!--(?!\[if).*?-->", "", chunk, flags=re.S)
            chunk = re.sub(r">\s*\n\s*<", "><", chunk)
            chunk = re.sub(r"\s*\n\s*", " ", chunk)
            chunk = re.sub(r"[ \t]{2,}", " ", chunk)
        out.append(chunk)
    return "".join(out).strip() + "\n"


def render_page(site, page):
    main = page.render(site, page)
    content_hash = hashlib.sha256(VOLATILE_RE.sub("", main).encode("utf-8")).hexdigest()[:16]
    today = site.today.isoformat()
    prior = site.state.get(page.path)
    if prior and prior.get("hash") == content_hash:
        updated = prior["updated"]
    else:
        updated = today
    first = (prior or {}).get("first_seen") or today
    site.state[page.path] = {"hash": content_hash, "updated": updated, "first_seen": first}
    page.updated = parse_date(updated)
    main = main.replace(UPDATED_TOKEN, time_el(page.updated))
    return minify(layout(site, page, main))


def write_sitemaps(site, pages, docs):
    groups = {"pages": [], "deals": [], "guides": []}
    for p in pages:
        if p.sitemap and not p.noindex:
            groups[p.sitemap].append(p)
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'
    newest = {}
    for name, items in groups.items():
        rows = []
        for p in items:
            img = f"<image:image><image:loc>{e(site.abs_url(p.image))}</image:loc></image:image>" if p.image else ""
            rows.append(f"<url><loc>{e(site.abs_url(p.path))}</loc><lastmod>{p.updated.isoformat()}</lastmod>{img}</url>")
        newest[name] = max((p.updated for p in items), default=site.today)
        write_text(docs / f"sitemap-{name}.xml",
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset {ns}>\n' + "\n".join(rows) + "\n</urlset>\n")
    index = "\n".join(f"<sitemap><loc>{e(site.abs_url(f'sitemap-{n}.xml'))}</loc><lastmod>{newest[n].isoformat()}</lastmod></sitemap>"
                      for n in groups)
    write_text(docs / "sitemap.xml",
        '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + index + "\n</sitemapindex>\n")


def rfc822(d):
    return dt.datetime(d.year, d.month, d.day, 6, 0, tzinfo=dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_feeds(site, docs):
    c = site.config
    live = sorted(site.live_deals(), key=lambda d: d["added"], reverse=True)
    items = []
    for d in live:
        page = site.deal_link_target(d)
        guid = site.abs_url(page) if page else f"viewdeals-{d['id']}"
        perma = "true" if page else "false"
        items.append(f"<item><title>{e(smart(d['title']))}</title><link>{e(affiliate_url(c, d))}</link>"
                     f'<guid isPermaLink="{perma}">{e(guid)}</guid><pubDate>{rfc822(parse_date(d["added"]))}</pubDate>'
                     f"<category>{e(site.category_name(d['category']))}</category>"
                     f"<description>{e(smart(d['blurb']))}</description></item>")
    rss = (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f"<title>{e(c['site_name'])}</title><link>{e(c['base_url'])}/</link><description>{e(c['tagline'])}</description>"
           f'<language>en-us</language><atom:link href="{e(site.abs_url("feed.xml"))}" rel="self" type="application/rss+xml"/>'
           f"<lastBuildDate>{rfc822(site.today)}</lastBuildDate>\n" + "\n".join(items) + "\n</channel></rss>\n")
    write_text(docs / "feed.xml", rss)
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": c["site_name"], "home_page_url": c["base_url"] + "/", "feed_url": site.abs_url("feed.json"),
        "description": c["tagline"], "language": "en-US",
        "items": [{
            "id": site.abs_url(site.deal_link_target(d)) if site.deal_link_target(d) else f"viewdeals-{d['id']}",
            "url": site.abs_url(site.deal_link_target(d)) if site.deal_link_target(d) else affiliate_url(c, d),
            "external_url": affiliate_url(c, d), "title": smart(d["title"]), "content_text": smart(d["blurb"]),
            "date_published": f"{d['added']}T06:00:00Z", "tags": [site.category_name(d["category"])],
        } for d in live],
    }
    write_text(docs / "feed.json", json.dumps(feed, indent=1, ensure_ascii=False) + "\n")


def check_links(docs):
    """Return broken internal links found in docs/*.html."""
    errors = []
    attr = re.compile(r'(?:href|src)="([^"]+)"')
    for f in docs.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        refresh = re.findall(r'http-equiv="refresh" content="0; url=([^"]+)"', text)
        for ref in attr.findall(text) + refresh:
            ref = html.unescape(ref)
            if re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith(("#", "//")):
                continue
            path = ref.split("#")[0].split("?")[0]
            if not path:
                continue
            target = (docs / path.lstrip("/")) if path.startswith("/") else (f.parent / path)
            target = target.resolve()
            if target.is_dir() or path.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                errors.append(f"broken link in {f.relative_to(docs).as_posix()}: {ref}")
    return errors


def check_heads(docs):
    """SEO checks on the written pages: JSON-LD parses, inline CSS fits the first
    round trip, inline CSS urls resolve, and every indexable page has a share image."""
    import gzip
    errors = []
    for f in docs.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        where = f.relative_to(docs).as_posix()
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
            try:
                json.loads(block)
            except ValueError as exc:
                errors.append(f"{where}: JSON-LD does not parse ({exc})")
        style = re.search(r"<style>(.*?)</style>", text, re.S)
        if style:
            gz = len(gzip.compress(style.group(1).encode("utf-8")))
            if gz > CRITICAL_MAX:
                errors.append(f"{where}: inline CSS is {gz} bytes compressed (max {CRITICAL_MAX})")
            for ref in re.findall(r"url\(([^)\"']*assets/[^)\"']+)\)", style.group(1)):
                target = (docs / ref.lstrip("/")) if ref.startswith("/") else (f.parent / ref)
                if not target.resolve().exists():
                    errors.append(f"{where}: inline CSS url not found: {ref}")
        if 'name="robots" content="noindex"' not in text and 'http-equiv="refresh"' not in text \
                and 'property="og:image"' not in text:
            errors.append(f"{where}: no og:image share card")
    return errors


def build(site):
    docs = site.root / "docs"
    pages = plan_pages(site)
    errors = validate_pages(site, pages)
    if errors:
        return errors
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir()
    shutil.copytree(site.root / "assets", docs / "assets", ignore=shutil.ignore_patterns(".gitkeep"))
    write_text(docs / "assets" / "style.css", css_minify((site.root / "assets" / "style.css").read_text(encoding="utf-8")) + "\n")
    for page in pages:
        out = docs / page.out_file
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text(out, render_page(site, page))
    write_sitemaps(site, pages, docs)
    write_feeds(site, docs)
    write_text(docs / "robots.txt",
        f"User-agent: *\nDisallow: /styleguide/\n\nSitemap: {site.abs_url('sitemap.xml')}\n")
    write_text(docs / "CNAME", site.config["domain"] + "\n")
    write_text(docs / ".nojekyll", "")
    key = site.config.get("indexnow_key")
    if key:
        write_text(docs / f"{key}.txt", key)
    live_paths = {p.path for p in pages}
    site.state = {k: val for k, val in site.state.items() if k in live_paths}
    write_json(site.root / "data" / "page-state.json", dict(sorted(site.state.items())))
    errors = check_links(docs) + check_heads(docs)
    if errors:
        return errors
    print(f"Built {len(pages)} pages into docs/ for {site.today.isoformat()} "
          f"({len(site.live_deals())} live deals, {sum(1 for p in pages if p.kind == 'deal')} deal pages).")
    return []


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate and build ViewDeals.")
    ap.add_argument("--check", action="store_true", help="validate only; write nothing")
    ap.add_argument("--prune", action="store_true", help="archive expired deals, then build")
    ap.add_argument("--today", help="treat this YYYY-MM-DD date as today")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    today = parse_date(args.today) if args.today else eastern_today()
    if args.today and not today:
        print(f"ERROR: --today {args.today} is not a YYYY-MM-DD date")
        return 1
    root = Path(args.root)

    site = Site(root, today)
    errors = validate(site.config, site.deals, site.events, site.archive, site.guides, root, site.photos)
    if not errors:
        errors = validate_pages(site, plan_pages(site))
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    if not site.config["retailers"].get("amazon", {}).get("query_params", {}).get("tag"):
        print("WARNING: Amazon tracking tag is empty; Amazon links will not earn commission.")

    if args.check:
        print(f"OK: {len(site.deals)} deals are valid.")
        return 0

    if args.prune:
        prune(root, today)
        site = Site(root, today)

    errors = build(site)
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
