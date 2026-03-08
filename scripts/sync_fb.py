"""
v260308
Sync Facebook posts from Wooly Pig Farm Brewery's page to a static HTML site.

Fetches posts via Graph API, downloads images, renders branded HTML, and
copies static assets to docs/ for GitHub Pages deployment.

Designed to run as a GitHub Action (every 6h) or locally for testing.

Usage:
    FB_PAGE_TOKEN=xxx FB_PAGE_ID=yyy python scripts/sync_fb.py
"""

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────

FB_PAGE_TOKEN = os.environ.get('FB_PAGE_TOKEN', '')
FB_PAGE_ID = os.environ.get('FB_PAGE_ID', '')
FB_API_VERSION = 'v21.0'
FB_API_BASE = 'https://graph.facebook.com/{}'.format(FB_API_VERSION)

MAX_POSTS = 30
POST_FETCH_LIMIT = 50

SITE_URL = 'https://feed.woolypigfarmbrewery.com'
SITE_TITLE = 'Wooly Pig Farm Brewery - Feed'
SITE_DESCRIPTION = (
    'Latest posts from Wooly Pig Farm Brewery in Fresno, Ohio. '
    'Craft beer, farm life, events, and food trucks.'
)

HOURS = [
    ('Wed. & Th.', '4-9pm'),
    ('Friday', '1-9pm'),
    ('Saturday', '12-9pm'),
    ('Sunday', '12-7pm'),
    ('Mon-Tuesday', 'closed'),
]
HOURS_SEASON = 'Winter 2026'

# Resolve paths relative to the repo root (one level up from scripts/)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.dirname(_SCRIPT_DIR)
DOCS_DIR = os.path.join(_REPO_DIR, 'docs')
IMAGES_DIR = os.path.join(DOCS_DIR, 'images')
STATIC_DIR = os.path.join(_REPO_DIR, 'static')
POSTS_JSON = os.path.join(_REPO_DIR, 'posts.json')


# ──────────────────────────────────────────────────────────────────────
# FACEBOOK API
# ──────────────────────────────────────────────────────────────────────

def fetch_posts(session):
    # type: (requests.Session) -> Optional[List[Dict[str, Any]]]
    """Fetch recent posts from the Facebook Page via Graph API."""
    if not FB_PAGE_TOKEN or not FB_PAGE_ID:
        print("ERROR: FB_PAGE_TOKEN and FB_PAGE_ID must be set")
        return None

    url = '{}/{}/posts'.format(FB_API_BASE, FB_PAGE_ID)
    params = {
        'fields': (
            'id,message,created_time,full_picture,permalink_url,'
            'type,attachments{media,type,url,title,description,subattachments}'
        ),
        'limit': POST_FETCH_LIMIT,
        'access_token': FB_PAGE_TOKEN,
    }

    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'error' in data:
            code = data['error'].get('code', 0)
            msg = data['error'].get('message', 'Unknown error')
            print("FB API error (code {}): {}".format(code, msg))
            if code == 190:
                print("AUTH ERROR: Token is invalid or expired. "
                      "Re-generate and update the FB_PAGE_TOKEN secret.")
            return None

        posts = data.get('data', [])
        print("Fetched {} posts from Facebook".format(len(posts)))
        return posts

    except requests.exceptions.RequestException as e:
        print("Error fetching posts: {}".format(e))
        return None


# ──────────────────────────────────────────────────────────────────────
# IMAGE DOWNLOADS
# ──────────────────────────────────────────────────────────────────────

def image_filename(url):
    # type: (str) -> str
    """Generate a stable filename from the image URL using content hash."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    ext = '.jpg'
    if '.png' in url.lower():
        ext = '.png'
    elif '.gif' in url.lower():
        ext = '.gif'
    return 'fb_{}{}'.format(url_hash, ext)


def download_image(session, url, dest_path):
    # type: (requests.Session, str, str) -> bool
    """Download an image if it doesn't already exist."""
    if os.path.exists(dest_path):
        return True
    try:
        response = session.get(url, timeout=30, stream=True)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print("Error downloading image {}: {}".format(url, e))
        return False


