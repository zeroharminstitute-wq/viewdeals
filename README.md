# ViewDeals

ViewDeals is a deals website at **viewdeals.com**. It has no server, no database and no monthly bill. Here's how it works:

1. Every deal lives in one file, `data/deals.json`.
2. A small Python program, `scripts/build.py`, checks that file against the rules and turns it into the finished website in the `docs/` folder.
3. GitHub Pages hosts `docs/` for free and republishes the site about two minutes after every change.
4. Each night a GitHub robot takes down expired deals. Each morning a Claude scheduled task finds new deals, writes them up and publishes them.

This guide covers everything you, the owner, need to do. It assumes no programming experience. Do the steps in order; each one says how long it takes and how to tell it worked.

| Step | What | Who | Time |
| --- | --- | --- | --- |
| 1 | GitHub account and the `gh` tool | You | 15 min |
| 2 | Put the site on GitHub | Claude Code | 5 min |
| 3 | Point viewdeals.com at GitHub (DNS) | You | 15 min, then up to a few hours of waiting |
| 4 | Turn on HTTPS | Claude Code or you | 1 min |
| 5 | Google Search Console and Bing | You, with Claude Code | 20 min |
| 6 | IndexNow (instant indexing on Bing) | Claude Code | 5 min |
| 7 | Cloudflare Web Analytics | You | 10 min |
| 8 | Affiliate programs | You | 30 min each, plus waiting for approval |
| 9 | The daily scheduled task | You | 10 min |

---

## Step 1. GitHub account and the `gh` tool

GitHub stores the site's files and hosts the website.

