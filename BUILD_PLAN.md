# ViewDeals Build Plan for Claude Code

Nov 25, 2026 · @Todd Benedict

## How to use this plan

Export this doc as Markdown, save it as `BUILD_PLAN.md` in an empty folder, open Claude Code in that folder, and paste the kickoff prompt below. Claude Code works through the phases in order and stops at each gate for you to check.

If you already have `viewdeals.zip` from our chat, unzip it into the folder first. Claude Code will treat it as the starting point and only fill in the gaps, which saves much of Phases 1–2 (the design and SEO layers are new).

What gets built:

- A free static website for viewdeals.com, hosted on GitHub Pages and generated from one deals data file.
- A Python build script (no packages needed) that validates the deals, applies affiliate tags, and writes the site.
- Compliance built in: affiliate disclosures, `rel="sponsored"` links, and no Amazon prices.
- A daily automated update that finds new deals, removes expired ones, and publishes.

### Kickoff prompt (paste into Claude Code)

```text
Read BUILD_PLAN.md in this folder. It is the full spec for viewdeals.com.

Build it phase by phase, exactly as written. If files from viewdeals.zip are
already here, keep them and only change what the spec requires.

Rules:
- Use only the Python standard library for the site and build. No frameworks.
  Dev-only checks such as Lighthouse via npx are fine.
- The Art direction and SEO sections are hard requirements, not suggestions.
- After each phase, run that phase's acceptance checks, show me the results,
  and wait for my "go" before starting the next phase.
- If the spec is unclear or conflicts with itself, ask me. Don't guess.
- Never put real affiliate IDs, API keys or passwords in the repo except the
  Amazon tracking ID in site.config.json, which I will give you.
- Use git. Commit at the end of each phase with a clear message.

Start with Phase 1.
```

## Goals, constraints, and non-goals

The site must cost $0 a month to run, update itself daily, and stay within Amazon Associates rules.

**Goals**

1. Publish a fast, mobile-first deals site at https://viewdeals.com with 15–30 live deals at any time (up to 40 in big sale weeks).
2. Earn affiliate commission on every outbound retailer link, starting with Amazon.
3. Refresh daily: add 5–10 new deals, remove expired ones, publish automatically.
4. Be easy for a non-developer to run: one data file, one config file, plain-English runbook.

**Constraints**

- Hosting: GitHub Pages, free tier, public repo, served from the `/docs` folder of `main`.
- Code: Python 3.9+ standard library only. Plain HTML, CSS and a little vanilla JavaScript. No frameworks, no build tools, and nothing from npm in the shipped site. Dev-only checks run with npx (Lighthouse) are fine.
- Fonts and art are self-hosted. The only third-party request allowed is Cloudflare Web Analytics (free and cookieless; see SEO).
- Amazon content: no prices, percent-off figures, star ratings, or product images (see Compliance).

**Non-goals (for now)**

- User accounts, comments, email newsletter, or a database.
- Live prices through Amazon's Product Advertising API. That only becomes possible after the Associates account has qualifying sales; it's a later phase.
- Analytics. Add a privacy-friendly option later if wanted.

## Architecture and repository layout

One data file feeds one build script, which writes a static site into `docs/` that GitHub Pages serves. Nothing runs on a server.

The daily flow is: the scheduled task edits `data/deals.json` → runs `scripts/build.py` → commits and pushes → GitHub Pages republishes within about two minutes.

Create exactly this layout:

```text
viewdeals/
├── README.md               owner setup guide (GitHub, DNS, affiliate programs)
├── MAINTENANCE.md          daily update runbook (see Daily maintenance)
├── DAILY_TASK_PROMPT.md    prompt for the daily scheduled task
├── site.config.json        site settings, retailers, affiliate tags, categories
├── data/
│   ├── deals.json          live deals, the only file edited day to day
│   ├── archive.json        expired deals, created by --prune
│   ├── events.json         event hubs and this year's dates
│   └── guides/             one JSON file per guide
├── scripts/
│   └── build.py            validate + build
├── tests/
│   └── test_build.py       unittest suite (standard library)
├── assets/
│   ├── style.css
│   ├── app.js              on-page search only
│   ├── favicon.svg
│   ├── fonts/              self-hosted WOFF2 (see Art direction)
│   └── art/                illustrations, annotation marks, share images
├── .github/workflows/   nightly-prune.yml, ci.yml, indexnow.yml (see Daily maintenance, SEO)
├── .gitignore
└── docs/                   GENERATED, committed, never edited by hand
```

`docs/` is committed because GitHub Pages serves it directly from the branch. Every build deletes and regenerates it.

## Data model

Two JSON files hold everything that changes: `site.config.json` (rarely edited, owned by the site owner) and `data/deals.json` (edited daily).

### site.config.json

| Key | Type | Purpose |
| --- | --- | --- |
| `site_name` | string | "ViewDeals" |
| `domain` | string | "viewdeals.com", written to `docs/CNAME` |
| `base_url` | string | "https://viewdeals.com", used for canonical URLs, sitemap, RSS |
| `tagline` | string | "Hand-picked deals, refreshed every day." |
| `description` | string | Meta description for the home page |
| `contact_email` | string | Shown on About, Disclosure, Privacy |
| `timezone` | string | "America/New\_York", defines "today" |
| `retailers` | object | Keyed by retailer slug (see below) |
| `categories` | object | slug → display name |
| `disclosure_short` | string | One-line disclosure shown on every page |

