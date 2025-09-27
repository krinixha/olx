"""
OLX Deals Monitor
-----------------
Scrapes OLX.in for new items (DDR4, DDR5, NVMe, Xeon, PowerEdge).
- Saves results into docs/index.html (for GitHub Pages).
- Sends email if new items are found.
- Always takes a screenshot after visiting OLX, saved in docs/.

"""

import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright

SEARCH_URLS = [
    "https://www.olx.in/items/q-ddr4/?isSearchCall=true",
    "https://www.olx.in/items/q-ddr5/?isSearchCall=true",
    "https://www.olx.in/items/q-nvme/?isSearchCall=true",
    "https://www.olx.in/items/q-xeon/?isSearchCall=true",
    "https://www.olx.in/items/q-poweredge/?isSearchCall=true",
]

SEEN_FILE = "seen.json"
DOCS_DIR = "docs"
HTML_FILE = os.path.join(DOCS_DIR, "index.html")

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

async def scrape_olx_page(context, url):
    print("Visiting", url)
    page = await context.new_page()
    results = []

    try:
        await page.goto(url, timeout=60000)

        # 🔹 Save screenshot immediately after loading
        ts = int(time.time())
        screenshot_name = f"screenshot_{ts}.png"
        screenshot_path = os.path.join(DOCS_DIR, screenshot_name)
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
            print("📸 Screenshot saved:", screenshot_path)
        except Exception as e:
            print("⚠️ Screenshot failed:", e)

        # Try scraping items
        await page.wait_for_selector('[data-aut-id="itemsList"]', timeout=20000)
        items = await page.query_selector_all('[data-aut-id="itemBox"]')

        for item in items:
            link = await item.query_selector("a")
            if link:
                href = await link.get_attribute("href")
                if href:
                    results.append("https://www.olx.in" + href)

    except Exception as e:
        print("Error scraping", url, e)

    finally:
        await page.close()

    return results

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-http2"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )

        seen = load_seen()
        all_new = []

        for url in SEARCH_URLS:
            items = await scrape_olx_page(context, url)
            for link in items:
                if link not in seen:
                    all_new.append(link)
                    seen.add(link)

        await browser.close()
        save_seen(seen)

        os.makedirs(DOCS_DIR, exist_ok=True)
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write("<html><head><title>OLX Deals Monitor</title></head><body>")
            f.write("<h1>OLX Deals Monitor</h1>")
            f.write("<p>Auto-updated: {}</p>".format(time.strftime("%Y-%m-%d %H:%M:%S")))

            f.write("<h2>New items ({})</h2>".format(len(all_new)))
            if all_new:
                f.write("<ul>")
                for link in all_new:
                    f.write(f"<li><a href='{link}' target='_blank'>{link}</a></li>")
                f.write("</ul>")
            else:
                f.write("<p>No new items in this run.</p>")

            f.write("<h2>All tracked items</h2><ul>")
            for link in seen:
                f.write(f"<li><a href='{link}' target='_blank'>{link}</a></li>")
            f.write("</ul></body></html>")

        if all_new:
            send_email(all_new)

def send_email(new_items):
    msg = MIMEMultipart()
    msg["From"] = os.environ.get("EMAIL_FROM")
    msg["To"] = os.environ.get("EMAIL_TO")
    msg["Subject"] = "New OLX Listings Found"

    body = "New OLX items:\n\n" + "\n".join(new_items)
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as server:
            server.starttls()
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            server.sendmail(msg["From"], [msg["To"]], msg.as_string())
            print("✅ Email sent successfully.")
    except Exception as e:
        print("⚠️ Failed to send email:", e)

if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