def download_post_images(session, posts):
    # type: (requests.Session, List[Dict]) -> None
    """Download images for all posts that have them."""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    downloaded = 0
    for post in posts:
        img_url = post.get('full_picture')
        if not img_url:
            continue
        fname = image_filename(img_url)
        dest = os.path.join(IMAGES_DIR, fname)
        if download_image(session, img_url, dest):
            post['_local_image'] = 'images/{}'.format(fname)
            downloaded += 1
    print("Downloaded/verified {} images".format(downloaded))


# ──────────────────────────────────────────────────────────────────────
# POST CACHE
# ──────────────────────────────────────────────────────────────────────

def load_cached_posts():
    # type: () -> List[Dict]
    try:
        if os.path.exists(POSTS_JSON):
            with open(POSTS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print("Error loading cached posts: {}".format(e))
    return []


def save_cached_posts(posts):
    # type: (List[Dict]) -> None
    try:
        with open(POSTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        print("Saved {} posts to cache".format(len(posts)))
    except Exception as e:
        print("Error saving cached posts: {}".format(e))


def merge_posts(new_posts, cached_posts):
    # type: (List[Dict], List[Dict]) -> List[Dict]
    """Merge new posts with cache, dedup by id, sort newest first, trim."""
    by_id = {}
    for post in cached_posts:
        by_id[post['id']] = post
    for post in new_posts:
        by_id[post['id']] = post

    merged = sorted(
        by_id.values(),
        key=lambda p: p.get('created_time', ''),
        reverse=True,
    )
    return merged[:MAX_POSTS]


# ──────────────────────────────────────────────────────────────────────
# HTML RENDERING
# ──────────────────────────────────────────────────────────────────────

def format_date(iso_str):
    # type: (str) -> str
    """Format ISO datetime to a readable date string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%B %d, %Y')
    except Exception:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def format_timestamp(dt):
    # type: (datetime) -> str
    return dt.strftime('%B %d, %Y at %I:%M %p UTC')


def escape_html(text):
    # type: (str) -> str
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def is_video_post(post):
    # type: (Dict) -> bool
    post_type = post.get('type', '')
    if post_type == 'video':
        return True
    attachments = post.get('attachments', {}).get('data', [])
    for att in attachments:
        if att.get('type') in ('video_inline', 'video_autoplay', 'video'):
            return True
    return False


def render_post_card(post):
    # type: (Dict) -> str
    """Render a single post card as HTML."""
    message = post.get('message', '')
    image_path = post.get('_local_image', '')
    permalink = post.get('permalink_url', '#')
    created = post.get('created_time', '')
    date_str = format_date(created)
    video = is_video_post(post)

    has_image = bool(image_path)
    has_text = bool(message.strip())

    # Determine card class
    card_class = 'post-card'
    if not has_image and has_text:
        card_class += ' post-card--text-only'

    parts = []
    parts.append('<article class="{}">'.format(card_class))

    # Image section
    if has_image:
        if video:
            parts.append('  <div class="post-card-image-wrapper">')
            parts.append('    <img class="post-card-image" src="{}" alt="{}" loading="lazy">'.format(
                escape_html(image_path),
                escape_html(message[:80]) if has_text else 'Post from Wooly Pig Farm Brewery',
            ))
            parts.append('    <span class="video-badge">Watch on Facebook</span>')
            parts.append('  </div>')
        else:
            parts.append('  <img class="post-card-image" src="{}" alt="{}" loading="lazy">'.format(
                escape_html(image_path),
                escape_html(message[:80]) if has_text else 'Post from Wooly Pig Farm Brewery',
            ))

    # Body section
    parts.append('  <div class="post-card-body">')
    if has_text:
        parts.append('    <p class="post-card-text">{}</p>'.format(escape_html(message)))
    parts.append('    <div class="post-card-meta">')
    parts.append('      <time class="post-card-date" datetime="{}">{}</time>'.format(
        escape_html(created), escape_html(date_str),
    ))
    parts.append('      <a class="post-card-link" href="{}" target="_blank" rel="noopener">View on Facebook</a>'.format(
        escape_html(permalink),
    ))
    parts.append('    </div>')
    parts.append('  </div>')
    parts.append('</article>')

    return '\n'.join(parts)


def render_nav():
    # type: () -> str
    """Render the navigation bar matching the main site."""
    base = 'https://www.woolypigfarmbrewery.com'
    links = [
        ('Our Brewery', '{}/our-brewery-1'.format(base)),
        ('Our Farm', '{}/'.format(base)),
        ('Our Beers', '{}/our-beers-1'.format(base)),
        ('Third Place', '{}/tasting-room'.format(base)),
        ('Events/Food Trucks', '{}/events-test'.format(base)),
        ('Feed', '#'),
        ('Visit Us', '{}/visit-us'.format(base)),
        ('FAQ/Contact', '{}/contact-us'.format(base)),
        ('Merch Store', 'https://wooly-pig-farm-brewery-co-101874.square.site/'),
        ('Gift Cards', 'https://squareup.com/gift/11TV5N7F7DFHA/order'),
        ('Pork Shop', 'https://wooly-pig-farm-brewery-co-2.square.site/'),
        ('Three Rivers Wine Trail', 'https://visitcoshocton.dotsondesignstudio.com/trwt.php'),
    ]
    items = []
    for label, href in links:
        if href == '#':
            items.append('<li><a href="{}" class="active">{}</a></li>'.format(
                SITE_URL, label))
        else:
            items.append('<li><a href="{}">{}</a></li>'.format(href, label))
    return '\n            '.join(items)


def render_hours():
    # type: () -> str
    lines = []
    for day, time in HOURS:
        if time == 'closed':
            lines.append('<p><em>{} {}</em></p>'.format(day, time))
        else:
            lines.append('<p><strong>{}</strong> {}</p>'.format(day, time))
    return '\n            '.join(lines)


def render_json_ld():
    # type: () -> str
    ld = {
        "@context": "https://schema.org",
        "@type": "Brewery",
        "name": "Wooly Pig Farm Brewery",
        "description": SITE_DESCRIPTION,
        "url": "https://www.woolypigfarmbrewery.com",
        "telephone": "(740) 693-5050",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "23631 TR 167",
            "addressLocality": "Fresno",
            "addressRegion": "OH",
            "addressCountry": "US",
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 40.2922,
            "longitude": -81.7351,
        },
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Wednesday", "opens": "16:00", "closes": "21:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Thursday", "opens": "16:00", "closes": "21:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Friday", "opens": "13:00", "closes": "21:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Saturday", "opens": "12:00", "closes": "21:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "Sunday", "opens": "12:00", "closes": "19:00"},
        ],
        "sameAs": [
            "https://www.facebook.com/woolypigbrewery/",
            "https://www.instagram.com/woolypigfarmbrewery/",
        ],
    }
    return json.dumps(ld, indent=2)


def render_page(posts, updated_at):
    # type: (List[Dict], datetime) -> str
    """Render the full HTML page."""
    post_cards = '\n\n        '.join(render_post_card(p) for p in posts)
    nav_items = render_nav()
    hours_html = render_hours()
    json_ld = render_json_ld()
    timestamp = format_timestamp(updated_at)

    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <link rel="canonical" href="{site_url}">

    <!-- Open Graph -->
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:url" content="{site_url}">
    <meta property="og:type" content="website">
    <meta property="og:image" content="{site_url}/logo.png">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Kameron:wght@400;700&family=Raleway:wght@400;500;600&display=swap" rel="stylesheet">

    <link rel="stylesheet" href="style.css">
    <link rel="icon" href="favicon.ico">

    <!-- Structured Data -->
    <script type="application/ld+json">
{json_ld}
    </script>
</head>
<body>

    <header class="site-header">
        <a href="https://www.woolypigfarmbrewery.com/" class="site-logo">
            <img src="logo.png" alt="Wooly Pig Farm Brewery" width="280" height="60">
        </a>
    </header>

    <nav class="site-nav" aria-label="Main navigation">
        <ul>
            {nav_items}
        </ul>
    </nav>

    <section class="page-title-section">
        <h1 class="page-title">Latest from the Farm</h1>
        <p class="page-subtitle">Posts from our Facebook page</p>
    </section>

    <main class="feed-container">
        <div class="feed-inner">
        {post_cards}
        </div>
    </main>

    <div class="pre-footer">
        <div class="social-links">
            <a href="https://www.instagram.com/woolypigfarmbrewery/" target="_blank" rel="noopener" class="social-link" aria-label="Instagram">
                <svg viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
            </a>
            <a href="https://www.facebook.com/woolypigbrewery/" target="_blank" rel="noopener" class="social-link" aria-label="Facebook">
                <svg viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385h-3.047v-3.47h3.047v-2.642c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953h-1.513c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385c5.737-.9 10.125-5.864 10.125-11.854z"/></svg>
            </a>
        </div>
    </div>

    <footer class="site-footer">
        <div class="footer-inner">
            <div class="footer-col footer-col--badges">
                <img src="pig-badge.png" alt="Wooly Pig Farm Brewery" class="footer-badge" width="140" height="140">
                <a href="http://ohiocraftbeer.org/" target="_blank" rel="noopener">
                    <img src="ohio-craft-beer.png" alt="Ohio Craft Beer" class="footer-badge footer-badge--square" width="120" height="78">
                </a>
            </div>

            <div class="footer-col">
                <h3>Location</h3>
                <p><a href="https://www.google.com/maps/dir//Wooly+Pig+Farm+Brewery,+Township+Road+167,+Fresno,+OH/" target="_blank" rel="noopener">23631 TR 167<br>Fresno, Ohio</a></p>
                <p><a href="tel:+17406935050">(740) 693-5050</a></p>
            </div>

            <div class="footer-col footer-hours">
                <h3>{hours_season} Hours:</h3>
                {hours_html}
            </div>
        </div>
    </footer>

    <div class="last-updated">
        Last updated {timestamp}
    </div>

</body>
</html>""".format(
        title=escape_html(SITE_TITLE),
        description=escape_html(SITE_DESCRIPTION),
        site_url=SITE_URL,
        json_ld=json_ld,
        nav_items=nav_items,
        post_cards=post_cards,
        hours_season=HOURS_SEASON,
        hours_html=hours_html,
        timestamp=escape_html(timestamp),
    )


# ──────────────────────────────────────────────────────────────────────
# SITEMAP
# ──────────────────────────────────────────────────────────────────────

def render_sitemap(updated_at):
    # type: (datetime) -> str
    date_str = updated_at.strftime('%Y-%m-%d')
    return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{}</loc>
    <lastmod>{}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>""".format(SITE_URL, date_str)


# ──────────────────────────────────────────────────────────────────────
# STATIC ASSETS
# ──────────────────────────────────────────────────────────────────────

def copy_static_assets():
    # type: () -> None
    """Copy static/ files into docs/ for GitHub Pages."""
    if not os.path.isdir(STATIC_DIR):
        print("Warning: static/ directory not found at {}".format(STATIC_DIR))
        return

    copied = 0
    for fname in os.listdir(STATIC_DIR):
        src = os.path.join(STATIC_DIR, fname)
        dst = os.path.join(DOCS_DIR, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied += 1
    print("Copied {} static assets to docs/".format(copied))


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────

def main():
    print("sync_fb.py | Starting at {}".format(datetime.now(timezone.utc).isoformat()))

    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    cached_posts = load_cached_posts()
    api_failed = False

    with requests.Session() as session:
        new_posts = fetch_posts(session)

        if new_posts is not None:
            posts = merge_posts(new_posts, cached_posts)
            download_post_images(session, posts)
            save_cached_posts(posts)
        else:
            api_failed = True
            posts = cached_posts
            print("Using {} cached posts (API unavailable)".format(len(posts)))
            # Still re-download images for any cached posts that need them
            if posts:
                download_post_images(session, posts)

    if not posts:
        print("ERROR: No posts available (API failed and no cache)")
        sys.exit(1)

    # Render HTML
    now = datetime.now(timezone.utc)
    html = render_page(posts, now)
    html_path = os.path.join(DOCS_DIR, 'index.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("Wrote {} ({} bytes)".format(html_path, len(html)))

    # Render sitemap
    sitemap = render_sitemap(now)
    sitemap_path = os.path.join(DOCS_DIR, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap)

    # Copy static assets
    copy_static_assets()

    # Ensure CNAME exists
    cname_path = os.path.join(DOCS_DIR, 'CNAME')
    if not os.path.exists(cname_path):
        with open(cname_path, 'w') as f:
            f.write('feed.woolypigfarmbrewery.com')

    print("Done. {} posts rendered.".format(len(posts)))

    if api_failed:
        print("WARNING: API was unavailable, used cached data.")
        sys.exit(1)


if __name__ == '__main__':
    main()