Each retailer entry has `name` and **one** of:

- `query_params`: an object of URL parameters to add. Amazon uses `{"tag": ""}`; the owner fills in the tracking ID, such as `viewdeals-20`. Empty values are skipped.
- `link_template`: a deep-link URL for networks like Impact, with `{url}` where the URL-encoded product link goes. Empty means link directly.

Start with retailers `amazon`, `walmart`, `target`, `bestbuy`, `other`, and categories `tech`, `home`, `smart-home`, `beauty`, `toys`, `outdoors`, `fashion`, `events`.

### data/deals.json

Top level: `{"updated": "YYYY-MM-DD", "deals": [ ... ]}`. Each deal:

| Field | Required | Rules |
| --- | --- | --- |
| `id` | yes | Unique; lowercase letters, numbers, dashes |
| `title` | yes | Product or sale name |
| `retailer` | yes | A key in `retailers` |
| `url` | yes | Full `https://` link, with no affiliate tag in it |
| `category` | yes | A key in `categories` |
| `blurb` | yes | 1–2 original sentences, max 320 characters |
| `label` | no | 1–3 word tag, such as "Gift idea" or "Ends Nov 30" |
| `featured` | no | true for the 2–4 top picks |
| `added` | yes | YYYY-MM-DD |
| `expires` | yes | YYYY-MM-DD, last day shown; on or after `added` |

Example:

```json
{
  "id": "apple-airpods-pro-3",
  "title": "Apple AirPods Pro 3",
  "retailer": "amazon",
  "url": "https://www.amazon.com/s?k=Apple+AirPods+Pro+3",
  "category": "tech",
  "blurb": "Apple's current flagship earbuds, with active noise cancellation and a built-in hearing aid feature.",
  "label": "Black Friday Week",
  "featured": true,
  "added": "2026-11-25",
  "expires": "2026-11-30"
}
```

`data/archive.json` has the same shape (`{"deals": [...]}`) and only ever grows.

## Build script specification

`scripts/build.py` validates the data first and builds nothing if any rule fails. It uses only the standard library.

### Commands

| Command | Does |
| --- | --- |
| `python3 scripts/build.py` | Validate, then build `docs/` as of today |
| `python3 scripts/build.py --check` | Validate only; print `OK: N deals are valid.` or the errors; write nothing |
| `python3 scripts/build.py --prune` | Move deals with `expires` before today into `data/archive.json` (no duplicates), rewrite `deals.json`, then build |
| `python3 scripts/build.py --today YYYY-MM-DD` | Treat that date as today (combine with any flag above) |

Exit code 0 on success and 1 on validation errors, with each error on its own line naming the deal id. If the Amazon tag is empty, print a one-line warning but still build.

### Validation rules (each a separate error)

1. Every required field is present and non-empty.
2. `id` matches `^[a-z0-9][a-z0-9-]*$` and is unique.
3. `retailer` and `category` exist in the config.
4. `url` is `https://` with a host.
5. Amazon deals: the host contains `amazon.` or `amzn.`, and the URL contains no `tag=`.
6. Amazon deals: `title`, `blurb` and `label` contain no price or discount figure. Reject the regex `[$€£]\s?\d|\d+\s?%|\bpercent\b` (case-insensitive).
7. `added` and `expires` parse as ISO dates, and `expires` is on or after `added`.
8. `blurb` is 320 characters or fewer.

### Affiliate link logic

Write one function, `affiliate_url(config, deal)`, and use it everywhere a deal links out (cards, RSS):

1. If the retailer has a non-empty `link_template`, return it with `{url}` replaced by the URL-encoded deal URL.
2. Otherwise, if it has non-empty `query_params`, add them to the URL, replacing any existing parameter of the same name.
3. Otherwise, return the URL unchanged.

Example: tag `viewdeals-20` turns `https://www.amazon.com/s?k=Echo+Dot` into `https://www.amazon.com/s?k=Echo+Dot&tag=viewdeals-20`.

### Build output

- Deals shown: those with `expires` on or after today. Sort featured first, then newest `added`, then soonest `expires`.
- Delete `docs/`, recreate it, and copy `assets/` into `docs/assets/`.
- Write every page listed in the next section, plus `sitemap.xml` (all pages, `lastmod` = `updated`), `robots.txt` (allow all, sitemap line), `feed.xml` (RSS 2.0, one item per live deal, newest first, linking to the affiliate URL), `CNAME` (the domain), and an empty `.nojekyll`.
- HTML-escape every value that comes from JSON.
- Use relative links between pages (`./`, `../`) so the site also works when opened from a local folder.

## Pages, templates, and design

Every page shares one layout: a sticky header (logo, tagline, category chips), a disclosure bar, the main content, and a footer. The core pages are below; the SEO section adds event hubs, deal pages, guides, author pages and How we pick, and the Art direction section sets how every page looks.

### Pages

| Path | Content |
| --- | --- |
| `/` | "Today's best deals", updated date, live count, search box, Top picks (featured), All live deals |
| `/c/<slug>/` (one per category) | Category heading, updated date, count, that category's deals; friendly empty state |
| `/about/` | What the site is, how deals are picked, why no prices, contact |
| `/disclosure/` | Full Amazon Associates statement plus other networks; commissions don't decide picks |
| `/privacy/` | No accounts or personal data; retailer cookies; GitHub Pages logs; contact |
| `/404.html` | "That page is gone. The deal may have ended." plus a link home |

