#!/usr/bin/env python3
"""
OLX Playwright monitor:
- Writes site HTML to docs/index.html (for GitHub Pages)
- Persists seen items in seen.json (committed back to repo by the workflow)
- Sends email when new items found
- Saves a screenshot each run (docs/screenshot_<ts>.png) for debugging
"""

import os, json, time, smtplib, pathlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.sync_api import sync_playwright

# ========== CONFIG ==========
SEARCH_URLS = [
    "https://www.olx.in/items/q-ddr4/?isSearchCall=true",
    "https://www.olx.in/items/q-ddr5/?isSearchCall=true",
    "https://www.olx.in/items/q-nvme/?isSearchCall=true",
    "https://www.olx.in/items/q-xeon/?isSearchCall=true",
    "https://www.olx.in/items/q-poweredge/?isSearchCall=true",
]
KEYWORDS = ["ddr4", "ddr5", "nvme", "xeon", "poweredge"]
SEEN_FILE = "seen.json"
DOCS_INDEX = "docs/index.html"

# Email / SMTP from env
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO", "").split(",") if os.getenv("EMAIL_TO") else []
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Optional: title for the generated page
SITE_TITLE = os.getenv("SITE_TITLE", "OLX Deals Monitor")
# ============================


def ensure_docs_dir():
    pathlib.Path("docs").mkdir(exist_ok=True)


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            return set(json.load(open(SEEN_FILE, "r", encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    json.dump(sorted(list(seen)), open(SEEN_FILE, "w", encoding="utf-8"), indent=2)


def make_site_html(all_items, new_items):
    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{SITE_TITLE}</title>
<style>
body{{font-family:Inter,ui-sans-serif,system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; margin:18px; max-width:1000px}}
h1{{color:#0b57d0}}
.card{{padding:10px;border-radius:8px;border:1px solid #e6e6e6;margin-bottom:10px}}
.new{{background:#f0fff4;border-color:#b7f0c6}}
a{{color:#0b57d0;text-decoration:none}}
.small{{color:#666;font-size:0.9rem}}
</style>
</head>
<body>
<h1>{SITE_TITLE}</h1>
<p class="small">Auto-updated: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
<h2>New items ({len(new_items)})</h2>
"""
    new_html = ""
    if new_items:
        for it in new_items:
            new_html += f"""<div class="card new"><a href="{it['link']}" target="_blank"><strong>{it['title']}</strong></a>
<p class="small">{it.get('snippet','')}</p></div>"""
    else:
        new_html += "<p>No new items in this run.</p>"

    all_html = "<h2>All tracked items</h2>"
    if all_items:
        for it in all_items:
            all_html += f"""<div class="card"><a href="{it['link']}" target="_blank"><strong>{it['title']}</strong></a>
<p class="small">{it.get('snippet','')}</p></div>"""
    else:
        all_html += "<p>No items found yet.</p>"

    foot = "</body></html>"
    return head + new_html + all_html + foot


def send_email(new_items):
    if not EMAIL_FROM or not EMAIL_TO or not SMTP_USER or not SMTP_PASS:
        print("Email not configured (missing env). Skipping email.")
        return
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(EMAIL_TO)
    msg["Subject"] = f"OLX Monitor — {len(new_items)} new item(s)"
    body = "<h2>New OLX items</h2><ul>"
    for i in new_items:
        body += f"<li><a href='{i['link']}'>{i['title']}</a></li>"
    body += "</ul>"
    msg.attach(MIMEText(body, "html"))
    s = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    s.starttls()
    s.login(SMTP_USER, SMTP_PASS)
    s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    s.quit()


def scrape_olx_page(page, url):
    print("Visiting", url)
    try:
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_selector("div[data-aut-id='itemsList']", timeout=20000)
    except Exception as e:
        print("⚠️ Failed to load items on", url, e)

        # Save screenshot anyway
        ts = int(time.time())
        screenshot_path = f"docs/screenshot_fail_{ts}.png"
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            print("📸 Saved fail screenshot to", screenshot_path)
        except Exception as ee:
            print("⚠️ Could not save screenshot:", ee)

        return []

    items = []
    cards = page.query_selector_all("a[data-aut-id='itemBox']")

    for c in cards:
        try:
            href = c.get_attribute("href")
            title = c.inner_text().strip()
        except Exception:
            continue

        if not href or not title:
            continue

        low = title.lower()
        if not any(k in low for k in KEYWORDS):
            continue

        if not href.startswith("http"):
            href = "https://www.olx.in" + href

        snippet = title[:160].replace("\n", " ")
        items.append({"title": title, "link": href, "snippet": snippet})

    # Save screenshot of successful page load
    ts = int(time.time())
    screenshot_path = f"docs/screenshot_{ts}.png"
    try:
        page.screenshot(path=screenshot_path, full_page=True)
        print("📸 Saved screenshot to", screenshot_path)
    except Exception as e:
        print("⚠️ Could not save screenshot:", e)

    print(f"✅ Found {len(items)} items on {url}")
    return items


def main():
    ensure_docs_dir()
    seen = load_seen()
    all_found = []
    new_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-http2"]
        )
        page = browser.new_page()
        for url in SEARCH_URLS:
            try:
                items = scrape_olx_page(page, url)
            except Exception as e:
                print("Error scraping", url, e)
                items = []
            for it in items:
                if it["link"] not in {x['link'] for x in all_found}:
                    all_found.append(it)
                if it["link"] not in seen:
                    new_items.append(it)
                    seen.add(it["link"])
            time.sleep(2)
        browser.close()

    html = make_site_html(all_found, new_items)
    with open(DOCS_INDEX, "w", encoding="utf-8") as f:
        f.write(html)

    save_seen(seen)

    if new_items:
        try:
            send_email(new_items)
            print(f"Sent email for {len(new_items)} new item(s)")
        except Exception as e:
            print("Failed to send email:", e)
    else:
        print("No new items found.")


if __name__ == "__main__":
    main()
