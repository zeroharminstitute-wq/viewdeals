#!/usr/bin/env python3
"""Turn today's edition in docs/daily.xml into a Kit email broadcast.

Standard library only. Run by .github/workflows/daily-email.yml after the daily
task pushes; safe to run twice (an edition is only ever made into one broadcast).

    python3 scripts/send_daily_email.py             make the broadcast
    python3 scripts/send_daily_email.py --dry-run   print what would be sent; call nothing

Settings come from the environment:

    KIT_API_KEY     the owner's Kit API key (a GitHub secret). Unset: do nothing.
    KIT_SEND_MODE   "draft" (default) saves a draft for the owner to look at in Kit;
                    "send" schedules it to go out a few minutes later.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import eastern_today, parse_date  # noqa: E402

API = "https://api.kit.com/v4/broadcasts"
GUID_PREFIX = "viewdeals-edition-"
SEND_DELAY_MINUTES = 10     # time for GitHub Pages to publish the pages the email links to


def read_edition(feed_path):
    """Return {guid, date, subject, html} for the feed's one item, or None when it has none."""
    item = ET.parse(feed_path).getroot().find("./channel/item")
    if item is None:
        return None
    guid = (item.findtext("guid") or "").strip()
    day = parse_date(guid[len(GUID_PREFIX):]) if guid.startswith(GUID_PREFIX) else None
    if not day:
        raise ValueError(f"daily.xml item has an unexpected guid: {guid!r}")
    return {"guid": guid, "date": day, "subject": (item.findtext("title") or "").strip(),
            "html": item.findtext("description") or ""}


def call(method, url, key, body=None):
    """One Kit API request; returns (status, parsed JSON)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Kit-Api-Key": key, "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": "viewdeals-daily-email"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(text)
        except ValueError:
            return err.code, {"errors": [text[:300]]}


def payload(edition, mode, now):
    body = {
        "subject": edition["subject"],
        "preview_text": "This morning's new deals, each one checked by hand.",
        "description": edition["guid"],          # internal label; also how a repeat run spots its own work
        "content": edition["html"],
        "public": False,
        "published_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "send_at": None,
    }
    if mode == "send":
        body["send_at"] = (now + dt.timedelta(minutes=SEND_DELAY_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return body


def run(feed_path, today, key, mode, dry_run=False, request=call, now=None, out=print):
    """Returns the process exit code."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if mode not in ("draft", "send"):
        out(f"ERROR: KIT_SEND_MODE must be draft or send, not {mode!r}")
        return 1
    edition = read_edition(feed_path)
    if not edition:
        out("No new deals in today's edition; no email.")
        return 0
    if edition["date"] != today:
        out(f"The edition in daily.xml is for {edition['date']}, not today ({today}); no email.")
        return 0
    body = payload(edition, mode, now)
    if dry_run:
        out(json.dumps(body, indent=2, ensure_ascii=False))
        return 0
    if not key:
        out("KIT_API_KEY is not set, so the daily email is not set up yet; nothing done.")
        return 0

    status, data = request("GET", API + "?slim=true&per_page=100", key)
    if status != 200:
        out(f"ERROR: Kit refused the list request ({status}): {data.get('errors')}")
        return 1
    if any(b.get("description") == edition["guid"] for b in data.get("broadcasts", [])):
        out(f"Kit already has a broadcast for {edition['guid']}; nothing done.")
        return 0

    status, data = request("POST", API, key, body)
    if status != 201:
        out(f"ERROR: Kit refused the broadcast ({status}): {data.get('errors')}")
        return 1
    made = data.get("broadcast", {})
    what = f"scheduled for {body['send_at']}" if mode == "send" else "saved as a draft (KIT_SEND_MODE is draft)"
    out(f"Broadcast {made.get('id')} \"{edition['subject']}\" {what}.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make today's ViewDeals edition into a Kit broadcast.")
    ap.add_argument("--dry-run", action="store_true", help="print the broadcast; call nothing")
    ap.add_argument("--today", help="treat this YYYY-MM-DD date as today")
    ap.add_argument("--feed", default=str(Path(__file__).resolve().parent.parent / "docs" / "daily.xml"))
    args = ap.parse_args(argv)
    today = parse_date(args.today) if args.today else eastern_today()
    if not today:
        print(f"ERROR: --today {args.today} is not a YYYY-MM-DD date")
        return 1
    return run(args.feed, today, os.environ.get("KIT_API_KEY", "").strip(),
               (os.environ.get("KIT_SEND_MODE") or "draft").strip().lower(), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