Each page needs: `<title>`, meta description, canonical URL, Open Graph title, description and URL, favicon, RSS link, and a viewport meta.

### Deal card

Top to bottom:

1. The deal's art: its category or event illustration (see Art direction), or a retailer-provided product image where that program allows it. Never emoji, and never a copied Amazon image.
2. Retailer name (bold) · category name.
3. Title, linking out.
4. Blurb.
5. A badge row ("New today" in green if `added` is today, plus `label`), with timing text on the right: "Last day", "Ends tomorrow", "Ends in N days" (7 or fewer), or "Through Mon D, YYYY".
6. A full-width button: "See deal at {Retailer} →".

Every outbound link opens in a new tab with `rel="sponsored nofollow noopener"`. Featured cards get a warm tinted background and border.

### Search (assets/app.js)

On the home page only, typing in the search box filters cards instantly by matching every typed word against each card's title, blurb, retailer and category. Hide sections that end up empty and show "No deals match that search." when nothing matches. No requests, no storage, no tracking.

## Art direction and visual design

The site should read like a beautifully made printed object, not a template: a daily deals circular crossed with a well-designed magazine. Every page is today's "edition". This section replaces any generic styling elsewhere in the plan.

### Concept: The Daily Circular

- **Masthead.** A large "ViewDeals" wordmark above a thin rule, with an edition line underneath: "No. 214 · Wednesday, November 25, 2026 · 17 deals today". The build computes the edition number from the launch date.
- **Front page, not a feed.** One lead deal, set big with its illustration and an editor's note. Beside it, an "Ending soon" sidebar. Below the fold, a mixed grid of feature, standard and compact deals.
- **Departments.** Categories are styled as newspaper sections ("Tech", "Home", "Gifts"), each with its own section front.
- **Retail print cues, used sparingly:** die-cut price tags with a punched hole for labels, a red "New today" ink stamp, highlighter swipes, and hand-drawn circles and arrows around one or two editor's picks per page.

Reference mood: vintage grocery circulars, Sunday newspaper inserts, risograph zines, independent print magazines. It should feel warm, confident, tactile, a little witty, and never cluttered.

### Typography

- **Two self-hosted families, both on the SIL Open Font License.** Headlines and the wordmark use a high-contrast editorial serif with optical sizes; Newsreader is the default. Body text and interface use a crisp grotesque; Hanken Grotesk is the default. If the owner licenses a foundry typeface later, it swaps in through one CSS variable.
- **Scale.** A clear editorial scale: masthead 64–96px; lead headline 40–56px; section heads 28px; body 17px on a 1.55 line height; small labels 13px in the serif's small caps (never tracked-out all caps).
- **Details.** Curly quotes and real dashes; `font-variant-numeric: tabular-nums` for dates and counts; `text-wrap: balance` on headings and `text-wrap: pretty` on body text; hanging punctuation where supported; line length 60–70 characters.

### Color

The palette is two spot colors on paper, like a real print run.

| Role | Light ("day edition") | Dark ("night edition") |
| --- | --- | --- |
| Paper | #F4EFE6 newsprint | #141210 |
| Ink | #161412 | #EEE7DA |
| Spot 1 | #D7261E tag red (stamps, tags, links on hover) | #FF5A4E |
| Spot 2 | #FFD23F highlighter (swipes behind key words only) | #E8C23A at 85% |
| Rules | #161412 at 15% | #EEE7DA at 18% |

All text meets WCAG AA contrast. Dark mode follows `prefers-color-scheme`, with a manual toggle in the footer.

**Amendment (owner, 2026-11-26): white paper, natural photos.** The cream newsprint read as brown, so the site uses clean white paper and neutral inks. The two spot colours, the type and the layout are unchanged. The paper grain texture and the lead-card texture are removed.

| Role | Day edition | Night edition |
| --- | --- | --- |
| Paper | #FFFFFF | #131416 (neutral charcoal) |
| Ink | #111111 | #F2F2F0 |
| Muted text | #555555 | #B4B4B4 |
| Spot 1 | #D7261E tag red | #FF5A4E |
| Spot 2 | #FFD23F highlighter | #E8C23A at 85% |
| Featured wash | #FFF6CC, edge #F0C419 | #1F2024, edge #6B5A1A |
| Rules | #111111 at 13% | #F2F2F0 at 16% |

Every text pair still meets WCAG AA (tag red on white 5.0:1, on the featured wash 4.6:1).

### Illustration and imagery

With no Amazon product photos allowed, illustration carries the visual weight, so it has to be excellent and consistent.

- **One commissioned set in a single style:** two-color risograph-style spot illustrations (ink plus tag red), with visible grain and slight misregistration.
  - 8 category illustrations
  - 6 event illustrations: Black Friday, Cyber Monday, Prime Day, back to school, holiday gifts, and spring sales
  - 1 lead-story texture
  - 1 set of 8 hand-drawn annotation marks: a circle, underline, arrow, star burst, bracket, checkmark, "editor's pick" script, and "last chance" script
