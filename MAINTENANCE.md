# ViewDeals daily maintenance runbook

This is the rulebook for the daily curation task, which `DAILY_TASK_PROMPT.md` starts every morning at 6:13 AM Eastern. A person can follow it by hand too. Do the steps in order. Never skip **Publish** checks to save time.

Two jobs keep the site fresh:

- **The nightly prune** (`.github/workflows/nightly-prune.yml`) runs at 12:07 AM Eastern. It moves expired deals into `data/archive.json` and rebuilds the site. It runs even when nothing else does.
- **The daily task** (this runbook) removes deals that ended early, adds new ones, writes the strongest up as their own pages, keeps event hubs current, writes guides on Mondays and Thursdays, and writes the weekly SEO note on Mondays.

Commands below use `python3`. On Windows use `python`.

---

## 1. Setup

1. Pull the latest `main`: `git checkout main`, then `git pull --rebase`.
2. **Today** is the current date in America/New_York, not UTC. Get it with `TZ=America/New_York date +%F`, and use that `YYYY-MM-DD` value everywhere below as `TODAY`. Note the weekday too: Monday and Thursday have extra work.
3. Run `python3 scripts/build.py --check --today TODAY`. If it fails before you have changed anything, someone else broke the data. Fix only what the error names, and put it at the top of the report.

## 2. Remove

1. Run `python3 scripts/build.py --prune --today TODAY`. This archives everything that expired before today. It is safe to run twice.
2. Re-check by hand every **featured** deal and every deal whose `expires` is within 2 days of today. Open the retailer page and the source.
3. If a deal has ended early, sold out, or a source says it's over, end it. Set its `expires` to **yesterday**, then run `--prune` again. If yesterday is before its `added` date, set `added` to yesterday as well. Don't delete deals from `deals.json` by hand: archived deals keep their pages working (see "Deal page lifecycle" below).
4. If a deal is still on but its end date changed, update `expires` and `label`.

## 3. Find

**Targets:**

| Item | Normal week | Big sale week (Prime Day, Prime Big Deal Days, Black Friday to Cyber Monday) |
| --- | --- | --- |
| New deals per day | 5–10 | 5–10 |
| Live deals in total | 15–30 | Up to 40 |
| Categories covered | At least 4 | At least 4 |

Fewer good deals beats more weak ones. If you can only find 3 that pass **Qualify**, add 3 and say so in the report.

**Sources**, in this order. Use only items dated within the last 48 hours.

1. Retailers' own deal pages:
   - amazon.com/deals and aboutamazon.com
   - walmart.com/shop/deals
   - target.com (Deals and Weekly Ad)
   - bestbuy.com (Top Deals)
2. Reputable roundups:
   - Tom's Guide, TechRadar, 9to5Toys, The Verge, Engadget
   - CNN Underscored, NBC Select, Today
   - The Slickdeals front page (front page only, not the forums)

A roundup is a lead, not proof. Always confirm the deal on the retailer's own page before adding it.

**Amazon exception (owner, 2026-11-25).** Amazon blocks automated browsers, so its pages often can't be opened. When that happens, an Amazon deal may still be added if **two independent reputable sources** from the list above, both dated within 48 hours, report it. List every deal added this way under **Amazon, two-source** in the report, with both source links, so the owner can spot-check it.

## 4. Qualify

Add a deal only if every one of these is true:

- **The retailer is in `site.config.json`**: `amazon`, `walmart`, `target` or `bestbuy`. Use `other` only for another big, established retailer, and say so in the report.
- **It's on sale now**, confirmed on the retailer's page. Amazon deals may instead be confirmed by two independent sources (see **Find**).
- **It's a known or well-reviewed product**, from a recognized brand or with strong reviews from a reputable outlet. No unknown-brand marketplace listings.
- **It isn't a duplicate.** Check `data/deals.json` for the same product at any retailer. If two stores have it, keep the better deal. Also check `data/archive.json`: an archived id can't be reused, so give a returning product a new id such as `stanley-quencher-40oz-dec`.
- **It suits the categories:** `tech`, `home`, `smart-home`, `beauty`, `toys`, `outdoors`, `fashion`, `events`. Use `events` for store-wide sales, not single products.

## 5. Write

### The deal entry

Add each deal to the `deals` array in `data/deals.json`:

