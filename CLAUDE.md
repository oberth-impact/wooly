# Wooly Pig Farm Brewery -- Facebook Content Sync Page

## What this project is

A GitHub Actions + GitHub Pages static site that syncs Facebook Page posts from Wooly Pig Farm Brewery's FB page to a branded web page at `feed.woolypigfarmbrewery.com`. The brewery's main site is on Squarespace (can't programmatically update), so this subdomain page mimics their branding while being independently hosted and SEO-indexable.

## Why it exists

Facebook stopped recommending places that sell alcohol. The brewery's primary content is on FB, so they need that content mirrored to a web page that search engines can find and index.

## Architecture

- **GitHub Action** runs every 6 hours (cron) + manual trigger
- **Python script** (`scripts/sync_fb.py`) fetches posts via Facebook Graph API, downloads images, generates static HTML
- **Output** goes to `docs/` folder, served by GitHub Pages
- **Custom domain**: `feed.woolypigfarmbrewery.com` via CNAME record in Squarespace DNS
- The Squarespace site's "FEED" nav link (currently empty page at woolypigfarmbrewery.com/feed) will be updated to point to this subdomain

## Key design decisions

- **No templating engine.** HTML is generated with plain Python f-strings/str.format(). Only dependency is `requests`. Matches the pub/ project pattern.
- **Images are committed to repo**, not hotlinked from FB CDN. Content-hash filenames for idempotency.
- **`posts.json` cache** persists between runs. If the API fails, the last good data is preserved.
- **Never-expiring Page Access Token** (generated from long-lived user token via `me/accounts` endpoint). Only invalidates if admin changes FB password or revokes app.

## Repo structure

```
wooly-page/
  .github/workflows/sync.yml       # Cron workflow (every 6h) + manual trigger
  scripts/
    sync_fb.py                      # Main script: fetch, download, render
    requirements.txt                # requests (only dependency)
  static/
    style.css                       # Brewery-branded CSS
    logo.png                        # Wooly Pig wordmark (white)
    pig-badge.png                   # Circular pig/hop logo (footer)
    ohio-craft-beer.png             # Ohio Craft Beer badge
    favicon.ico
  docs/                             # GitHub Pages output directory
    index.html                      # Generated
    images/                         # Downloaded FB post images
    CNAME                           # feed.woolypigfarmbrewery.com
  posts.json                        # Cached post data
```

## Brewery branding (from woolypigfarmbrewery.com)

- **Background**: Dark brown `#4A3C31`
- **Nav text**: White uppercase, Raleway, 2px letter-spacing
- **Active nav**: Gold `#FFCC00` (the "FEED" link)
- **Heading font**: Oswald (Google Fonts)
- **Body/nav font**: Raleway (Google Fonts)
- **Content areas**: White `#FFFFFF` backgrounds
- **Teal accent**: ~`#1B5A5A` (used in hero sections)
- **Logo**: "WOOLY PIG / FARM BREWERY" wordmark, white on brown
- **Footer**: Circular red-pigs-on-teal badge, Ohio Craft Beer badge, location/hours/social links, Instagram grid thumbnails

## Facebook API details

- **Page**: facebook.com/woolypigbrewery
- **Page ID**: 200662070448291
- **API version**: v25.0
- **Endpoint**: `GET /{page_id}/posts?fields=id,message,created_time,full_picture,permalink_url`
- **Note**: `type` and `attachments` fields deprecated in Graph API v3.3+
- **Permissions**: `pages_show_list`, `pages_read_engagement`, `pages_read_user_content`
- **Secrets** (GitHub Actions): `FB_PAGE_TOKEN`, `FB_PAGE_ID`

## Footer info (from live site, Winter 2026)

- Location: 23631 TR 167, Fresno, Ohio
- Phone: (740) 693-5050
- Hours: Wed & Th 4-9pm, Fri 1-9pm, Sat 12-9pm, Sun 12-7pm, Mon-Tue closed
- Instagram: instagram.com/woolypigfarmbrewery
- Facebook: facebook.com/woolypigbrewery

## Related projects

- `C:\Users\rob\Documents\claude\pub\` -- Columbus Science Pub project with similar automation patterns
  - `ticket-sales-viz/live_scraper.py` -- reference for scripting style (config block, function-per-concern, requests.Session)
  - `CLAUDE.md` lines 62-73 -- GitHub Pages custom domain setup notes (DNS TTL strategy, HTTPS provisioning)
- `C:\Users\rob\Documents\python learning files\evansrc2\` -- Hugo site on GitHub Pages (reference for Actions workflow)

## Working preferences

- Follow the scripting patterns from `pub/ticket-sales-viz/live_scraper.py`: config constants at top, `_SCRIPT_DIR` for path resolution, function-per-concern, explicit error handling
- No frameworks, no build steps. Plain HTML + CSS + Python.
- Windows development environment (paths use backslashes locally, but scripts should work cross-platform for GitHub Actions on ubuntu)

## Plan file

Full implementation plan is at: `C:\Users\rob\.claude\plans\expressive-whistling-whistle.md`