- **Where it comes from.** The recommended route is to commission one illustrator for the whole set (Dribbble or a risograph studio; budget roughly $400–1,200). The fallback is to generate images with a locked style prompt, hand-pick for consistency, then vectorize and clean them up. Either way, every file is reviewed by a person before it ships.
- **Never** use emoji, stock icon packs, clip art, 3D blobs, or generic gradient illustrations.
- **Amendment (owner, 2026-11-25): treated photographs.** Departments, event hubs and guides may use real photographs instead of the illustrations, provided that:
  - the photo is free-license (Unsplash or Pexels license, never Unsplash+ or other paid tiers) or the owner's own;
  - it shows no readable brand logos and no identifiable faces;
  - it is prepared by `scripts/dev/treat_photos.py`: shown in natural colour since the 2026-11-26 amendment (the original two-ink treatment remains available as `--style riso`);
  - it is credited in `data/photos.json` (photographer, source, link), shown in a caption on page headers and articles and listed on the About page.
  The illustrations stay as the fallback for anything without a photo.
- **Product photos on deals (owner, 2026-11-25): exact item or nothing.** A deal shows a picture only when it is the exact product being sold, from a source its retailer's affiliate program allows (`product_images` in `site.config.json`; the build refuses anything else). Without one, the deal card and deal page have no picture at all: never a department photo, illustration or look-alike, because readers take any picture on a deal to be the item.
- **Formats.** SVG (optimized, under 30 KB each) or AVIF/WebP at 1x and 2x with explicit width and height, all in `assets/art/`.
- **Retailer product images** are allowed only where that retailer's affiliate program provides them for affiliates. For Amazon, that means only after Product Advertising API access, served from Amazon's own servers.

### Layout

- **Grid.** A 12-column grid up to 1280px wide, with generous outer margins and hairline column rules in the lead area.
- **Front page.** The lead spans 8 columns and the "Ending soon" sidebar spans 4. Below that, an asymmetric mix: 2 feature cards (6 columns each), then rows of standard cards (4 columns) interrupted every 6–8 items by a compact "quick hits" list.
- **Card variants.** Lead, feature, standard and compact (a list row with no art). Never a wall of identical tiles.
- **Tags.** Each tag is rotated by a fixed amount between −2° and +2°, derived from a hash of the deal id, so the page feels placed by hand but never shifts between builds.
- **Mobile, designed rather than merely stacked.** A compact sticky masthead and a swipeable department bar. The lead stays visually dominant. Compact rows keep the page scannable, and tap targets are at least 44px.

### Motion

Three touches, all off under `prefers-reduced-motion`:

1. Tags swing about 3° on hover.
2. The "New today" stamp presses in once on first view.
3. Annotation marks draw themselves on scroll into view, using an SVG stroke-dashoffset animation.

There is no other animation: no parallax, carousels or autoplay.

### Voice

Copy is short, specific and lightly witty, like a good shop clerk: "Fine, it's another air fryer. It's also the one reviewers keep recommending." Avoid hype words ("insane", "unbelievable") and marketing filler.

### Anti-generic rules (Claude Code must check each one)

- [ ] No emoji or stock icons anywhere.
- [ ] No centered hero of headline, subhead and button. No gradient blobs, glassmorphism, or purple.
- [ ] Corner radius 0–4px everywhere except the die-cut tags.
- [ ] No uniform grid of identical cards on any page.
- [ ] Spacing follows a 4px base scale (4, 8, 12, 16, 24, 32, 48, 72, 96).
- [ ] Every page has a clear typographic hierarchy you can read from across a room.
- [ ] Copy has no lorem ipsum, no "Welcome to our website", and no exclamation marks in headings.

### Design process for Claude Code

1. Build a style tile page first, at `/styleguide/` (noindex). It shows the masthead, type scale, colors, every card variant, tags, stamps and annotation marks, in both light and dark.
2. Screenshot it at 390, 768, 1280 and 1600px wide in both modes, then stop for owner approval.
3. Only then apply it to the real templates, and screenshot the home page, one department page and one deal page for a second approval.

### Performance guardrails for the design

- Fonts: subset to Latin, WOFF2 only, at most 4 files, `font-display: swap`, with metric-matched fallbacks (`size-adjust`, `ascent-override`) so the layout doesn't shift when fonts load.
- Preload only the masthead and headline font files.
- Home page first load is under 500 KB total and under 100 KB of CSS and JS combined.
- Paper grain is a tiny inline SVG noise filter, never a large bitmap.

## Compliance requirements

These rules protect the Amazon Associates account, which can be closed for violations. They are not optional, and the build enforces the ones it can.

**Amazon Associates**

- **No prices or discount figures.** Amazon's [linking requirements](https://affiliate-program.amazon.com/gp/associates/help/operating/linking/) only allow prices and availability that Amazon itself serves (through its API). Static pages can't meet that, so Amazon deals never show `$`, `%`, "percent", star ratings, or review counts. Validation rule 6 enforces this.
- **No Amazon product images.** Images must come through Amazon's API too. Use the site's own illustrations instead.
- **No misleading claims.** Don't write "lowest price ever" unless a source says so, and don't invent reviews or testimonials.
- **Tagged links only through the build.** Deal URLs never contain `tag=`; `affiliate_url` adds it from the config.
- **Required statement.** Every page shows: "As an Amazon Associate, ViewDeals earns from qualifying purchases." The Disclosure page uses Amazon's full program wording.
- **Trademark line** in the footer: "Amazon and the Amazon logo are trademarks of Amazon.com, Inc. or its affiliates."