| Field | Required | Rule |
| --- | --- | --- |
| `id` | yes | Lowercase letters, numbers and dashes, unique across `deals.json` **and** `archive.json`. Example: `sony-wh-1000xm5` |
| `title` | yes | The product or sale name, as the retailer names it, shortened if needed |
| `retailer` | yes | A key in `site.config.json` → `retailers` |
| `url` | yes | `https://` link to the product page **with no affiliate tag**. Remove `tag=`, `ref=` and tracking junk. The build adds the tag. |
| `category` | yes | A key in `categories` |
| `blurb` | yes | 1–2 original sentences, at most 320 characters. Say why it's worth a look. Never copy the retailer's or a source's wording. |
| `label` | no | 1–3 words, such as `Gift idea`, `Ends Nov 30`, `Doorbuster`, `Lowest we've seen` (only if a source says so) |
| `featured` | no | `true` for the 2–4 top picks. Keep 2–4 featured at all times; un-feature older ones. |
| `added` | yes | `TODAY` |
| `expires` | yes | The last day the deal should show (see below) |
| `source` | yes, for this runbook | The page where you confirmed the deal. It isn't shown on the site; it's there so the deal can be re-checked |
| `event` | no | `black-friday`, `cyber-monday`, `prime-day`, `back-to-school` or `holiday-gifts`, if the deal is part of that live event |

**Links.** For Amazon, use `https://www.amazon.com/dp/ASIN` only when you have confirmed the ASIN on the product page itself. Otherwise use a search link: `https://www.amazon.com/s?k=Brand+Model+Name`. For other stores, use the product page link.

**`expires`.**

- Use the announced end date if there is one.
- For a single-product price drop with no end date, use `added` + 3 days.
- For a sale event with no end date, use `added` + 7 days.

### Amazon compliance (the account can be closed for breaking these)

- **No prices or discount figures anywhere on an Amazon deal.** This covers `title`, `blurb`, `label`, `write_up`, `who_for`, `skip_if`, `hook`, `short_name`, `seo_title` and `meta_description`. No `$`, `€` or `£` with a number, no `30%`, no "percent", no star ratings, no review counts. The build rejects most of these, but don't rely on it. "Save big" and "half off" style wording is also out; say *why* it's a good buy instead.
- **No Amazon product images.** Don't add an `image` field to Amazon deals; the config doesn't allow it until the owner has the Amazon API.
- **No invented claims.** "Lowest price ever" only if a dated source says so, and name the source in the write-up. Never invent reviews, testimonials or personal experience.

For other retailers, prices are allowed but go stale within hours. Prefer the reason it's a good buy over the number.

### Write-ups: the strongest 3–5 new deals get their own pages

A deal gets a page at `/deals/<id>/` only when it has a `write_up` of at least 150 original words. Each day, give the 3–5 strongest new deals these fields:

| Field | Rule |
| --- | --- |
| `write_up` | An array of 3–5 paragraphs, 150+ words in total. 150 is a floor, not a target; 180–300 is typical. |
| `who_for` | One sentence: who this is for |
| `skip_if` | One sentence: who should skip it |
| `related` | 3 ids of related live deals, preferably ones that have pages |
| `short_name` | The name for the page title, for example `Sony WH-1000XM5` |
| `hook` | Why it's good, in 3–5 words, for example `Still-Great ANC Doorbuster` |
| `meta_description` | Optional. 120–155 characters, unique. The build writes one if it's missing. |

The page title is built as `{short_name} Deal: {hook} | ViewDeals` and must be **60 characters or fewer**. If it's too long, shorten `hook`, or set `seo_title` yourself. `--check` reports the exact length.

**Every write-up covers these four things**, in your own words:

1. **Why it's a good deal right now.** Source any claim about price history, for example "the lowest price NBC Select has tracked".
2. **Who it's for, and who should skip it.**
3. **What to check before buying:** model year or generation, size or variant, who the seller is (sold by the retailer, or by a marketplace seller), and the return window.
4. **Better or cheaper alternatives,** naming other deals on the site where they exist.

No filler, no "in today's fast-paced world", no repeating the blurb. Five strong pages a day beat twenty thin ones.

### Event hubs

When a deal belongs to a live event, set its `event`. While an event is live, refresh its entry in `data/events.json` every day:

- **`intro`:** 1–3 sentences saying what's happening now, such as which day it is and what's worth watching. Rewrite it when it goes stale.
- **`start` / `end`:** correct them when retailers announce or extend dates. Set `"dates_confirmed": true` once the dates are official.

See the **Event-hub calendar** below for when to roll each hub forward to next year.

### Guides: Mondays and Thursdays

