# Wooly Pig Farm Brewery -- Facebook Content Sync Page

## What this project is

A GitHub Actions + GitHub Pages static site that syncs Facebook Page posts from Wooly Pig Farm Brewery's FB page to a branded web page at `feed.woolypigfarmbrewery.com`. The brewery's main site is on Squarespace (can't programmatically update), so this subdomain page mimics their branding while being independently hosted and SEO-indexable.

## Why it exists

Facebook stopped recommending places that sell alcohol. The brewery's primary content is on FB, so they need that content mirrored to a web page that search engines can find and index.

## Knowledge base (wiki)

Architecture details, Facebook token procedures, branding, incident write-ups, and decision history for this project live in the home wiki at `../wiki`. Start from `../wiki/pages/projects/wooly.md` (hub) or `../wiki/index.md`. Check it before re-deriving how something works. When a session produces a durable finding, offer to file it by following `../wiki/.claude/skills/wiki-ingest/SKILL.md` before the session ends.

## Architecture

- **GitHub Action** runs hourly at :15 (cron `15 * * * *`) + manual trigger
- **Python script** (`scripts/sync_fb.py`) fetches posts via Facebook Graph API, downloads images, generates static HTML
- **Output** goes to `docs/` folder, served by GitHub Pages
- **Custom domain**: `feed.woolypigfarmbrewery.com` via CNAME record in Squarespace DNS
- The Squarespace site's "FEED" nav link (currently empty page at woolypigfarmbrewery.com/feed) will be updated to point to this subdomain

## Key design decisions

See ../wiki/pages/systems/wooly-fb-sync.md and ../wiki/pages/decisions/wooly-history-squash.md. Before changing image handling, read ../wiki/pages/incidents/2026-08-14-wooly-image-bloat.md.

## Repo structure

```
wooly-page/
  .github/workflows/sync.yml       # Cron workflow (hourly at :15) + manual trigger
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

## Brewery branding

Colors and fonts (verified against static/style.css): ../wiki/pages/projects/wooly.md.

## Facebook API details

- **Secrets** (GitHub Actions): `FB_PAGE_TOKEN`, `FB_PAGE_ID`
- Page id, API version, fields, permissions, and token refresh (Rob is admin, not owner): ../wiki/pages/systems/wooly-fb-sync.md and ../wiki/pages/services/facebook-graph-api.md.

## Footer info

Footer facts: ../wiki/pages/projects/wooly.md.

## Related projects

- `C:\Users\rob\Documents\claude\pub\` -- Columbus Science Pub project with similar automation patterns
  - `ticket-sales-viz/live_scraper.py` -- reference for scripting style (config block, function-per-concern, requests.Session)
  - GitHub Pages custom domain setup (DNS TTL strategy, HTTPS provisioning): ../wiki/pages/services/github-pages-hugo.md
- `C:\Users\rob\Documents\python learning files\evansrc2\` -- Hugo site on GitHub Pages (reference for Actions workflow)

## Working preferences

- Follow the scripting patterns from `pub/ticket-sales-viz/live_scraper.py`: config constants at top, `_SCRIPT_DIR` for path resolution, function-per-concern, explicit error handling
- No frameworks, no build steps. Plain HTML + CSS + Python.
- Windows development environment (paths use backslashes locally, but scripts should work cross-platform for GitHub Actions on ubuntu)

## Plan file

Full implementation plan is at: `C:\Users\rob\.claude\plans\expressive-whistling-whistle.md`