**FTC endorsement guides**

- The disclosure must be clear and appear before the reader clicks. The disclosure bar sits above the deals on every page, not only in the footer.
- Affiliate links carry `rel="sponsored"`, which is also what Google asks for.

**Content**

- Blurbs are written fresh, never copied from a source article or Amazon listing.
- The footer notes that prices and availability change and are set by each retailer.

## SEO

ViewDeals will compete on five things: very fast pages, evergreen URLs that build authority year after year, complete structured data, original content that shows real judgment, and indexing that picks up changes the same day. Most deal sites lose because their pages are thin and disappear within a week. This plan avoids both.

### URL architecture

URLs are lowercase, hyphenated, end in a trailing slash, and never contain a query string. Evergreen pages never have a year in the URL. The year goes in the title and headline instead, so links earned one year keep counting the next.

| Page type | URL | Purpose |
| --- | --- | --- |
| Home | `/` | Today's edition |
| Department | `/c/<slug>/` | Category hub, such as `/c/tech/` |
| Event hub | `/events/<slug>/` | Reused every year: `black-friday`, `cyber-monday`, `prime-day`, `back-to-school`, `holiday-gifts` |
| Deal page | `/deals/<id>/` | One deal with an original write-up (rules below) |
| Guide | `/guides/<slug>/` | Buying guides and gift guides |
| Author | `/authors/<slug>/` | Real bylines for E-E-A-T |
| Method | `/how-we-pick/` | How deals are chosen and checked |

**Deal pages have a lifecycle**, so expired deals never create a pile of 404s or thin pages:

1. The page is created only if the deal has an original `write_up` of at least 150 words. Otherwise the card links straight to the retailer and no page is made.
2. When the deal expires, the page stays up (status 200). It shows a "This deal has ended" banner and links to 3 related live deals.
3. Sixty days after expiry, the page gets `noindex` and leaves the sitemap.
4. After 365 days, the page is replaced by a meta-refresh redirect to its department page. GitHub Pages can't send real 301s, so the build writes a redirect page with a canonical to the department.

### On-page rules (the build enforces them)

- **One H1 per page.** Headings are descriptive, not clever.
- **Titles of 60 characters or fewer, following one pattern per page type:**
  - Deal page: "{Product} Deal: {why it's good in 3–5 words} | ViewDeals"
  - Event hub: "Best Black Friday Deals {year}: Hand-Checked Daily | ViewDeals"
  - Department: "Best {Department} Deals Today | ViewDeals"
- **Meta descriptions** of 120–155 characters, unique per page, generated from the data and overridable per page.
- **Visible dates:** published and updated, in `<time datetime>`. "Updated" changes only when the content actually changes. The build stores a content hash per page to decide.
- **Breadcrumbs** on every page except home.
- **Descriptive alt text** on every illustration; purely decorative art gets `alt=""`.
- **Internal linking:**
  - Every deal page links to its department, the live event hub (if any), and 3 related deals.
  - Every guide links to at least 5 deal pages.
  - Home and the footer link to every event hub.
  - Anchor text is always descriptive, never "click here".
- **Canonical:** self-referential, absolute URL on every page.

### Structured data (JSON-LD, generated by the build)

