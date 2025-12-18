import feedparser
from datetime import datetime
import re

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

def escape_xml(text):
    """Escape special XML characters"""
    if not text:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text

def extract_image(entry):
    """Extract image from multiple possible sources in feed entry"""
    # Try media:content
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if "url" in media:
                return media["url"]

    # Try media:thumbnail
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            if "url" in thumb:
                return thumb["url"]

    # Try enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("url", "")

    # Try parsing HTML content for images
    content = ""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        content = entry.summary
    elif hasattr(entry, "description"):
        content = entry.description

    if content:
        # Look for img tags
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
        if img_match:
            return img_match.group(1)

    return None

def fetch_items(feed_urls):
    all_items = []
    images_found = 0
    
    for feed_url in feed_urls:
        print(f"Fetching: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                if not hasattr(entry, "link"):
                    continue

                original_link = entry.link
                archive_link = ARCHIVE_PREFIX + original_link

                # Extract image
                image_url = extract_image(entry)
                if image_url:
                    images_found += 1
                    print(f"  📸 Image found: {image_url[:60]}...")

                all_items.append({
                    "title": entry.title,
                    "link": archive_link,
                    "description": entry.get("description", ""),
                    "pubDate": entry.get(
                        "published",
                        datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
                    ),
                    "image": image_url
                })
        except Exception as e:
            print(f"  ❌ Error: {e}")

    # Sort by date
    all_items.sort(
        key=lambda x: datetime.strptime(
            x["pubDate"], "%a, %d %b %Y %H:%M:%S +0000"
        ),
        reverse=True
    )
    
    limited_items = all_items[:500]
    print(f"\n✅ Total items: {len(limited_items)}")
    print(f"📸 Items with images: {sum(1 for i in limited_items if i['image'])}")
    
    return limited_items

def create_rss(items):
    """Create RSS XML manually to avoid namespace issues"""
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">')
    xml_lines.append('  <channel>')
    xml_lines.append('    <title>Combined Economist RSS Feed</title>')
    xml_lines.append('    <link>https://yourusername.github.io/combined.xml</link>')
    xml_lines.append('    <description>Combined feed of multiple Economist RSS sources with archive.is/o/nuunc links</description>')

    for item in items:
        xml_lines.append('    <item>')
        xml_lines.append(f'      <title>{escape_xml(item["title"])}</title>')
        xml_lines.append(f'      <link>{escape_xml(item["link"])}</link>')
        xml_lines.append(f'      <description>{escape_xml(item["description"])}</description>')
        xml_lines.append(f'      <pubDate>{item["pubDate"]}</pubDate>')

        # Add image if available
        if item["image"]:
            xml_lines.append(f'      <media:thumbnail url="{escape_xml(item["image"])}" />')
            xml_lines.append(f'      <media:content url="{escape_xml(item["image"])}" medium="image" />')
            xml_lines.append(f'      <enclosure url="{escape_xml(item["image"])}" type="image/jpeg" />')

        xml_lines.append('    </item>')

    xml_lines.append('  </channel>')
    xml_lines.append('</rss>')

    return '\n'.join(xml_lines)

if __name__ == "__main__":
    print("=" * 70)
    print("Economist RSS Feed Aggregator with Images")
    print("=" * 70)
    
    items = fetch_items(rss_feeds)
    rss_xml = create_rss(items)
    
    with open("combined.xml", "w", encoding="utf-8") as f:
        f.write(rss_xml)
    
    print("\n✅ Combined RSS feed created successfully (combined.xml)")
    print("=" * 70)