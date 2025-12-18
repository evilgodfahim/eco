import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json
import time

# ------------------------------
# CONFIGURATION
# ------------------------------
FLARESOLVERR_URL = "http://localhost:8191/v1"
ARCHIVE_PREFIX = "https://archive.is/o/nuunc/"
MAX_ITEMS = 500
PER_FEED_LIMIT = 10

rss_feeds = [
    "https://www.economist.com/briefing/rss.xml",
    "https://www.economist.com/the-economist-explains/rss.xml",
    "https://www.economist.com/leaders/rss.xml",
    "https://www.economist.com/asia/rss.xml",
    "https://www.economist.com/china/rss.xml",
    "https://www.economist.com/international/rss.xml",
    "https://www.economist.com/united-states/rss.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://www.economist.com/the-world-this-week/rss.xml",
    "https://www.economist.com/science-and-technology/rss.xml",
    "https://www.economist.com/europe/rss.xml",
    "https://www.economist.com/business/rss.xml",
    "https://www.economist.com/graphic-detail/rss.xml",
    "https://www.economist.com/rss/middle_east_and_africa_rss.xml",
    "https://www.economist.com/the-americas/rss.xml"
]

# ------------------------------
# FLARESOLVERR FETCH
# ------------------------------
def fetch_html_via_flaresolverr(url):
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000
    }

    r = requests.post(
        FLARESOLVERR_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload)
    )
    r.raise_for_status()
    data = r.json()
    return data["solution"]["response"]

# ------------------------------
# ARTICLE TEXT EXTRACTION
# ------------------------------
def extract_article_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    section = soup.find("section")
    if not section:
        return ""

    paragraphs = section.find_all(
        "div",
        style=lambda x: x and "line-height: 28px" in x
    )

    full_text = ""
    for p in paragraphs:
        full_text += p.get_text(separator=" ", strip=True) + "\n\n"

    return full_text.strip()

# ------------------------------
# RSS ITEM FETCH
# ------------------------------
def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    all_items = []

    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        count = 0

        for entry in feed.entries:
            if count >= per_feed_limit:
                break

            if not hasattr(entry, "link"):
                continue

            original_link = entry.link
            archive_link = ARCHIVE_PREFIX + original_link

            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url")

            try:
                html = fetch_html_via_flaresolverr(archive_link)
                article_text = extract_article_text(html)
            except Exception:
                article_text = ""

            all_items.append({
                "title": entry.title,
                "link": archive_link,
                "description": article_text,
                "pubDate": entry.get(
                    "published",
                    datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
                ),
                "image": image_url
            })

            count += 1
            time.sleep(1)

    all_items.sort(
        key=lambda x: datetime.strptime(
            x["pubDate"], "%a, %d %b %Y %H:%M:%S +0000"
        ),
        reverse=True
    )

    return all_items[:MAX_ITEMS]

# ------------------------------
# RSS XML CREATION
# ------------------------------
def create_rss(items):
    rss = ET.Element(
        "rss",
        version="2.0",
        attrib={"xmlns:media": "http://search.yahoo.com/mrss/"}
    )

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = (
        "Combined Economist feed with full article text fetched via FlareSolverr"
    )

    for item in items:
        i = ET.SubElement(channel, "item")
        ET.SubElement(i, "title").text = item["title"]
        ET.SubElement(i, "link").text = item["link"]
        ET.SubElement(i, "description").text = item["description"]
        ET.SubElement(i, "pubDate").text = item["pubDate"]

        if item["image"]:
            ET.SubElement(
                i,
                "enclosure",
                url=item["image"],
                type="image/jpeg"
            )
            ET.SubElement(
                i,
                "media:content",
                url=item["image"],
                medium="image"
            )

    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)

# ------------------------------
# MAIN
# ------------------------------
if __name__ == "__main__":
    items = fetch_items(rss_feeds)
    rss_xml = create_rss(items)

    with open("combined.xml", "wb") as f:
        f.write(rss_xml)

    print("Combined RSS feed created with FlareSolverr-rendered full text and per-feed limit applied.")