On Mondays and Thursdays in steady weeks, write one guide. Steady weeks are every week except the big sale weeks; in a big sale week, keeping the deals current comes first. Write the guide on a topic people search for: "best {category} under {budget}", "gifts for {person}", "is {product} worth it", "what to buy for {event}".

Create `data/guides/<slug>.json` (the slug is lowercase with dashes and has no year):

```json
{
  "slug": "gifts-for-coffee-lovers",
  "title": "Gifts for Coffee Lovers That Are on Sale Now",
  "kicker": "Gift guide",
  "dek": "One or two sentences on what the guide covers and how we chose.",
  "author": "viewdeals-desk",
  "published": "TODAY",
  "updated": "TODAY",
  "image": "assets/art/share-holiday-gifts.svg",
  "image_alt": "Short description of the illustration",
  "meta_description": "120 to 155 characters, unique, describing the guide.",
  "sections": [
    {"heading": "How we chose these", "paragraphs": ["...", "..."]},
    {"heading": "For the ...", "paragraphs": ["..."]}
  ],
  "deal_ids": ["deal-id-1", "deal-id-2", "deal-id-3", "deal-id-4", "deal-id-5"]
}
```

Guide rules:

- **`deal_ids` must include at least 5 deals that have pages** (deals with a `write_up`). Write extra write-ups the same day if needed.
- **The title is 60 characters or fewer *including* " | ViewDeals"**, so about 47 characters of your own. It's descriptive, not clever.
- **`image` must be an existing file in `assets/art/`.** Pick the closest `share-*.svg` or `cat-*.svg`. Don't add photos: header photos need the owner's photo tool (`scripts/dev/treat_photos.py`), so list "header photo wanted for <slug>" in the report instead.
- **Use the same rules as write-ups:** original, sourced, and no Amazon prices.
- **When you update an older guide** (swap out ended deals, fix advice), set its `updated` to `TODAY`. Don't change `published`.

### Seasonal calendar

Plan deals, labels and guides around these:

| Month | What to cover |
| --- | --- |
| January | New Year: fitness, organizing, planners, winter clearance |
| February | Valentine's Day (gifts), Presidents Day (mattresses, appliances, TVs) |
| March–April | Spring cleaning, outdoor and garden, tax-refund tech |
| May | Mother's Day (gifts), Memorial Day (grills, outdoor, mattresses, appliances) |
| June | Father's Day (gifts), graduation (laptops, headphones, dorm basics); Prime Day hub goes up |
| July | Prime Day and rival sales (Walmart, Target, Best Buy); Back to School hub goes up |
| August | Back to school: laptops, tablets, backpacks, dorm and lunch gear |
| September | Labor Day (appliances, mattresses, outdoor clearance) |
| October | Prime Big Deal Days, Halloween; Black Friday and Holiday Gifts hubs go up by late October |
| November | Black Friday through Cyber Monday: the biggest weeks of the year |
| December | Holiday gifts, last-minute gifts, and shipping cut-off reminders (standard shipping about Dec 15–18, express about Dec 20–22; confirm each year) |

### Event-hub calendar

Each hub is reused every year at the same URL. Roll it forward 3–4 weeks before the event, so it's crawled and ranking in time:

| Hub | Roll forward by | Usually runs |
| --- | --- | --- |
| `prime-day` | Mid-June | Mid-July, 2–4 days |
| `back-to-school` | Mid-July | Mid-July to Labor Day |
| `black-friday` | Late October | The week before Thanksgiving through the Sunday after |
| `cyber-monday` | Late October | The Monday after Thanksgiving, often plus Tuesday |
| `holiday-gifts` | Late October | November 1 to December 24 |

To roll a hub forward:

1. Set `start` and `end` to next year's dates, with `"dates_confirmed": false` until they're announced. The page then says "expected; not yet announced" and its title shows the new year.
2. Rewrite `intro` for the coming event, including what to expect and when we'll start adding deals.
3. When the dates are announced, update them and set `"dates_confirmed": true`.

Leave a past event's dates alone until its roll-forward date. Then the page shows "Ended for {year}" with its year in the title, which is correct.

### Weekly SEO note: Mondays

Every Monday, add an entry to the **top** of `data/seo-notes.md`, below its heading:

```markdown
## 2026-11-30

- Deal pages added this week: 18 (list the ids)
- Guides added or updated: gifts-for-coffee-lovers (new), black-friday-gifts-worth-giving (updated)
- Event hubs updated: black-friday (daily), cyber-monday (dates confirmed)
- Live deals today: 27 across 7 categories
- Build warnings: none (or quote them)
- Notes: anything the owner should know, such as a hub to roll forward soon or a category that's been thin
```

