import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime

# RSS feed URLs
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

ARCHIVE_PREFIX = "https://archive.is/o/nuunc/"

def fetch_items(feed_urls):
    all_items = []
    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if not hasattr(entry, "link"):
                continue
            original_link = entry.link
            archive_link = ARCHIVE_PREFIX + original_link
            all_items.append({
                "title": entry.title,
                "link": archive_link,
                "description": entry.get("description", ""),
                "pubDate": entry.get("published", datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
            })
    return all_items

def create_rss(items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined feed of multiple Economist RSS sources with archive.is/o/nuunc links"

    for item in items:
        i = ET.SubElement(channel, "item")
        ET.SubElement(i, "title").text = item["title"]
        ET.SubElement(i, "link").text = item["link"]
        ET.SubElement(i, "description").text = item["description"]
        ET.SubElement(i, "pubDate").text = item["pubDate"]

    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    items = fetch_items(rss_feeds)
    rss_xml = create_rss(items)
    with open("combined.xml", "wb") as f:
        f.write(rss_xml)
    print("Combined RSS feed created successfully.")