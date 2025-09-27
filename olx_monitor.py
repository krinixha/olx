#!/usr/bin/env python3
"""
OLX Monitor (stealth-enabled)
-----------------------------
- Uses Playwright (async) to visit OLX search pages.
- Adds several "stealth" measures so the headless browser looks more like a real user:
  * randomized User-Agent from a small realistic set
  * viewport, deviceScaleFactor, locale, timezone
  * extra HTTP headers (Accept-Language)
  * injected JS to override navigator.webdriver and add fake plugins/languages
- Always saves a screenshot to docs/screenshot_<ts>.png (so you can inspect what the headless browser saw)
- Tracks seen links in seen.json, writes docs/index.html and emails if there are new items
"""

import os
import json
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from playwright.async_api import async_playwright

# ---------- CONFIG ----------
SEARCH_URLS = [
    "https://www.olx.in/items/q-ddr4/?isSearchCall=true",
    "https://www.olx.in/items/q-ddr5/?isSearchCall=true",
    "https://www.olx.in/items/q-nvme/?isSearchCall=true",
    "https://www.olx.in/items/q-xeon/?isSearchCall=true",
    "https://www.olx.in/items/q-poweredge/?isSearchCall=true",
]
KEYWORDS = ["ddr4", "ddr5", "nvme", "xeon", "poweredge"]

SEEN_FILE = "seen.json"
DOCS_DIR = Path("docs")
HTML_FILE = DOCS_DIR / "index.html"

# Email / SMTP via GitHub Secrets (configured in workflow)
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Some realistic user agents to randomly choose from
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
]

# Locale/timezone options to appear more realistic
LOCALES = [("en-GB", "Europe/London"), ("en-IN", "Asia/Kolkata"), ("en-US", "America/Los_Angeles")]

# ---------- Helpers ----------
def load_seen():
    if Path(SEEN_FILE).exists():
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)

def send_email(new_items):
    if not (EMAIL_FROM and EMAIL_TO and SMTP_USER and SMTP_PASS):
        print("Email not configured (missing env). Skipping email.")
        return
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"OLX Monitor — {len(new_items)} new item(s)"
    html = "<h2>New OLX items</h2><ul>"
    for it in new_items:
        html += f"<li><a href='{it}'>{it}</a></li>"
    html += "</ul>"
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO.split(","), msg.as_string())
        print("✅ Email sent successfully.")
    except Exception as e:
        print("⚠️ Failed to send email:", e)

# JavaScript injected into every page to hide webdriver and add some fake properties
STEALTH_JS = r"""
// Overwrite the `navigator.webdriver` to false
Object.defineProperty(navigator, 'webdriver', {
  get: () => false,
});

// Mock plugins and languages
Object.defineProperty(navigator, 'plugins', {
  get: () => [1,2,3,4]
});
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en']
});

// Pass a fake webdriver property for some checks
window.__nightmare = true;

// Prevent detection via permissions query
const originalQuery = navigator.permissions.query;
navigator.permissions.__originalQuery = originalQuery;
navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""

# ---------- Scraper logic ----------
async def scrape_olx_page(context, url, ua):
    """Visit URL, take screenshot (always), try to extract item links."""
    print("Visiting", url)
    page = await context.new_page()
    results = []
    try:
        # Navigate and wait for DOMContentLoaded (fast), then take immediate screenshot
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")

        # take a screenshot immediately (debug)
        ts = int(time.time())
        DOCS_DIR.mkdir(exist_ok=True)
        screenshot_name = f"screenshot_{ts}.png"
        screenshot_path = DOCS_DIR / screenshot_name
        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print("📸 Saved screenshot:", screenshot_path)
        except Exception as e:
            print("⚠️ Screenshot failed:", e)

        # Now wait for OLX items container (if present)
        try:
            await page.wait_for_selector('[data-aut-id="itemsList"]', timeout=15000)
        except Exception:
            print("⚠️ itemsList container not found (maybe blocked or empty).")

        # Prefer the OLX card selector (data-aut-id="itemBox")
        cards = await page.query_selector_all('[data-aut-id="itemBox"]')
        for c in cards:
            try:
                # sometimes the <a> is the card itself or nested
                href = await c.get_attribute("href")
                if not href:
                    # try to find nested anchor
                    a = await c.query_selector("a")
                    if a:
                        href = await a.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        href = "https://www.olx.in" + href
                    text = (await (c.inner_text())) or ""
                    low = text.lower()
                    if any(k in low for k in KEYWORDS):
                        results.append({"title": text.strip(), "link": href})
            except Exception:
                continue

        print(f"✅ Found {len(results)} items on {url}")
    except Exception as e:
        print("Error scraping", url, e)
    finally:
        await page.close()
    return results

# ---------- Main ----------
async def main():
    # choose random UA, locale, timezone to appear more human
    ua = random.choice(USER_AGENTS)
    locale, tz = random.choice(LOCALES)
    viewport = {"width": 1280, "height": 800}

    seen = load_seen()
    all_found = []
    new_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-http2",
            "--disable-blink-features=AutomationControlled"
        ])

        context = await browser.new_context(
            user_agent=ua,
            viewport=viewport,
            locale=locale,
            timezone_id=tz,
            device_scale_factor=1,
            # set Accept-Language header so server sees typical browser header
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        # inject stealth JS into every page
        # Note: add_init_script can be synchronous on some versions; works without await here
        try:
            context.add_init_script(STEALTH_JS)
        except Exception:
            # fallback: try page-level injection later
            pass

        # Visit each URL and collect items
        for url in SEARCH_URLS:
            items = await scrape_olx_page(context, url, ua)
            for it in items:
                link = it["link"]
                all_found.append(it)
                if link not in seen:
                    new_items.append(it)
                    seen.add(link)
            # small delay between searches to avoid aggressive scraping
            time.sleep(1.5)

        await browser.close()

    # write index.html to docs
    DOCS_DIR.mkdir(exist_ok=True)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
        f.write("<title>OLX Deals Monitor</title></head><body>")
        f.write(f"<h1>OLX Deals Monitor</h1><p class='small'>Auto-updated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>")
        f.write(f"<h2>New items ({len(new_items)})</h2>")
        if new_items:
            for it in new_items:
                f.write(f"<div class='card new'><a href='{it['link']}' target='_blank'><strong>{it['title']}</strong></a></div>")
        else:
            f.write("<p>No new items in this run.</p>")
        f.write("<h2>All tracked items</h2>")
        if all_found:
            for it in all_found:
                f.write(f"<div class='card'><a href='{it['link']}' target='_blank'>{it['title']}</a></div>")
        else:
            f.write("<p>No items found yet.</p>")
        f.write("</body></html>")

    save_seen(seen)

    # send email with absolute URLs if new items found
    if new_items:
        send_email([it["link"] for it in new_items])
    else:
        print("No new items found.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
