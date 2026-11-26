"""Unit tests for scripts/send_daily_email.py. No network: the Kit API is a stand-in."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import send_daily_email as mail  # noqa: E402

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>ViewDeals daily</title>
{item}</channel></rss>
"""
ITEM = ("<item><title>Kettle and 2 more new deals</title><link>https://viewdeals.com/</link>"
        '<guid isPermaLink="false">viewdeals-edition-2026-11-27</guid>'
        "<description>&lt;p&gt;3 new deals&lt;/p&gt;</description></item>")
TODAY = dt.date(2026, 11, 27)
NOW = dt.datetime(2026, 11, 27, 11, 20, tzinfo=dt.timezone.utc)


class FakeKit:
    def __init__(self, existing=(), create_status=201):
        self.existing, self.create_status, self.calls = list(existing), create_status, []

    def __call__(self, method, url, key, body=None):
        self.calls.append((method, body))
        if method == "GET":
            return 200, {"broadcasts": [{"description": d} for d in self.existing]}
        if self.create_status != 201:
            return self.create_status, {"errors": ["Not allowed on this plan"]}
        return 201, {"broadcast": {"id": 7}}


class SendDailyEmailTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.feed = Path(self.dir.name) / "daily.xml"
        self.lines = []

    def tearDown(self):
        self.dir.cleanup()

    def go(self, item=ITEM, today=TODAY, key="k", mode="draft", kit=None, **kw):
        self.feed.write_text(FEED.format(item=item), encoding="utf-8")
        self.kit = kit or FakeKit()
        return mail.run(self.feed, today, key, mode, request=self.kit, now=NOW, out=self.lines.append, **kw)

    def posts(self):
        return [body for method, body in self.kit.calls if method == "POST"]

    def test_draft_mode_saves_a_draft(self):
        self.assertEqual(self.go(), 0)
        (body,) = self.posts()
        self.assertIsNone(body["send_at"])
        self.assertEqual(body["subject"], "Kettle and 2 more new deals")
        self.assertEqual(body["description"], "viewdeals-edition-2026-11-27")
        self.assertEqual(body["content"], "<p>3 new deals</p>")
        self.assertFalse(body["public"])

    def test_send_mode_schedules_a_few_minutes_ahead(self):
        self.assertEqual(self.go(mode="send"), 0)
        self.assertEqual(self.posts()[0]["send_at"], "2026-11-27T11:30:00Z")

    def test_an_edition_is_never_sent_twice(self):
        self.assertEqual(self.go(kit=FakeKit(existing=["viewdeals-edition-2026-11-27"])), 0)
        self.assertEqual(self.posts(), [])

    def test_no_email_without_new_deals_or_for_an_old_edition(self):
        self.assertEqual(self.go(item=""), 0)
        self.assertEqual(self.kit.calls, [])
        self.assertEqual(self.go(today=dt.date(2026, 11, 28)), 0)
        self.assertEqual(self.kit.calls, [])

    def test_no_key_means_not_set_up_and_no_calls(self):
        self.assertEqual(self.go(key=""), 0)
        self.assertEqual(self.kit.calls, [])

    def test_dry_run_calls_nothing(self):
        self.assertEqual(self.go(dry_run=True), 0)
        self.assertEqual(self.kit.calls, [])

    def test_a_refusal_from_kit_fails_the_job_and_says_why(self):
        self.assertEqual(self.go(kit=FakeKit(create_status=403)), 1)
        self.assertIn("Not allowed on this plan", self.lines[-1])

    def test_bad_mode_is_an_error(self):
        self.assertEqual(self.go(mode="now"), 1)


if __name__ == "__main__":
    unittest.main()
