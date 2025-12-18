import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium_recaptcha_solver import RecaptchaSolver
from bs4 import BeautifulSoup
import time

# ------------------------------
# CONFIGURATION
# ------------------------------
PER_FEED_LIMIT = 10
MAX_ITEMS = 500
ARCHIVE_PREFIX = "https://archive.is/o/nuunc/"
RSS_FEEDS = [
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
# SELENIUM + RECAPTCHA SETUP
# ------------------------------

def create_webdriver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=options)

def fetch_html_with_selenium(driver, url, timeout=30):
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        time.sleep(2)  # let page script settle
    except TimeoutException:
        pass
    return driver.page_source

# ------------------------------
# ARTICLE TEXT EXTRACTION
# ------------------------------
def extract_article_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    section = soup.find("section")
    if not section:
        return ""
    paragraphs = []
    for div in section.find_all("div", style=True):
        style = div.get("style") or ""
        norm = style.replace(" ", "").lower()
        if "line-height:28px" in norm and "display:none" not in norm:
            if div.find("figcaption") is None:
                text = div.get_text(separator=" ", strip=True)
                if text:
                    paragraphs.append(text)
    return "\n\n".join(paragraphs).strip()

# ------------------------------
# DATE PARSING
# ------------------------------
def parse_pubdate(entry):
    published = entry.get("published") or entry.get("updated") or ""
    if published:
        try:
            dt = parsedate_to_datetime(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return datetime.now(timezone.utc)

# ------------------------------
# FETCH ITEMS
# ------------------------------
def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    items = []
    driver = create_webdriver()
    solver = RecaptchaSolver(driver=driver)

    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        count = 0

        for entry in feed.entries:
            if count >= per_feed_limit:
                break

            original_link = entry.get("link")
            if not original_link:
                continue

            try:
                html_data = fetch_html_with_selenium(driver, original_link)
                text = extract_article_text(html_data)
            except Exception:
                text = ""

            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url")

            pub_dt = parse_pubdate(entry)
            items.append({
                "title": entry.get("title", "").strip(),
                "link": ARCHIVE_PREFIX + original_link,
                "description": text,
                "pub_dt": pub_dt,
                "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000"),
                "image": image_url
            })

            count += 1
            time.sleep(1)

    try:
        driver.quit()
    except Exception:
        pass

    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

# ------------------------------
# CREATE RSS
# ------------------------------
def create_rss(items, outpath="combined.xml"):
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:media": "http://search.yahoo.com/mrss/"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined feed with full text via Selenium"

    for it in items:
        i = ET.SubElement(channel, "item")
        ET.SubElement(i, "title").text = it["title"]
        ET.SubElement(i, "link").text = it["link"]
        ET.SubElement(i, "description").text = it["description"]
        ET.SubElement(i, "pubDate").text = it["pubDate"]
        if it["image"]:
            ET.SubElement(i, "enclosure", url=it["image"], type="image/jpeg")
            ET.SubElement(i, "media:content", url=it["image"], medium="image")

    xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    with open(outpath, "wb") as f:
        f.write(xml_bytes)

# ------------------------------
# MAIN
# ------------------------------
if __name__ == "__main__":
    items = fetch_items(RSS_FEEDS)
    create_rss(items)
    print("combined.xml written")
