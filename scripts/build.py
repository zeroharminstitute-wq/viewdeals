#!/usr/bin/env python3
"""ViewDeals build script: validate the deals data, then build the static site.

Standard library only. Phase 1 implements validation (--check); the site
build itself arrives in Phase 2.

Usage:
    python3 scripts/build.py --check [--today YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "site.config.json"
DEALS_PATH = ROOT / "data" / "deals.json"
EVENTS_PATH = ROOT / "data" / "events.json"

REQUIRED = ["id", "title", "retailer", "url", "category", "blurb", "added", "expires"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PRICE_RE = re.compile(r"[$€£]\s?\d|\d+\s?%|\bpercent\b", re.IGNORECASE)
BLURB_MAX = 320
WRITE_UP_MIN_WORDS = 150


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def word_count(paragraphs):
    if not isinstance(paragraphs, list):
        return 0
    return sum(len(str(p).split()) for p in paragraphs)


def validate(config, deals, events=None):
    """Return a list of error strings; empty means the data is valid."""
    errors = []
    retailers = config.get("retailers", {})
    categories = config.get("categories", {})
    event_slugs = {e["slug"] for e in (events or {}).get("events", [])}
    seen = set()
    all_ids = {d.get("id") for d in deals if isinstance(d, dict)}

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
                for p in deal["write_up"] + [deal.get("who_for", ""), deal.get("skip_if", "")]:
                    if PRICE_RE.search(str(p)):
                        errors.append(f"{did}: Amazon write-up must not show a price or discount")
                        break
        for rid in deal.get("related", []):
            if rid not in all_ids:
                errors.append(f"{did}: related id '{rid}' does not exist")
        if deal.get("event") and deal["event"] not in event_slugs:
            errors.append(f"{did}: unknown event '{deal['event']}'")

    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate and build ViewDeals.")
    ap.add_argument("--check", action="store_true", help="validate only; write nothing")
    ap.add_argument("--prune", action="store_true", help="archive expired deals, then build")
    ap.add_argument("--today", help="treat this YYYY-MM-DD date as today")
    args = ap.parse_args(argv)

    if args.today and not parse_date(args.today):
        print(f"ERROR: --today {args.today} is not a YYYY-MM-DD date")
        return 1

    config = load_json(CONFIG_PATH)
    data = load_json(DEALS_PATH)
    events = load_json(EVENTS_PATH) if EVENTS_PATH.exists() else {"events": []}
    deals = data.get("deals", [])

    errors = validate(config, deals, events)
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 1

    if not config["retailers"].get("amazon", {}).get("query_params", {}).get("tag"):
        print("WARNING: Amazon tracking tag is empty; Amazon links will not earn commission.")

    if args.check:
        print(f"OK: {len(deals)} deals are valid.")
        return 0

    print("Build not implemented yet (Phase 2).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
