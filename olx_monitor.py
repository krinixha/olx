#!/usr/bin/env python3
"""
OLX Monitor (stealth-enabled)
-----------------------------
- Scrapes OLX.in search pages with Playwright
- Uses stealth techniques (random UA, locale, JS patches)
- Saves screenshots to docs/
- Writes docs/index.html and updates seen.json
- Sends email if new items found
"""

import os
import json
import time
import random
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

# Email from secrets
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Realistic User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
]
LOCALES = [("en-GB", "Europe/London"), ("en-IN", "Asia/Kolkata"), ("en-US", "America/Los_Angeles")]

STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""

# ---------- Helpers ----------
def load_seen():
    if Path(SEEN_FILE).exists():
        try:
            return set(json.load(open(SEEN_FILE)))
        except Exception:
            return set()
    return set()

def save_seen(seen):
    json.dump(sorted(list(seen)), open(SEEN_FILE, "w"), indent=2)

def send_email(new_items):
    if not (EMAIL_FROM and EMAIL_TO and SMTP_USER and SMTP_PASS):
        print("⚠ Email not configured, skipping.")
        return
    msg = MIMEMultipart("alternative")
    msg["From"], msg["To"] = EMAIL_FROM, EMAIL_TO
    msg["Subject"] = f"OLX Monitor — {len(new_items)} new items"
    htm
