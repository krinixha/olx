#!/usr/bin/env python3
for a in anchors:
try:
href = a.get_attribute("href")
txt = a.inner_text().strip()
except Exception:
continue
if not href or not txt:
continue
low = txt.lower()
if not any(k in low for k in KEYWORDS):
continue
if not href.startswith("http"):
href = "https://www.olx.in" + href
# small snippet: first 120 chars
snippet = txt[:160].replace("\n", " ")
items.append({"title": txt, "link": href, "snippet": snippet})
return items




def main():
ensure_docs_dir()
seen = load_seen()
all_found = [] # accumulate unique items (most recent first)
new_items = []
with sync_playwright() as p:
browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()
for url in SEARCH_URLS:
try:
items = scrape_olx_page(page, url)
except Exception as e:
print("Error scraping", url, e)
items = []
# append unique ones
for it in items:
if it["link"] not in {x['link'] for x in all_found}:
all_found.append(it)
if it["link"] not in seen:
new_items.append(it)
seen.add(it["link"])
time.sleep(2)
browser.close()


# generate site html
html = make_site_html(all_found, new_items) if False else make_site_html(all_found, new_items)
# save docs index
with open(DOCS_INDEX, "w", encoding="utf-8") as f:
f.write(html)


# Save seen
save_seen(seen)


# Send email only if there are new items
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