1. Create a free account at [github.com/signup](https://github.com/signup). Your username will appear in one DNS record later, so pick one you're happy with.
2. Install the GitHub command-line tool. On Windows, open **PowerShell** and run:

   ```powershell
   winget install --id GitHub.cli
   ```

   On a Mac, install it from [cli.github.com](https://cli.github.com).
3. Close PowerShell, open it again, and log in:

   ```powershell
   gh auth login
   ```

   Choose **GitHub.com**, then **HTTPS**, then **Login with a web browser**, and follow the prompts.

**It worked if** `gh auth status` says "Logged in to github.com".

## Step 2. Put the site on GitHub

Tell Claude Code "go" for Phase 7 and it runs these commands for you:

```powershell
gh repo create viewdeals --public --source . --push
```

```powershell
gh api -X POST repos/zeroharminstitute-wq/viewdeals/pages -f "source[branch]=main" -f "source[path]=/docs"
```

```powershell
gh api -X PUT repos/zeroharminstitute-wq/viewdeals/pages -f cname=viewdeals.com
```

The repository has to be **public**, because free GitHub Pages only serves public repositories. Nothing secret is stored in it: the only ID in the files is your Amazon tracking ID, which appears in every Amazon link on the site anyway.

**It worked if** github.com/zeroharminstitute-wq/viewdeals shows the files, and its **Settings → Pages** says "Your site is live" or "DNS check in progress".

## Step 3. Point viewdeals.com at GitHub (DNS)

Do this where you bought the domain (GoDaddy, Namecheap, Squarespace and so on) or in Cloudflare if your domain uses it. Look for a page called **DNS**, **DNS records** or **Manage DNS**.

1. Delete any existing **A**, **AAAA** or **CNAME** records whose name is `@` (sometimes shown as `viewdeals.com` or left blank) or `www`. Leave MX and TXT records alone, because those handle email.
2. Add these five records:

   | Type | Name | Value |
   | --- | --- | --- |
   | A | @ | 185.199.108.153 |
   | A | @ | 185.199.109.153 |
   | A | @ | 185.199.110.153 |
   | A | @ | 185.199.111.153 |
   | CNAME | www | zeroharminstitute-wq.github.io |

3. **On Cloudflare only:** click the orange cloud next to each record so it turns grey ("DNS only"). You can turn it orange again after Step 4 if you want.
4. Optional but recommended: in GitHub go to your profile picture → **Settings → Pages → Add a domain** and verify viewdeals.com. That stops anyone else from claiming it on GitHub.

DNS changes usually take 10–60 minutes to spread, and occasionally a few hours.

**It worked if** GitHub's **Settings → Pages** shows a green "DNS check successful".

## Step 4. Turn on HTTPS

When the DNS check is green, GitHub issues a free security certificate. This can take another hour. Then either tick **Enforce HTTPS** in **Settings → Pages**, or let Claude Code run:

```powershell
gh api -X PUT repos/zeroharminstitute-wq/viewdeals/pages -F https_enforced=true
```

**It worked if** these all load with a padlock: https://viewdeals.com, https://www.viewdeals.com, https://viewdeals.com/sitemap.xml and https://viewdeals.com/feed.xml. Typing http://viewdeals.com should also jump to the https address.

## Step 5. Google Search Console and Bing Webmaster Tools

These tell Google and Bing the site exists and show you which searches bring people in.

1. Go to [Google Search Console](https://search.google.com/search-console) and add a **URL prefix** property for `https://viewdeals.com/`.
2. Choose the **HTML tag** method. Google shows a line like `<meta name="google-site-verification" content="abc123..." />`. Copy only the code inside `content="..."`.
3. Do the same at [Bing Webmaster Tools](https://www.bing.com/webmasters). The easiest route is **Import from Google Search Console** once Google is verified. If you add the site by hand, choose the **meta tag** method and copy its `content` code.
4. Give both codes to Claude Code, or paste them into `site.config.json` yourself:

   ```json
   "verification": {
     "google": "abc123...",
     "bing": "DEF456..."
   },
   ```

5. After the site is rebuilt and pushed, click **Verify** in each tool.
6. In each tool, open **Sitemaps** and submit `https://viewdeals.com/sitemap.xml`.

**It worked if** both tools say the site is verified and the sitemap status is "Success". Search data starts showing after a few days.

## Step 6. IndexNow (instant indexing on Bing)

IndexNow tells Bing, Yandex, Seznam and Naver about new and changed pages within minutes. Google doesn't use it; it reads the sitemap instead.

Ask Claude Code to "turn on IndexNow". It creates a random key, puts it in `site.config.json` under `indexnow_key`, and rebuilds. The key isn't a password. It just proves the site is yours, which is why the build publishes it at `https://viewdeals.com/<key>.txt`.

From then on, every time GitHub Pages finishes publishing, the `indexnow` workflow sends the pages whose content changed.

**It worked if** the **Actions** tab on GitHub shows an **indexnow** run with a green tick and "IndexNow response: 200" (or 202) in its log.

## Step 7. Cloudflare Web Analytics

Free, cookieless visitor counts. It needs no cookie banner and is the only outside script the site loads.

1. Create a free account at [cloudflare.com](https://dash.cloudflare.com/sign-up), go to **Analytics & Logs → Web Analytics**, and add `viewdeals.com`.
2. Cloudflare shows a snippet containing `"token": "..."`. Copy that token.
3. Give it to Claude Code, or paste it into `site.config.json`:

   ```json
   "analytics": {
     "cloudflare_token": "your-token-here"
   },
   ```

4. Rebuild and push. If your DNS is on Cloudflare with the orange cloud on, you can switch on automatic setup in Cloudflare instead. Do one or the other, not both.

**It worked if** visits appear in the Cloudflare dashboard within an hour of someone opening the site.

## Step 8. Affiliate programs

### Amazon Associates

1. Wait until the site is live with deals on it. Amazon reviews the site itself.
2. Apply at [affiliate-program.amazon.com](https://affiliate-program.amazon.com). For the website, enter `https://viewdeals.com`.
3. Amazon gives you a **tracking ID** ending in `-20`. Put it in `site.config.json`:

   ```json
   "amazon": {
     "name": "Amazon",
     "query_params": { "tag": "yourid-20" },
   ```

   The build adds it to every Amazon link. Never paste `tag=` into a deal's link yourself: the build rejects it.
4. **Important:** Amazon closes new accounts that don't make 3 qualifying sales within 180 days. Share the site with friends, family and social followers early.

The site follows Amazon's rules automatically. It never shows Amazon prices, discounts, star ratings or product photos, because Amazon only allows those through its own data feed (the Product Advertising API). After your first 3 sales you can apply for that API. The site is already set up to show exact Amazon product photos once you have it; ask Claude Code to switch `product_images` for Amazon to `"api"`.

### Walmart, Target and Best Buy (optional)

All three run their programs through [Impact](https://impact.com). Join Impact, apply to each brand, and for each one that approves you, copy its **deep link** or **tracking link** template. It looks like a link containing a spot for the product address. Give each template to Claude Code, which puts it into that retailer's `link_template` with `{url}` where the product link goes.

These programs often supply product photos to affiliates. Once a program does, its `product_images` can be set to `"feed"`, and deals from that store will show the exact product. Until then deals show no photo, by design: a deal's picture is always the exact item or nothing.

## Step 9. The daily scheduled task

This is what finds and publishes new deals every morning.

1. In Claude, go to **Settings → Connectors** and connect **GitHub**. Give it access to the `viewdeals` repository, including permission to push.
2. Create a new scheduled task:
   - **Schedule:** every day at **6:13 AM Eastern**, so new deals are up before the morning shopping peak.
   - **Prompt:** paste everything in [DAILY_TASK_PROMPT.md](DAILY_TASK_PROMPT.md) below the line that says "copy from here".
   - **Repository:** attach `viewdeals`.
3. Run it once by hand and read its report.

For the first week, read each morning's report and click a few of the new deals to check they're real and correctly described. The task follows [MAINTENANCE.md](MAINTENANCE.md), which is the rulebook for what it adds and removes.

**It worked if** the repository gets a commit named like `Daily deals update 2026-11-26 (+7 new, -3 expired)` and the new deals appear on the site a few minutes later.

---

## Step 10. The daily email (Kit)

The site can collect email addresses and send each morning's new deals through [Kit](https://kit.com), whose free plan covers up to 10,000 subscribers. Both halves stay switched off until you do the steps below.

**The sign-up box**

1. Create a free Kit account. Kit asks for a postal address to print at the bottom of every email; the law requires one.
2. In Kit, create a form. Open its **Embed** options, choose **HTML**, and copy the code.
3. From that code, put the form's `action` address into `form_action` in the `newsletter` block of `site.config.json`, the `name` of its email box into `email_field`, any hidden boxes into `hidden_fields`, and `Kit` into `provider_name` (the Privacy page names it). Claude can do this step if you paste the code into a chat.
4. Rebuild and push. A sign-up box appears on the home page and above the footer everywhere else, and the Privacy page changes its wording to match.

**The morning email**

1. In Kit, open **Settings → Developer** and create a **V4 API key**. Kit shows it once.
2. On GitHub, open the `viewdeals` repository → **Settings → Secrets and variables → Actions → New repository secret**. Name it `KIT_API_KEY` and paste the key. Never put the key in a file or a chat.
3. From then on, each time the daily task pushes a new edition, the `daily-email` job makes a **draft** broadcast in Kit from `docs/daily.xml`. Look at a draft or two in Kit.
4. When the drafts look right, switch to sending: same GitHub page, **Variables** tab → **New repository variable**, name `KIT_SEND_MODE`, value `send`. Emails then go out about 10 minutes after each morning's push. Delete the variable to go back to drafts.

A day with no new deals sends nothing, and an edition is never sent twice. `daily.xml` links only to ViewDeals pages. Amazon does not allow its affiliate links in email, so never paste retailer links into an email by hand.

## The price record

For Walmart, Target and Best Buy deals, the daily task writes down the price it saw (`price` and `price_checked` in `data/deals.json`). The build keeps every one in `data/price-log.json` and shows them on the site: the price with the day it was checked, a "Lowest in our N price checks" line when the record supports it, and a table of past checks on the deal's page. Amazon prices are never recorded or shown, because Amazon's rules forbid it.

## What runs by itself

| What | When | Where to look |
| --- | --- | --- |
| **ci**: runs the tests and checks the data | Every push | GitHub → **Actions** → ci |
| **nightly-prune**: archives expired deals and rebuilds | 12:07 AM Eastern | Actions → nightly-prune; commits named "Nightly prune …" |
| **indexnow**: tells Bing which pages changed | After each publish | Actions → indexnow |
| **Daily scheduled task**: finds, writes and publishes deals | 6:13 AM Eastern | Claude's task history; commits named "Daily deals update …" |

GitHub emails you when a workflow fails. You can run **nightly-prune** or **indexnow** by hand: open it in the **Actions** tab and click **Run workflow**.

## Changing things yourself

The safest way is to ask Claude Code ("add this deal", "end the Stanley deal", "change the tagline"). If you'd rather edit directly:

- **Open the file on github.com** (for example `data/deals.json`), click the pencil icon, make the change and click **Commit changes**.
- **Your change appears on the site after the next build:** the nightly prune or the morning task, whichever comes first. To publish sooner, ask Claude Code to rebuild and push.
- **Never edit anything in `docs/`.** The build deletes and rewrites it every time, so hand edits vanish.
- **If you break a rule** (a missing field, a price on an Amazon deal, a typo in a date), the **ci** workflow turns red and the error names the deal and the problem. Nothing is published until it's fixed.

What each file is for:

| File | What's in it | How often it changes |
| --- | --- | --- |
| `site.config.json` | Site name, contact email, affiliate settings, verification codes, analytics | Rarely, and only by you |
| `data/deals.json` | Every live deal | Daily |
| `data/archive.json` | Expired deals. It only ever grows; don't delete it | Nightly |
| `data/events.json` | Sale events (Black Friday, Prime Day…) and this year's dates | A few times a year |
| `data/guides/` | One file per buying or gift guide | Twice a week |
| `data/seo-notes.md` | The weekly SEO note | Mondays |
| `data/page-state.json` | Content fingerprints so "Updated" dates are honest. Written by the build; don't edit | Every build |
| `data/photo-sources.json`, `data/photos.json` | The header photos on departments, events and guides, and their credits | When a photo changes |
| `assets/` | Styles, fonts, illustrations, photos, share images | When the design changes |
| `docs/` | The finished website. Generated, never edited | Every build |
| `MAINTENANCE.md` | The daily task's rulebook | When you change the rules |

## For developers

You need Python 3.12 or newer. The site and build use only Python's standard library.

```powershell
python scripts/build.py --check
```

Validates the data and writes nothing. It prints `OK: N deals are valid.` or one line per error.

```powershell
python scripts/build.py
```

Validates and builds `docs/` as of today in New York.

```powershell
python scripts/build.py --prune
```

Archives deals that expired before today, then builds. Add `--today YYYY-MM-DD` to any command to pretend it's another day, which is useful for previewing how a deal page ages.

```powershell
python -m unittest discover tests
```

Runs the test suite, which takes a few seconds.

```powershell
python -m http.server 8123 -d docs
```

Serves the built site at http://localhost:8123. Note that this simple server doesn't show `404.html` for missing pages, though GitHub Pages does.

Developer-only tools in `scripts/dev/` need extra packages (Pillow and fonttools). They aren't needed to build the site:

- `treat_photos.py` crops and compresses the free-license header photos listed in `data/photo-sources.json` (natural colour; `--style riso` gives the old two-ink print look).
- `make_share_images.py --fonts DIR` draws the 1200×630 social share cards and the logo. It needs the full Newsreader and Hanken Grotesk TTF fonts.
- `make_placeholder_art.py` and `screenshot.py` make placeholder art and take design screenshots.

The full specification is [BUILD_PLAN.md](BUILD_PLAN.md).
