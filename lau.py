#!/usr/bin/env python3
# lau.py - Combined Economist RSS using Selenium + webdriver-manager (+ optional RecaptchaSolver)

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import sys

# Try to import RecaptchaSolver; proceed without it if not usable in environment
try:
    from selenium_recaptcha_solver import RecaptchaSolver
except Exception:
    RecaptchaSolver = None

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
    "https://www.economist.com/the-americas/rss.xml",
]

PRIMARY_XPATH = (
    "/html/body/center/div[4]/div/div[1]/div/div/div[1]/div/div/div[3]/"
    "div/main/article/div/div[1]/div[3]/div/section/div"
)

# Create Chrome webdriver using webdriver-manager to fetch matching chromedriver
def create_webdriver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        # use modern headless mode if available
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # optional UA to reduce detection footprint
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    # install driver that matches installed Chrome
    chromedriver_path = ChromeDriverManager().install()
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# Attempt to detect and solve reCAPTCHA using solver (if available)
def solve_recaptcha_if_present(driver, solver, timeout=20):
    if solver is None:
        return False
    try:
        # search for common recaptcha iframe patterns
        iframe = None
        candidates = [
            '//iframe[contains(@src, "recaptcha")]',
            '//iframe[contains(@title, "reCAPTCHA")]',
            '//iframe[contains(@src, "google.com/recaptcha")]',
        ]
        for xp in candidates:
            try:
                iframe = driver.find_element(By.XPATH, xp)
                if iframe:
                    break
            except NoSuchElementException:
                continue
        if not iframe:
            return False
        # click checkbox flow (library helper)
        try:
            solver.click_recaptcha_v2(iframe=iframe)
            # wait a bit for challenge to clear
            t0 = time.time()
            while time.time() - t0 < timeout:
                try:
                    # re-check presence
                    driver.find_element(By.XPATH, xp)
                    time.sleep(1)
                except NoSuchElementException:
                    return True
            return True
        except Exception:
            try:
                solver.solve_recaptcha_v2_audio(iframe=iframe)
                return True
            except Exception:
                return False
    except Exception:
        return False

# Extract article text: prefer XPath fragment if provided, else use section + line-height filter
def extract_article_text_from_html(html_fragment_or_page_source):
    if not html_fragment_or_page_source:
        return ""
    soup = BeautifulSoup(html_fragment_or_page_source, "html.parser")

    # Try section-based extraction first
    section = soup.find("section")
    paragraphs = []
    if section:
        for div in section.find_all("div", style=True):
            style = (div.get("style") or "").replace(" ", "").lower()
            if "line-height:28px" in style and "display:none" not in style:
                if div.find("figcaption"):
                    continue
                text = div.get_text(separator=" ", strip=True)
                if text:
                    paragraphs.append(text)

    # Fallback: permissive scan
    if not paragraphs:
        for div in soup.find_all("div"):
            style = (div.get("style") or "").replace(" ", "").lower()
            if "display:none" in style:
                continue
            text = div.get_text(separator=" ", strip=True)
            if not text:
                continue
            if "line-height:28px" in style or "line-height:24px" in style or div.find_parent("article"):
                if div.find("figcaption"):
                    continue
                paragraphs.append(text)

    # Deduplicate consecutive duplicates
    cleaned = []
    prev = None
    for p in paragraphs:
        if p == prev:
            continue
        cleaned.append(p)
        prev = p

    return "\n\n".join(cleaned).strip()

def fetch_node_outer_html_if_xpath_matches(driver, xpath):
    try:
        node = driver.find_element(By.XPATH, xpath)
        if node:
            return node.get_attribute("outerHTML") or ""
    except Exception:
        return ""

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

def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    items = []
    driver = create_webdriver(headless=True)
    solver = None
    if RecaptchaSolver is not None:
        try:
            solver = RecaptchaSolver(driver=driver)
        except Exception:
            solver = None

    try:
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

                article_text = ""
                try:
                    try:
                        driver.set_page_load_timeout(40)
                        driver.get(original_link)
                    except TimeoutException:
                        pass
                    time.sleep(2)

                    # attempt recaptcha solve if present
                    if solver:
                        try:
                            solve_recaptcha_if_present(driver, solver)
                        except Exception:
                            pass

                    # try primary XPath fragment first
                    outer = fetch_node_outer_html_if_xpath_matches(driver, PRIMARY_XPATH)
                    if outer:
                        article_text = extract_article_text_from_html(outer)
                    else:
                        page_src = driver.page_source
                        article_text = extract_article_text_from_html(page_src)
                except Exception:
                    article_text = ""

                image_url = None
                if hasattr(entry, "media_content") and entry.media_content:
                    image_url = entry.media_content[0].get("url")
                elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get("url")

                pub_dt = parse_pubdate(entry)
                pub_str = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

                items.append({
                    "title": entry.get("title", "").strip(),
                    "link": archive_link,
                    "original_link": original_link,
                    "description": article_text,
                    "pubDate": pub_str,
                    "pub_dt": pub_dt,
                    "image": image_url,
                })

                count += 1
                time.sleep(1)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

def create_rss(items, outpath="combined.xml"):
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:media": "http://search.yahoo.com/mrss/"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined Economist feed with full article text (Selenium)."

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
    except Exception as e:
        print("ERROR:", repr(e), file=sys.stderr)
        raise
    print("combined.xml written")
