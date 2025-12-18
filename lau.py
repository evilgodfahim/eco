import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from selenium_recaptcha_solver import Browser
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
import time

# CONFIG
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

# Exact XPath you provided (primary selector)
PRIMARY_XPATH = (
    "/html/body/center/div[4]/div/div[1]/div/div/div[1]/div/div/div[3]/"
    "div/main/article/div/div[1]/div[3]/div/section/div"
)

# Initialize headless browser once, reuse for all requests
browser = Browser(driver_type="chrome", headless=True, expose_driver=True)

def fetch_page_node_html(url, xpath=PRIMARY_XPATH, wait_s=2, timeout=30):
    """
    Visit `url`. Try to locate node by XPath and return its outerHTML.
    If XPath fails, return full page_source for fallback parsing.
    """
    try:
        browser.driver.set_page_load_timeout(timeout)
        browser.visit(url)
    except (TimeoutException, WebDriverException):
        # proceed with whatever loaded; do not crash
        pass

    time.sleep(wait_s)  # let JS run and content settle

    # try XPath first (precise)
    try:
        node = browser.driver.find_element(By.XPATH, xpath)
        html_fragment = node.get_attribute("outerHTML")
        if html_fragment and html_fragment.strip():
            return html_fragment
    except (NoSuchElementException, WebDriverException):
        pass

    # fallback: try to extract the <section> from full page
    try:
        page = browser.driver.page_source
        return page
    except WebDriverException:
        return ""

def extract_article_text_from_html(html_content):
    """
    Prefer HTML fragments from XPath; if full page passed, find <section>.
    Extract <div> elements with 'line-height: 28px', skip hidden and figcaption.
    Return cleaned paragraphs joined by double newlines.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # If the provided html_content is a full page, find the main <section>
    # If html_content already is the fragment from the XPath, it will contain the section/divs directly.
    section = None
    if soup.find("section"):
        section = soup.find("section")
    else:
        # look for a likely article container if no section found
        # keep original soup (it might already be the fragment)
        section = soup

    paragraphs = []
    for div in section.find_all("div", style=True):
        style = div.get("style") or ""
        style_norm = style.replace(" ", "").lower()
        # require line-height close to 28px and exclude hidden/display:none
        if "line-height:28px" in style_norm and "display:none" not in style_norm:
            # skip figcaption-containing containers
            if div.find("figcaption"):
                continue
            text = div.get_text(separator=" ", strip=True)
            if text:
                paragraphs.append(text)

    # If no paragraphs found with precise filter, attempt a more permissive fallback:
    if not paragraphs:
        # find all divs inside section that contain text and have CSS-like line-height mention
        for div in section.find_all("div"):
            text = div.get_text(separator=" ", strip=True)
            if not text:
                continue
            style = div.get("style") or ""
            if "display:none" in style.replace(" ", "").lower():
                continue
            # accept divs with line-height:24px or 28px or those inside article > section
            if "line-height:28px" in style.replace(" ", "").lower() or "line-height:24px" in style.replace(" ", "").lower() or div.find_parent("article"):
                if div.find("figcaption"):
                    continue
                paragraphs.append(text)

    # final clean: deduplicate consecutive identical paragraphs
    cleaned = []
    prev = None
    for p in paragraphs:
        if p == prev:
            continue
        cleaned.append(p)
        prev = p

    return "\n\n".join(cleaned).strip()

def parse_pubdate(entry):
    # robustly parse feed entry published date to datetime
    published = entry.get("published") or entry.get("updated") or ""
    if published:
        try:
            dt = parsedate_to_datetime(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    # fallback to now UTC
    return datetime.now(timezone.utc)

def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    items = []

    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        count = 0

        for entry in feed.entries:
            if count >= per_feed_limit:
                break

            link = entry.get("link")
            if not link:
                continue

            original_link = link
            archive_link = ARCHIVE_PREFIX + original_link

            # fetch and extract using Selenium + XPath primary, section fallback
            try:
                node_html_or_page = fetch_page_node_html(original_link)
                article_text = extract_article_text_from_html(node_html_or_page)
            except Exception:
                article_text = ""

            # extract image if present in feed metadata
            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url")

            pub_dt = parse_pubdate(entry)
            pub_str = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

            items.append({
                "title": entry.get("title", "").strip(),
                "link": archive_link,           # keep archive link as RSS link
                "original_link": original_link,
                "description": article_text,
                "pubDate": pub_str,
                "pub_dt": pub_dt,
                "image": image_url
            })

            count += 1
            time.sleep(1)

    # sort by parsed datetime desc
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

def create_rss(items, outpath="combined.xml"):
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:media": "http://search.yahoo.com/mrss/"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined Economist feed with full article text extracted via Selenium (XPath primary, section fallback)."

    for it in items:
        i = ET.SubElement(channel, "item")
        ET.SubElement(i, "title").text = it["title"]
        ET.SubElement(i, "link").text = it["link"]
        ET.SubElement(i, "description").text = it["description"]
        ET.SubElement(i, "pubDate").text = it["pubDate"]

        if it.get("image"):
            ET.SubElement(i, "enclosure", url=it["image"], type="image/jpeg")
            ET.SubElement(i, "media:content", url=it["image"], medium="image")

    xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    with open(outpath, "wb") as f:
        f.write(xml_bytes)

if __name__ == "__main__":
    try:
        items = fetch_items(RSS_FEEDS, PER_FEED_LIMIT)
        create_rss(items)
    finally:
        # ensure browser quits even on error
        try:
            browser.quit()
        except Exception:
            pass

    print("combined.xml written")
