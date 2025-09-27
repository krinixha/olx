import requests
import json
import os
from datetime import datetime

SEARCH_TERMS = ["ddr4", "ddr5", "nvme", "xeon", "poweredge"]
SEEN_FILE = "seen.json"
OUTPUT_FILE = "docs/index.html"


def fetch_olx(query):
    """Fetch ads for a query from OLX JSON API"""
    url = f"https://www.olx.in/api/relevance/v2/search?query={query}&limit=20&offset=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/115 Safari/537.36",
        "Referer": f"https://www.olx.in/items/q-{query}/?isSearchCall=true",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for ad in data.get("data", []):
            ad_id = ad.get("id")
            title = ad.get("title")
            price = ad.get("price", {}).get("value", {}).get("display", "N/A")
            link = "https://www.olx.in" + ad.get("url", "")
            items.append({"id": ad_id, "title": title, "price": price, "url": link})
        return items
    except Exception as e:
        print(f"Error fetching {query}: {e}")
        return []


def load_seen():
    """Load seen items from JSON"""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_seen(seen):
    """Save seen items"""
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def save_html(all_items, new_items):
    """Write HTML report for GitHub Pages"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='UTF-8'><title>OLX Deals Monitor</title></head><body>")
        f.write("<h1>OLX Deals Monitor</h1>")
        f.write(f"<p>Auto-updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")

        f.write(f"<h2>New items ({len(new_items)})</h2>")
        if new_items:
            f.write("<ul>")
            for item in new_items:
                f.write(
                    f"<li><a href='{item['url']}' target='_blank'>{item['title']}</a> "
                    f"- {item['price']}</li>"
                )
            f.write("</ul>")
        else:
            f.write("<p>No new items in this run.</p>")

        f.write("<h2>All tracked items</h2>")
        if all_items:
            f.write("<ul>")
            for item in all_items:
                f.write(
                    f"<li><a href='{item['url']}' target='_blank'>{item['title']}</a> "
                    f"- {item['price']}</li>"
                )
            f.write("</ul>")
        else:
            f.write("<p>No items found yet.</p>")

        f.write("</body></html>")


def main():
    seen = load_seen()
    seen_ids = set(item["id"] for item in seen)

    all_items = []
    new_items = []

    for term in SEARCH_TERMS:
        print(f"Fetching {term}...")
        items = fetch_olx(term)
        for item in items:
            all_items.append(item)
            if item["id"] not in seen_ids:
                new_items.append(item)

    if new_items:
        print(f"Found {len(new_items)} new items.")
        seen.extend(new_items)
        save_seen(seen)
    else:
        print("No new items.")

    save_html(all_items, new_items)


if __name__ == "__main__":
    main()