Count "this week" as the previous Monday through Sunday. Use `git log --since` and `data/page-state.json` (whose `first_seen` dates show when pages first appeared).

## 6. Publish

1. Set `"updated": "TODAY"` at the top of `data/deals.json`.
2. Run `python3 scripts/build.py --check --today TODAY`. **If it fails, fix every error it lists and run it again. Never push while `--check` fails.**
3. Run `python3 -m unittest discover tests`. If a test fails and you can't see why, don't push; report it.
4. Build: `python3 scripts/build.py --today TODAY`. The build also checks every internal link and every page head; any error means don't push.
5. Commit everything (`data/` and `docs/`) with the message:

   ```text
   Daily deals update TODAY (+N new, -M expired)
   ```

   N is the number of deals added and M the number removed today, both pruned and ended early.
6. Push: `git push origin main`. If the push is rejected because the nightly prune pushed first:
   - run `git pull --rebase`;
   - if `docs/` or `data/page-state.json` conflict, take either side, then rebuild with step 4;
   - commit and push again.
7. About 2 minutes later, open https://viewdeals.com and confirm the edition date and a couple of the new deals.

## 7. Report

Start the report with **blockers**: anything that stopped a step or needs the owner, such as `--check` failing, a failed push, a missing permission, or a source that couldn't be reached. Write "No blockers" if there were none. Then:

- **Added (N):** id, title, retailer, category. Mark which got a write-up page.
- **Amazon, two-source:** each Amazon deal confirmed through two sources instead of Amazon's page, with both links.
- **Removed (M):** id and why (expired, ended early, sold out).
- **Live now:** total count and count per category; featured ids.
- **Broken or suspicious links:** any deal or source link that failed, redirected to a different product, or showed a different price than the source claimed.
- **Coming up:** sale events in the next 4 weeks, and any hub due to roll forward.
- **Guide / SEO note:** the guide written (Mon/Thu) and the SEO note (Mon), or why not.
- **Owner to-dos:** for example "header photo wanted for gifts-for-coffee-lovers".

## 8. Never

- **Never edit affiliate settings** in `site.config.json`: `query_params`, `link_template`, `product_images`, verification codes, analytics or the IndexNow key. Only the owner changes those. If a link template looks wrong, report it.
- **Never put `tag=`** or any affiliate parameter in a deal `url`.
- **Never host, copy or link Amazon product images.**
- **Never show Amazon prices,** discount figures, star ratings or review counts.
- **Never delete or rewrite `data/archive.json`**, or remove old guides. Ended deal pages stay up on purpose.
- **Never edit files in `docs/` by hand.** The build rewrites it.
- **Never push** when `--check`, the tests or the build fail.
- **Never invent** deals, prices, price history, reviews, testimonials or bylines.

---

## Reference

### Deal page lifecycle (automatic)

| Days after `expires` | What the deal's page does |
| --- | --- |
| 0 (last day) | Live |
| 1–60 | Stays up with a "This deal has ended" banner and 3 related live deals |
| 61–365 | Same, plus `noindex`, and it leaves the sitemap |
| 366+ | Redirects to its department page |

This only works if ended deals reach `archive.json` through `--prune`, which is why you never delete deals by hand.

### Commands

| Command | Does |
| --- | --- |
| `python3 scripts/build.py --check --today TODAY` | Validate only; writes nothing |
| `python3 scripts/build.py --today TODAY` | Validate and build `docs/` |
| `python3 scripts/build.py --prune --today TODAY` | Archive expired deals, then build |
| `python3 -m unittest discover tests` | Run the tests |

### Common `--check` errors

| Error says | Fix |
| --- | --- |
| `Amazon blurb must not show a price or discount` | Remove the `$`, `%` or "percent" wording |
| `url must not contain tag=` | Delete the `tag=...` part of the link |
| `title is 63 characters (max 60)` | Shorten `hook` or `short_name`, or set `seo_title` |
| `description is 162 characters (needs 120-155)` | Edit `meta_description`, or the blurb or `who_for` it's built from |
| `duplicate title` | Make `hook` different from the other deal's |
| `write_up has 120 words; needs 150+` | Write more substance, or remove `write_up` so the deal is a card only |
| `links to 4 deal pages (needs at least 5)` | Add a deal with a page to the guide's `deal_ids`, or write up one more deal |
| `related id 'x' does not exist` | Fix the id, or pick another related deal |
| `duplicate id` | Rename the new deal's id |