| Where | Types |
| --- | --- |
| Every page | `Organization` (name, url, logo, `sameAs` social profiles) and `WebSite` with `SearchAction` pointing to `/?q={search_term_string}` |
| Every page but home | `BreadcrumbList` |
| Home, departments, event hubs | `ItemList` of the deal pages shown, with positions |
| Guides | `Article`: headline, image, `author` as `Person` linking to the author page, `datePublished`, `dateModified` |
| Author pages | `ProfilePage` with `Person` |
| Deal pages | `WebPage` with `about`, plus `Product` and `Offer` **only** when a price is legally shown (a non-Amazon program feed, or Amazon's API later) |

Never add `Review` or `AggregateRating` without genuine first-hand reviews. Never fabricate ratings. Skip `FAQPage`, because Google no longer shows FAQ rich results for sites like this. `app.js` must read `?q=` on load and run the search, so that `SearchAction` actually works.

The build checks that every JSON-LD block parses. In Phase 7, check a sample of pages in Google's Rich Results Test and the Schema.org validator.

### Technical performance

| Metric (mobile, field data) | Target |
| --- | --- |
| Largest Contentful Paint | under 2.0 s |
| Interaction to Next Paint | under 200 ms |
| Cumulative Layout Shift | under 0.05 |
| Lighthouse (Performance, Accessibility, Best Practices, SEO) | 95 or higher on home, a department, a deal page and a guide |

How to hit those targets:

- **CSS:** inline critical CSS under 14 KB in the head, and load the rest without blocking rendering.
- **JavaScript:** one deferred script with no dependencies.
- **Images:** the lead illustration gets `fetchpriority="high"`; everything below the fold is `loading="lazy"`; every image has explicit `width` and `height`.
- **HTML:** minified by the build.
- **Links:** a build-time internal link checker fails the build on any broken internal link.
- **Accessibility:** WCAG 2.2 AA, with semantic landmarks, focus states and skip links. This is good SEO too.

### Crawling and indexing

- **Sitemaps.** A sitemap index pointing to `sitemap-pages.xml`, `sitemap-deals.xml` and `sitemap-guides.xml`, with honest `lastmod` dates from the content hash and image entries for the illustrations.
- **robots.txt.** Allow everything except `/styleguide/`, and include the sitemap index line.
- **IndexNow (instant indexing on Bing, Yandex, Seznam and Naver).** The build writes the key file to `docs/<key>.txt`. A GitHub Action that runs after each Pages deploy sends the changed URLs to `api.indexnow.org`. Google doesn't use IndexNow and relies on sitemaps plus Search Console.
- **Verification.** Put the Google Search Console and Bing Webmaster Tools meta tags in `site.config.json` under `verification`, and submit the sitemap index to both.
- **Feeds.** RSS 2.0 at `/feed.xml` and a JSON Feed at `/feed.json`.
- **noindex** on `/styleguide/`, on deal pages more than 60 days past expiry, and on any empty department (but not its links).

### Content quality and E-E-A-T

Google rewards affiliate content that adds something the retailer page doesn't, and demotes thin or mass-produced pages. Every write-up therefore covers:

- Why this is a good deal right now, with any claim about price history sourced.
- Who it's for, and who should skip it.
- What to check before buying: model year, size or variant, the seller, the return window.
- Better or cheaper alternatives, linking to other deal pages where they exist.

Rules:

- **Real bylines only.** The owner's real name and bio, or a clearly labeled "ViewDeals Desk" that links to `/how-we-pick/`. No invented personas or credentials.
- **No scaled filler.** It's better to publish 5 strong deal pages a day than 20 thin ones. The 150-word original minimum is a floor, not a target.
- **Freshness.** Event hubs are updated daily while the event is on.

**Editorial calendar.** Publish each event hub 3–4 weeks before the event so it's crawled and ranking in time: Prime Day by mid-June, Back to School by mid-July, Black Friday and Holiday Gifts by late October. In steady weeks, the daily task also writes 2 guides a week, on Monday and Thursday.

**Keyword strategy.** Target long-tail searches that a small, fresh site can win:

- "{product} deal"
- "{product} Black Friday {year}"
- "is {product} worth it"
- "best {category} under {budget}" (guides only, for non-Amazon pricing)

After month one, re-prioritize from Search Console queries that sit at positions 8–20.

### Social and off-site

- **Social cards.** Open Graph and Twitter card tags on every page. Each department, event hub and guide has a designed 1200×630 share image in the house illustration style; deal pages use their department's image.
- **Pinterest.** Gift guides and event hubs are naturally pinnable with this art style. Add Pinterest rich-pin meta and a "Pin" link on guides.
- **Links.** Earn links with the evergreen hubs and genuinely useful guides. Never buy links or use link networks.

### Measurement

- **Analytics.** Cloudflare Web Analytics: free, cookieless, one small script. This is the only third-party request allowed on the page.
- **Clicks and earnings.** Track outbound clicks and earnings in the Amazon Associates and Impact dashboards.
- **Weekly SEO note.** Every Monday the daily task adds a short entry to `data/seo-notes.md`: pages added, hubs updated, and any build warnings. The owner reviews Search Console monthly.

### Data and build changes for SEO

- **Deals** gain optional fields:
  - `write_up`: an array of paragraphs (needs 150+ words to get a page)
  - `who_for`
  - `skip_if`
  - `related`: deal ids
  - `event`: an event hub slug
- **Guides.** `data/guides/<slug>.json` with title, dek, `author`, `published`, `updated`, `image`, sections (heading plus paragraphs) and `deal_ids`.
- **Events.** `data/events.json` with slug, name, start and end dates for the current year, intro copy, and the share image.
- **Config.** `site.config.json` gains `authors`, `social_profiles`, `verification` and `indexnow_key`.
- **New validation rules:**
  - Titles and descriptions are within length limits.
  - No duplicate titles across pages.
  - Every `related` and `deal_ids` entry exists.
  - Every image path exists and has dimensions.
  - `write_up` meets the minimum before a page is built.

## Deployment: GitHub Pages and DNS

GitHub Pages serves `docs/` from `main` for free, with HTTPS on the custom domain. Claude Code can do the GitHub side if the `gh` CLI is installed and logged in (`gh auth status`); the DNS step is always yours.

### GitHub (Claude Code can do this)

1. `gh repo create viewdeals --public --source . --push`. Free Pages needs a public repo.
2. Turn on Pages from `main` `/docs`: `gh api -X POST repos/{owner}/viewdeals/pages -f "source[branch]=main" -f "source[path]=/docs"`.
3. Set the custom domain: `gh api -X PUT repos/{owner}/viewdeals/pages -f cname=viewdeals.com`. The `docs/CNAME` file keeps it set on every build.
4. Once DNS resolves and GitHub issues the certificate (minutes to a few hours), turn on HTTPS: `gh api -X PUT repos/{owner}/viewdeals/pages -F https_enforced=true`.

### DNS (you do this at your registrar or Cloudflare)

Remove any existing A, AAAA or CNAME records for `@` and `www`, then add:

| Type | Name | Value |
| --- | --- | --- |
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| CNAME | www | YOUR-GITHUB-USERNAME.github.io |

On Cloudflare, set these records to DNS only (grey cloud) until HTTPS is working on GitHub; you can switch the proxy on afterwards if you want. Optionally, verify the domain under GitHub → Settings → Pages → Verified domains, so nobody else can claim it.

### Done when

- `https://viewdeals.com` and `https://www.viewdeals.com` both load the site with a valid certificate.
- `http://` redirects to `https://`.
- `https://viewdeals.com/sitemap.xml` and `/feed.xml` load.

## Daily maintenance automation

Two layers keep the site fresh. A free GitHub Action removes expired deals every night, even if nothing else runs. A daily Claude scheduled task researches new deals and publishes them.

### Layer 1: nightly prune (GitHub Actions, free)

Create `.github/workflows/nightly-prune.yml`:

- Triggers: `schedule` with cron `7 5 * * *` (5:07 UTC, about midnight Eastern) and `workflow_dispatch`.
- `permissions: contents: write`.
- Steps: checkout → set up Python 3.12 → `python3 scripts/build.py --prune --today $(TZ=America/New_York date +%F)` → if `git status --porcelain` shows changes, commit as `github-actions[bot]` with the message `Nightly prune YYYY-MM-DD` and push.
- Also run `python3 -m unittest discover tests` and `--check` on every push and pull request, in a second workflow `ci.yml`.

### Layer 2: daily curation (Claude scheduled task)

Write `MAINTENANCE.md` as the runbook the task follows. It must cover, in this order:

1. **Setup.** Pull `main`; today = the current date in America/New\_York.
2. **Remove.** Run `--prune`; re-check featured deals and deals ending within 2 days; end any that sources say are over.
3. **Find.** Add 5–10 deals a day for 15–30 live in total (40 in big sale weeks), across at least 4 categories. Sources: retailers' own deal pages (amazon.com/deals, aboutamazon.com, walmart.com/shop/deals, target.com, bestbuy.com) and reputable roundups (Tom's Guide, TechRadar, 9to5Toys, The Verge, Engadget, CNN Underscored, NBC Select, Today, Slickdeals front page), dated within 48 hours.
4. **Qualify.** Established retailer in the config; on sale per a recent source; a known or well-reviewed product; not a duplicate.
5. **Write.** Follow the data model and compliance rules. Use `/dp/ASIN` links only when the ASIN is confirmed, otherwise `/s?k=` search links. For `expires`, use the announced end date, or `added` + 3 days for a single-product drop, or + 7 for a sale event. Keep 2–4 featured. Give the strongest 3–5 new deals a \`write\_up\` (150+ original words, following the SEO content rules) so they get their own pages, and refresh any live event hub.
6. **Publish.** Set `updated`, run `--check`, then build. Commit `Daily deals update YYYY-MM-DD (+N new, -M expired)` and push.
7. **Report.** List what was added and removed and the live count, and flag broken links or upcoming sale events.
8. **Never** edit affiliate settings, host Amazon images, show Amazon prices or ratings, or delete the archive.

Include a seasonal calendar: New Year (Jan), Valentine's and Presidents Day (Feb), Memorial Day and Mother's Day (May), Father's Day and graduation (Jun), Prime Day (Jul), back to school (Aug), Labor Day (Sep), Prime Big Deal Days and Halloween (Oct), Black Friday through Cyber Monday (Nov), and holiday gifts and shipping cut-offs (Dec).

Write `DAILY_TASK_PROMPT.md` as a standalone prompt: attach the repo with push access, follow `MAINTENANCE.md` exactly, don't push if `--check` fails, and put any blocker at the top of the report. The suggested schedule is daily at 6:13 AM Eastern, so new deals are up before the morning shopping peak. The owner creates the task in Claude once the repo exists.

## Build phases with acceptance criteria

Eight phases, each ending in a commit and a stop for your "go". Phases 1–6 run entirely on your computer; phases 7 and 8 need GitHub. Design gets two approval gates, because it's the part most worth getting right.

1. **Scaffold and data.** Create the layout, `.gitignore`, `site.config.json` (with the SEO keys), `data/events.json`, and `data/deals.json` with 10–20 real current deals researched on the web. At least 5 of them get full `write_up`s.
   - Done when `--check` prints OK and every deal URL opens a real page.
2. **Build engine.** Implement `build.py`: commands, validation (including the SEO rules), `affiliate_url`, prune, the deal page lifecycle, the content hash for `updated`, and HTML minification.
   - Done when `--prune --today` a week, 61 days and 366 days ahead each produce the right banner, `noindex` or redirect.
3. **Design system (gate 1).** Fonts, palette, type scale, every card variant, tags, stamps, annotation marks and motion, built as `/styleguide/`. Until the commissioned art arrives, use clearly marked placeholder art.
   - Done when screenshots at 390, 768, 1280 and 1600px wide in light and dark pass the anti-generic checklist, and the owner approves.
4. **Templates (gate 2).** Home front page, departments, event hubs, deal pages, guides, author pages, How we pick, About, Disclosure, Privacy and 404, all in the approved design.
   - Done when the owner approves screenshots of home, one department, one deal page and one guide.
5. **SEO layer.** JSON-LD for every type, the sitemap index, robots, RSS and JSON feeds, share images, breadcrumbs, the internal link checker, the IndexNow key file, the `?q=` search, and verification meta.
   - Done when every JSON-LD block parses, the link checker passes, and Lighthouse (via npx, mobile) scores 95+ in all four categories on 4 page types.
6. **Tests, docs and workflows.** `tests/test_build.py`, `README.md`, `MAINTENANCE.md` (including write-ups, guides on Monday and Thursday, the event-hub calendar, and the weekly SEO note), `DAILY_TASK_PROMPT.md`, and the `ci`, `nightly-prune` and `indexnow` workflows.
   - Done when the unit tests pass and the README walks a non-developer through setup.
7. **Deploy and verify.** Create the repo, push, turn on Pages and set the domain; you add DNS. Then: Search Console and Bing Webmaster Tools verified with the sitemap submitted, Rich Results Test passing on home, a deal page and a guide, and Cloudflare Web Analytics on.
   - Done when everything under "Done when" in Deployment is true, and the IndexNow workflow reports a 200 or 202 response.
8. **Go live with affiliates and automation.** Paste in the Amazon tag once approved, rebuild and push; you create the daily scheduled task; trigger the nightly prune once by hand.
   - Done when live Amazon links carry `tag=` and the first scheduled run publishes a commit with at least one new deal page.

## Testing and verification

Claude Code runs every check below before saying a phase is done, and shows you the output.

### Unit tests (tests/test\_build.py, unittest)

- `affiliate_url`: an Amazon tag is added; an existing parameter with the same name is replaced; an empty tag leaves the URL unchanged; a `link_template` URL-encodes the deal URL into `{url}`.
- Validation: one failing deal for each of the 8 rules produces exactly that error; the seed data passes.
- Prune: with `--today` set after some expiry dates, the expired deals move to the archive, none are duplicated on a second run, and live deals stay.
- Build: run into a temp copy of the repo and assert that every expected file exists, deal titles are HTML-escaped, a deal expiring today still shows, and one that expired yesterday doesn't.

### Manual checks

- [ ] `--check` passes and `unittest` passes.
- [ ] `python3 -m http.server -d docs` → click every nav chip, footer link and a sample of deal buttons; nothing 404s.
- [ ] Headless Chrome screenshots at 1280 and 390 wide; review both.
- [ ] Search for "vacuum" shows only matching cards; nonsense text shows the empty message.
- [ ] `grep -rE '\$[0-9]|[0-9]+%' docs/` finds nothing on Amazon cards.
- [ ] With a test tag in the config, every amazon.com link in `docs/` contains `tag=`; revert the tag afterwards.
- [ ] The disclosure bar is visible above the fold on mobile.
- [ ] After deploy: HTTPS works on both hostnames, and the sitemap is submitted in Google Search Console.

### Design and SEO checks

- [ ] Every item on the anti-generic checklist in Art direction passes on every page type.
- [ ] Screenshots at 390, 768, 1280 and 1600px wide in light and dark show no overlap, clipping or orphaned single words in headings.
- [ ] Lighthouse mobile scores 95+ in all four categories on home, a department, a deal page and a guide.
- [ ] Layout shift is under 0.05 with fonts loading on a throttled "Slow 4G" connection.
- [ ] Every page has one H1, a unique title of 60 characters or fewer, a description of 120–155 characters, a canonical URL, OG tags and breadcrumbs (except home).
- [ ] The Rich Results Test shows valid Breadcrumb data, and the Schema.org validator shows no errors, on home, a deal page and a guide.
- [ ] `/?q=vacuum` opens with the search already applied.
- [ ] An expired deal page shows the ended banner; at 61 days it is `noindex` and gone from the sitemap; at 366 days it redirects.
- [ ] Every URL in the sitemap index returns 200 locally and is not `noindex`.

## Owner-only tasks

These need your accounts or decisions, so Claude Code will pause and ask you at the right phase.

- [ ] Create a GitHub account, and install and log in to the `gh` CLI (`gh auth login`) before Phase 5.
- [ ] Add the DNS records at your registrar or Cloudflare (Phase 5).
- [ ] Create a contact inbox such as hello@viewdeals.com, or give Claude Code the address to use instead.
- [ ] Apply to [Amazon Associates](https://affiliate-program.amazon.com) once the site is live with deals. Paste the tracking ID into `site.config.json` → `retailers.amazon.query_params.tag`. New accounts are closed if they don't make 3 qualifying sales within 180 days, so share the site early.
- [ ] Optionally, join Walmart, Target and Best Buy through [Impact](https://impact.com) and paste each deep-link template into its `link_template`.
- [ ] Connect GitHub to Claude (Settings → Connectors) and create the daily scheduled task from `DAILY_TASK_PROMPT.md` (Phase 6).
- [ ] Add the site to [Google Search Console](https://search.google.com/search-console) and submit `sitemap.xml`.
- [ ] Read the first week of daily reports and spot-check a few deals.

Added for design and SEO:

- [ ] Commission the illustration set (Art direction lists exactly what to order), or approve the image-generation fallback. Placeholders are fine until it's delivered.
- [ ] Approve the two design gates (Phases 3 and 4).
- [ ] Decide on bylines: your real name with a short bio and photo, or "ViewDeals Desk".
- [ ] Create the social profiles you want listed in `sameAs`. Pinterest is the priority for gift guides.
- [ ] Verify the site in Bing Webmaster Tools as well as Google Search Console, and turn on Cloudflare Web Analytics (free).
