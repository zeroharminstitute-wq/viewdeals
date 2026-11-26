"""Unit tests for scripts/build.py (standard library only).

Run from the repo root:
    python3 -m unittest discover tests

Build tests work on a throwaway copy of the repo in a temp folder, so the real
data/ and docs/ are never touched. The copy uses the fixed deals and guides in
tests/fixtures, not today's; only test_seed_data_passes reads the real data.
"""
import contextlib
import copy
import datetime as dt
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402

D = dt.date.fromisoformat
SKIP_DIRS = {".git", "docs", "photos-src", "screenshots", "lighthouse-reports",
             "node_modules", "__pycache__", ".lighthouseci"}


def repo_copy():
    """Copy the repo (sources only) into a new temp folder and return its path."""
    tmp = Path(tempfile.mkdtemp(prefix="viewdeals-test-"))
    dest = tmp / "repo"
    shutil.copytree(ROOT, dest, ignore=lambda d, names: [n for n in names if n in SKIP_DIRS])
    # The copy gets a fixed set of deals and guides (tests/fixtures, a snapshot from 2026-11-26),
    # so the tests give the same answer whatever is live on the real site today.
    fixtures = ROOT / "tests" / "fixtures"
    shutil.copy(fixtures / "deals.json", dest / "data" / "deals.json")
    shutil.copy(fixtures / "archive.json", dest / "data" / "archive.json")
    shutil.rmtree(dest / "data" / "guides", ignore_errors=True)
    shutil.copytree(fixtures / "guides", dest / "data" / "guides")
    for name in ("price-log.json", "page-state.json"):
        (dest / "data" / name).unlink(missing_ok=True)
    return dest


def run(*argv):
    """Run build.main quietly; return (exit code, printed output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = build.main([str(a) for a in argv])
    return code, out.getvalue()


def edit_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def html_files(docs):
    return {p: p.read_text(encoding="utf-8") for p in docs.rglob("*.html")}


# --------------------------------------------------------------------------
# affiliate_url
# --------------------------------------------------------------------------

class AffiliateUrlTests(unittest.TestCase):
    def config(self, **retailer):
        return {"retailers": {"amazon": dict(name="Amazon", **retailer)}}

    def deal(self, url):
        return {"retailer": "amazon", "url": url}

    def test_amazon_tag_is_added(self):
        cfg = self.config(query_params={"tag": "viewdeals-20"})
        self.assertEqual(build.affiliate_url(cfg, self.deal("https://www.amazon.com/s?k=Echo+Dot")),
                         "https://www.amazon.com/s?k=Echo+Dot&tag=viewdeals-20")

    def test_tag_on_url_without_query(self):
        cfg = self.config(query_params={"tag": "viewdeals-20"})
        self.assertEqual(build.affiliate_url(cfg, self.deal("https://www.amazon.com/dp/B0FQFB8FMG")),
                         "https://www.amazon.com/dp/B0FQFB8FMG?tag=viewdeals-20")

    def test_existing_parameter_is_replaced(self):
        cfg = self.config(query_params={"tag": "viewdeals-20"})
        out = build.affiliate_url(cfg, self.deal("https://www.amazon.com/s?tag=someone-else-20&k=Echo+Dot"))
        self.assertEqual(out, "https://www.amazon.com/s?k=Echo+Dot&tag=viewdeals-20")
        self.assertEqual(out.count("tag="), 1)

    def test_empty_tag_leaves_url_unchanged(self):
        cfg = self.config(query_params={"tag": ""})
        url = "https://www.amazon.com/s?k=Echo+Dot"
        self.assertEqual(build.affiliate_url(cfg, self.deal(url)), url)

    def test_no_settings_leaves_url_unchanged(self):
        url = "https://www.walmart.com/ip/123"
        cfg = {"retailers": {"walmart": {"name": "Walmart", "link_template": ""}}}
        self.assertEqual(build.affiliate_url(cfg, {"retailer": "walmart", "url": url}), url)

    def test_link_template_url_encodes_deal_url(self):
        cfg = {"retailers": {"walmart": {"name": "Walmart",
                                         "link_template": "https://goto.walmart.com/c/1/2/3?u={url}"}}}
        out = build.affiliate_url(cfg, {"retailer": "walmart", "url": "https://www.walmart.com/ip/123?a=1&b=2"})
        self.assertEqual(out, "https://goto.walmart.com/c/1/2/3?u=https%3A%2F%2Fwww.walmart.com%2Fip%2F123%3Fa%3D1%26b%3D2")

    def test_link_template_wins_over_query_params(self):
        cfg = {"retailers": {"x": {"name": "X", "link_template": "https://net.example/?u={url}",
                                   "query_params": {"tag": "t"}}}}
        out = build.affiliate_url(cfg, {"retailer": "x", "url": "https://shop.example/p"})
        self.assertEqual(out, "https://net.example/?u=https%3A%2F%2Fshop.example%2Fp")


class DateTests(unittest.TestCase):
    def test_eastern_midnight_has_the_right_offset(self):
        self.assertEqual(build.eastern_midnight("2026-11-25"), "2026-11-25T00:00:00-05:00")
        self.assertEqual(build.eastern_midnight(D("2026-07-14")), "2026-07-14T00:00:00-04:00")
        self.assertEqual(build.eastern_midnight("2026-03-08"), "2026-03-08T00:00:00-04:00")   # DST starts
        self.assertEqual(build.eastern_midnight("2026-11-01"), "2026-11-01T00:00:00-05:00")   # DST ends


# --------------------------------------------------------------------------
# Validation: one failing deal per rule gives exactly that error
# --------------------------------------------------------------------------

class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))

    def base(self, **changes):
        deal = {"id": "test-kettle", "title": "Test Kettle", "retailer": "amazon",
                "url": "https://www.amazon.com/s?k=electric+kettle", "category": "home",
                "blurb": "A plain electric kettle that boils fast.", "label": "Gift idea",
                "added": "2026-11-25", "expires": "2026-11-30"}
        deal.update(changes)
        return {k: v for k, v in deal.items() if v is not None}

    def errors(self, *deals):
        return build.validate(self.config, list(deals))

    def assertOneError(self, deal, fragment):
        errs = self.errors(deal)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn(fragment, errs[0])
        self.assertTrue(errs[0].startswith(deal.get("id") or "#1"), errs[0])

    def test_base_deal_is_valid(self):
        self.assertEqual(self.errors(self.base()), [])

    def test_rule1_required_field(self):
        for field in build.REQUIRED:
            with self.subTest(field=field):
                deal = self.base(**{field: None})
                self.assertOneError(deal, f"missing required field '{field}'")
        self.assertOneError(self.base(blurb="   "), "missing required field 'blurb'")

    def test_rule2_id_format(self):
        self.assertOneError(self.base(id="Test_Kettle"), "id must be lowercase")
        self.assertOneError(self.base(id="-kettle"), "id must be lowercase")

    def test_rule2_id_unique(self):
        errs = self.errors(self.base(), self.base())
        self.assertEqual(errs, ["test-kettle: duplicate id"])

    def test_rule3_retailer_and_category(self):
        self.assertOneError(self.base(retailer="costco"), "unknown retailer 'costco'")
        self.assertOneError(self.base(category="garden"), "unknown category 'garden'")

    def test_rule4_https_with_host(self):
        self.assertOneError(self.base(url="http://www.amazon.com/s?k=kettle"), "url must be https://")
        self.assertOneError(self.base(retailer="walmart", url="https:///ip/1"), "url must be https://")

    def test_rule5_amazon_host(self):
        self.assertOneError(self.base(url="https://www.example.com/kettle"), "amazon. or amzn. host")
        self.assertEqual(self.errors(self.base(url="https://amzn.to/abc")), [])

    def test_rule5_no_tag_in_url(self):
        self.assertOneError(self.base(url="https://www.amazon.com/s?k=kettle&tag=me-20"), "must not contain tag=")

    def test_rule6_no_price_or_discount(self):
        cases = [("title", "Test Kettle under $20"), ("title", "Test Kettle £ 15 off"),
                 ("blurb", "Now 30% off for the holidays."), ("blurb", "Save 30 % today."),
                 ("label", "50 percent off"), ("label", "Half off €5")]
        for field, value in cases:
            with self.subTest(value=value):
                self.assertOneError(self.base(**{field: value}), f"Amazon {field} must not show a price")

    def test_rule6_only_for_amazon(self):
        self.assertEqual(self.errors(self.base(retailer="target", url="https://www.target.com/p/1",
                                               title="Kettle for $20")), [])

    def test_rule7_dates(self):
        self.assertOneError(self.base(added="2026-13-01"), "added is not a YYYY-MM-DD date")
        self.assertOneError(self.base(expires="Nov 30"), "expires is not a YYYY-MM-DD date")
        self.assertOneError(self.base(expires="2026-11-24"), "expires is before added")
        self.assertEqual(self.errors(self.base(expires="2026-11-25")), [])

    def test_rule8_blurb_length(self):
        self.assertEqual(self.errors(self.base(blurb="a" * build.BLURB_MAX)), [])
        self.assertOneError(self.base(blurb="a" * (build.BLURB_MAX + 1)), "blurb is over 320 characters")

    def test_short_write_up_is_rejected(self):
        self.assertOneError(self.base(write_up=["Too short to earn a page."]), "needs 150+ for a page")

    def test_related_must_exist(self):
        self.assertOneError(self.base(related=["no-such-deal"]), "related id 'no-such-deal' does not exist")

    def test_amazon_deal_cannot_carry_a_price(self):
        self.assertOneError(self.base(price=19.99, price_checked="2026-11-25"), "must not carry a price")

    def test_price_needs_a_number_and_the_day_it_was_checked(self):
        other = dict(retailer="walmart", url="https://www.walmart.com/ip/1")
        self.assertEqual(self.errors(self.base(price=19.99, price_checked="2026-11-25", **other)), [])
        self.assertOneError(self.base(price=19.99, **other), "price_checked")
        self.assertOneError(self.base(price="19.99", price_checked="2026-11-25", **other), "price must be a number")
        self.assertOneError(self.base(product="Bad Key", **other), "product must be")

    def test_seed_data_passes(self):
        today = D("2026-11-25")
        site = build.Site(ROOT, today)
        errs = build.validate(site.config, site.deals, site.events, site.archive, site.guides, ROOT, site.photos)
        self.assertEqual(errs, [])
        self.assertEqual(build.validate_pages(site, build.plan_pages(site)), [])

    def test_check_command_prints_ok(self):
        code, out = run("--check", "--today", "2026-11-25")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"OK: \d+ deals are valid\.")


# --------------------------------------------------------------------------
# Prune
# --------------------------------------------------------------------------

class PruneTests(unittest.TestCase):
    def setUp(self):
        self.root = repo_copy()
        self.addCleanup(shutil.rmtree, self.root.parent, ignore_errors=True)
        self.deals_path = self.root / "data" / "deals.json"
        self.archive_path = self.root / "data" / "archive.json"
        self.archive_path.unlink(missing_ok=True)
        self.before = json.loads(self.deals_path.read_text(encoding="utf-8"))["deals"]

    def load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))["deals"]

    def test_expired_move_to_archive_and_live_stay(self):
        today = D("2026-11-30")
        with contextlib.redirect_stdout(io.StringIO()):
            moved = build.prune(self.root, today)
        expired = {d["id"] for d in self.before if D(d["expires"]) < today}
        live = {d["id"] for d in self.before if D(d["expires"]) >= today}
        self.assertTrue(expired and live, "seed data should have both kinds at this date")
        self.assertEqual({d["id"] for d in moved}, expired)
        self.assertEqual({d["id"] for d in self.load(self.deals_path)}, live)
        self.assertEqual({d["id"] for d in self.load(self.archive_path)}, expired)

    def test_second_run_adds_no_duplicates(self):
        today = D("2026-11-30")
        with contextlib.redirect_stdout(io.StringIO()):
            build.prune(self.root, today)
            first = self.load(self.archive_path)
            build.prune(self.root, today)
            # An expired deal put back into deals.json by mistake must not be archived twice.
            edit_json(self.deals_path, lambda data: data["deals"].append(copy.deepcopy(first[0])))
            build.prune(self.root, today)
        archive = self.load(self.archive_path)
        ids = [d["id"] for d in archive]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(archive), len(first))
        self.assertNotIn(first[0]["id"], {d["id"] for d in self.load(self.deals_path)})

    def test_deal_expiring_today_is_not_pruned(self):
        today = D("2026-11-28")
        with contextlib.redirect_stdout(io.StringIO()):
            build.prune(self.root, today)
        self.assertIn("sony-wh-1000xm5", {d["id"] for d in self.load(self.deals_path)})


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

class BuildTests(unittest.TestCase):
    """One build of a temp copy on 2026-11-30.

    The build adds two deals of its own: Kasa plugs on their last day (expires
    11-30) and a speaker that ended the day before. Neither has a write-up, so each
    is only a card. The Kasa title has HTML special characters to test escaping.
    """
    TODAY = "2026-11-30"
    ODD_TITLE = 'Kasa <Smart> Plug & "Mini" 4-Pack'

    @classmethod
    def setUpClass(cls):
        cls.root = repo_copy()
        deals = cls.root / "data" / "deals.json"
        data = json.loads(deals.read_text(encoding="utf-8"))
        # The two deals under test are added here, so the tests don't depend on which real deals are live.
        cls.today_deal = {"id": "unit-test-kasa-plugs", "title": cls.ODD_TITLE, "retailer": "amazon",
                          "url": "https://www.amazon.com/s?k=unit+test+kasa+plugs", "category": "smart-home",
                          "blurb": "Four small smart plugs for lamps and fans.", "added": "2026-11-25", "expires": cls.TODAY}
        cls.gone_deal = {"id": "unit-test-gone-speaker", "title": "Unit Test Gone Speaker", "retailer": "walmart",
                         "url": "https://www.walmart.com/ip/unit-test-gone-speaker/1", "category": "outdoors",
                         "blurb": "A small speaker whose deal ended yesterday.", "added": "2026-11-25", "expires": "2026-11-29"}

        # These tests check a build with no analytics, so they don't depend on the owner's token.
        # ...and with no email sign-up, so the "off until set up" test doesn't either.
        def owner_settings_off(c):
            c.setdefault("analytics", {}).update(cloudflare_token="")
            c["newsletter"] = {"provider_name": "", "form_action": "", "email_field": "email", "hidden_fields": {}}
        edit_json(cls.root / "site.config.json", owner_settings_off)

        edit_json(deals, lambda d: d["deals"].extend([cls.today_deal, cls.gone_deal]))
        cls.code, cls.out = run("--today", cls.TODAY, "--root", cls.root)
        cls.docs = cls.root / "docs"
        cls.html = html_files(cls.docs) if cls.docs.exists() else {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root.parent, ignore_errors=True)

    def test_build_succeeds(self):
        self.assertEqual(self.code, 0, self.out)
        self.assertIn("Built ", self.out)

    def test_expected_files_exist(self):
        config = json.loads((self.root / "site.config.json").read_text(encoding="utf-8"))
        events = json.loads((self.root / "data" / "events.json").read_text(encoding="utf-8"))["events"]
        deals = json.loads((self.root / "data" / "deals.json").read_text(encoding="utf-8"))["deals"]
        expected = ["index.html", "404.html", "about/index.html", "disclosure/index.html",
                    "privacy/index.html", "how-we-pick/index.html", "styleguide/index.html",
                    "sitemap.xml", "sitemap-pages.xml", "sitemap-deals.xml", "sitemap-guides.xml",
                    "robots.txt", "feed.xml", "feed.json", "CNAME", ".nojekyll",
                    "assets/style.css", "assets/app.js", "assets/favicon.svg"]
        expected += [f"c/{slug}/index.html" for slug in config["categories"]]
        expected += [f"events/{ev['slug']}/index.html" for ev in events]
        expected += [f"authors/{slug}/index.html" for slug in config["authors"]]
        expected += [f"guides/{p.stem}/index.html" for p in (self.root / "data" / "guides").glob("*.json")]
        expected += [f"deals/{d['id']}/index.html" for d in deals
                     if build.word_count(d.get("write_up")) >= build.WRITE_UP_MIN_WORDS]
        missing = [f for f in expected if not (self.docs / f).is_file()]
        self.assertEqual(missing, [])
        self.assertEqual((self.docs / "CNAME").read_text(encoding="utf-8").strip(), config["domain"])

    def test_no_sign_up_form_until_the_owner_sets_one(self):
        self.assertNotIn('class="signup', "".join(self.html.values()))
        self.assertTrue((self.docs / "daily.xml").is_file())

    def test_guides_index_and_evergreen_guide_are_built_and_linked(self):
        index = self.html[self.docs / "guides" / "index.html"]
        self.assertIn("Year-round guides", index)
        page = self.html[self.docs / "guides" / "best-time-to-buy-a-tv" / "index.html"]
        self.assertIn("<h2>Sources</h2>", page)
        self.assertIn("<table>", page)
        self.assertIn('href="./guides/"', self.html[self.docs / "index.html"])

    def test_titles_are_html_escaped(self):
        text = "".join(self.html.values())
        self.assertIn("Kasa &lt;Smart&gt; Plug &amp;", text)
        self.assertNotIn("<Smart>", text)
        feed = (self.docs / "feed.xml").read_text(encoding="utf-8")
        self.assertNotIn("<Smart>", feed)
        json.loads((self.docs / "feed.json").read_text(encoding="utf-8"))   # still valid JSON

    def test_deal_expiring_today_still_shows(self):
        home = self.html[self.docs / "index.html"]
        dept = self.html[self.docs / "c" / "smart-home" / "index.html"]
        self.assertIn("Kasa &lt;Smart&gt; Plug", dept)
        self.assertIn("Kasa &lt;Smart&gt; Plug", home + dept)

    def test_deal_expired_yesterday_is_gone(self):
        title = self.gone_deal["title"]
        for rel in ("index.html", "c/outdoors/index.html", "feed.xml", "feed.json"):
            with self.subTest(file=rel):
                self.assertNotIn(title, (self.docs / rel).read_text(encoding="utf-8"))
        self.assertNotIn(self.gone_deal["url"], "".join(self.html.values()))

    def test_affiliate_links_are_sponsored(self):
        home = self.html[self.docs / "index.html"]
        outbound = re.findall(r'<a [^>]*href="https://www\.(?:amazon|walmart|target|bestbuy)\.com[^>]*>', home)
        self.assertTrue(outbound)
        for a in outbound:
            self.assertIn("sponsored", a)

    def test_required_statements_on_every_page(self):
        for path, text in self.html.items():
            if 'http-equiv="refresh"' in text:
                continue
            with self.subTest(page=str(path.relative_to(self.docs))):
                self.assertIn("As an Amazon Associate, ViewDeals earns from qualifying purchases.", text)

    def test_no_third_party_scripts(self):
        # With no analytics token, pages load nothing from other hosts.
        for path, text in self.html.items():
            srcs = re.findall(r'<script[^>]+src="([^"]+)"', text)
            self.assertEqual([u for u in srcs if u.startswith(("http:", "https:", "//"))], [], str(path))

    def test_json_ld_parses(self):
        for path, text in self.html.items():
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
                json.loads(block)

    def test_robots_and_sitemap(self):
        robots = (self.docs / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /styleguide/", robots)
        self.assertIn("Sitemap: https://viewdeals.com/sitemap.xml", robots)
        index = (self.docs / "sitemap.xml").read_text(encoding="utf-8")
        for name in ("sitemap-pages.xml", "sitemap-deals.xml", "sitemap-guides.xml"):
            self.assertIn(name, index)
        self.assertNotIn("styleguide", (self.docs / "sitemap-pages.xml").read_text(encoding="utf-8"))


class ConfigBuildTests(unittest.TestCase):
    """Owner settings in site.config.json reach every page."""

    @classmethod
    def setUpClass(cls):
        cls.root = repo_copy()

        def settings(c):
            c["retailers"]["amazon"]["query_params"]["tag"] = "unit-test-20"
            c["analytics"] = {"cloudflare_token": "0123456789abcdef"}
            c["verification"] = {"google": "g-test-code", "bing": "b-test-code"}
            c["indexnow_key"] = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
        edit_json(cls.root / "site.config.json", settings)
        cls.code, cls.out = run("--today", "2026-11-25", "--root", cls.root)
        cls.docs = cls.root / "docs"
        cls.html = html_files(cls.docs) if cls.docs.exists() else {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root.parent, ignore_errors=True)

    def test_build_succeeds(self):
        self.assertEqual(self.code, 0, self.out)

    def test_every_amazon_link_is_tagged(self):
        links = []
        for text in self.html.values():
            links += re.findall(r'href="(https://www\.amazon\.com[^"]*)"', text)
        self.assertTrue(links)
        self.assertEqual([u for u in links if "tag=unit-test-20" not in u], [])

    def test_analytics_beacon_once_per_page(self):
        home = self.html[self.docs / "index.html"]
        self.assertEqual(home.count("static.cloudflareinsights.com/beacon.min.js"), 1)
        self.assertIn("0123456789abcdef", home)
        self.assertNotIn("cloudflareinsights", self.html[self.docs / "styleguide" / "index.html"])

    def test_verification_meta_and_indexnow_key(self):
        home = self.html[self.docs / "index.html"]
        self.assertIn('<meta name="google-site-verification" content="g-test-code">', home)
        self.assertIn('<meta name="msvalidate.01" content="b-test-code">', home)
        key = self.docs / "a1b2c3d4e5f60718293a4b5c6d7e8f90.txt"
        self.assertEqual(key.read_text(encoding="utf-8").strip(), "a1b2c3d4e5f60718293a4b5c6d7e8f90")


class PriceAndEmailTests(unittest.TestCase):
    """A checked price joins the price record, and the email sign-up appears once it is set up."""
    TODAY = "2026-11-26"

    @classmethod
    def setUpClass(cls):
        cls.root = repo_copy()
        deals = cls.root / "data" / "deals.json"
        data = json.loads(deals.read_text(encoding="utf-8"))
        # The deal under test is added here, so the tests don't depend on which real deals are live.
        cls.deal = {"id": "unit-test-priced-kettle", "title": "Unit Test Priced Kettle", "retailer": "walmart",
                    "url": "https://www.walmart.com/ip/unit-test-priced-kettle/2", "category": "home",
                    "blurb": "A plain electric kettle used by the tests.", "added": cls.TODAY, "expires": "2026-11-30",
                    "short_name": "Unit Test Kettle", "hook": "Test Only",
                    "write_up": ["kettle " * (build.WRITE_UP_MIN_WORDS + 10)],
                    "price": 100, "price_checked": cls.TODAY, "product": "unit-test-product"}

        def price(d):
            d["updated"] = cls.TODAY
            for x in d["deals"]:
                x.pop("price", None)
                x.pop("price_checked", None)
            d["deals"].append(cls.deal)
        edit_json(deals, price)
        (cls.root / "data" / "price-log.json").write_text(json.dumps({"products": {"unit-test-product": {
            "title": "Unit test product", "points": [{"date": "2026-11-01", "retailer": "target", "price": 120, "deal": "older"}]}}}),
            encoding="utf-8")
        edit_json(cls.root / "site.config.json", lambda c: c.update(newsletter={
            "provider_name": "Test Mail", "form_action": "https://mail.example/subscribe", "email_field": "email_address",
            "hidden_fields": {"list": "abc"}}))
        cls.code, cls.out = run("--today", cls.TODAY, "--root", cls.root)
        cls.docs = cls.root / "docs"
        cls.html = html_files(cls.docs) if cls.docs.exists() else {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root.parent, ignore_errors=True)

    def points(self):
        log = json.loads((self.root / "data" / "price-log.json").read_text(encoding="utf-8"))
        return log["products"]["unit-test-product"]["points"]

    def test_build_succeeds(self):
        self.assertEqual(self.code, 0, self.out)

    def test_price_is_recorded_once(self):
        self.assertEqual([(x["date"], x["price"]) for x in self.points()], [("2026-11-01", 120), (self.TODAY, 100)])
        build.record_prices(self.root, json.loads((self.root / "data" / "deals.json").read_text(encoding="utf-8"))["deals"])
        self.assertEqual(len(self.points()), 2)

    def test_deal_page_shows_price_and_record(self):
        page = self.html[self.docs / "deals" / self.deal["id"] / "index.html"]
        self.assertIn("$100</b> when we checked on", page)
        self.assertIn("Lowest in our 2 price checks since Nov 1, 2026.", page)
        self.assertIn("Our price record", page)
        self.assertIn("$120", page)

    def test_no_price_is_shown_for_amazon(self):
        for text in self.html.values():
            for card in re.findall(r'<article class="card.*?</article>', text, re.S):
                if "amazon.com" in card:
                    self.assertNotIn("card__price", card)

    def test_sign_up_form_and_privacy_wording(self):
        home = self.html[self.docs / "index.html"]
        self.assertIn('action="https://mail.example/subscribe"', home)
        self.assertIn('name="email_address"', home)
        self.assertIn('name="list" value="abc"', home)
        privacy = self.html[self.docs / "privacy" / "index.html"]
        self.assertIn("Test Mail", privacy)
        self.assertNotIn("no newsletter sign-up", privacy)

    def test_daily_feed_links_only_to_our_own_pages(self):
        feed = (self.docs / "daily.xml").read_text(encoding="utf-8")
        self.assertIn(f"viewdeals-edition-{self.TODAY}", feed)
        self.assertIn("https://viewdeals.com/deals/" + self.deal["id"] + "/", feed)
        import html as html_lib
        links = re.findall(r'href="([^"]+)"', html_lib.unescape(feed))
        self.assertTrue(links)
        self.assertEqual([u for u in links if not u.startswith("https://viewdeals.com/")], [])


class EvergreenGuideTests(unittest.TestCase):
    """A year-round guide needs sources and length, not live deals."""

    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))

    def guide(self, **changes):
        g = {"slug": "best-time-to-buy-a-test", "title": "Best Time to Buy a Test", "dek": "A dek.",
             "author": "viewdeals-desk", "published": "2026-11-26", "updated": "2026-11-26",
             "image": "assets/art/cat-tech.svg", "evergreen": True, "category": "tech",
             "sections": [{"heading": "One", "paragraphs": ["word " * build.EVERGREEN_MIN_WORDS]}],
             "sources": [{"name": "A", "url": "https://a.example/x"}, {"name": "B", "url": "https://b.example/y"}]}
        g.update(changes)
        return g

    def errors(self, guide):
        return build.validate(self.config, [], guides=[guide])

    def test_valid_without_deal_ids(self):
        self.assertEqual(self.errors(self.guide()), [])

    def test_needs_two_sources(self):
        errs = self.errors(self.guide(sources=[{"name": "A", "url": "https://a.example/x"}]))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("at least 2 sources", errs[0])

    def test_source_needs_https_url(self):
        errs = self.errors(self.guide(sources=[{"name": "A", "url": "http://a.example"}, {"name": "B", "url": "https://b.example"}]))
        self.assertIn("https url", errs[0])

    def test_needs_length(self):
        errs = self.errors(self.guide(sections=[{"heading": "One", "paragraphs": ["too short"]}]))
        self.assertIn(f"at least {build.EVERGREEN_MIN_WORDS} words", errs[0])

    def test_table_rows_must_match_head(self):
        g = self.guide()
        g["sections"][0]["table"] = {"head": ["a", "b"], "rows": [["1"]]}
        self.assertIn("table needs", self.errors(g)[0])

    def test_ordinary_guide_still_needs_deal_ids(self):
        g = self.guide(evergreen=False)
        self.assertTrue(any("deal_ids" in x for x in self.errors(g)))


class LifecycleTests(unittest.TestCase):
    """An ended deal page: banner after a week, noindex after 61 days, redirect after 366."""
    DEAL, DEPT = "sony-wh-1000xm5", "tech"   # expires 2026-11-28, has a write-up

    def build_at(self, days):
        root = repo_copy()
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        today = D("2026-11-28") + dt.timedelta(days=days)
        code, out = run("--prune", "--today", today.isoformat(), "--root", root)
        self.assertEqual(code, 0, out)
        page = (root / "docs" / "deals" / self.DEAL / "index.html").read_text(encoding="utf-8")
        sitemap = (root / "docs" / "sitemap-deals.xml").read_text(encoding="utf-8")
        return page, sitemap

    def test_week_after_shows_ended_banner(self):
        page, sitemap = self.build_at(7)
        self.assertIn("This deal has ended.", page)
        self.assertNotIn('content="noindex"', page)
        self.assertIn(f"/deals/{self.DEAL}/", sitemap)

    def test_61_days_after_is_noindex_and_out_of_sitemap(self):
        page, sitemap = self.build_at(61)
        self.assertIn('<meta name="robots" content="noindex">', page)
        self.assertNotIn(f"/deals/{self.DEAL}/", sitemap)

    def test_366_days_after_redirects_to_department(self):
        page, sitemap = self.build_at(366)
        self.assertRegex(page, rf'http-equiv="refresh" content="0; url=[^"]*c/{self.DEPT}/"')
        self.assertIn(f'rel="canonical" href="https://viewdeals.com/c/{self.DEPT}/"', page)
        self.assertNotIn(f"/deals/{self.DEAL}/", sitemap)


if __name__ == "__main__":
    unittest.main()
