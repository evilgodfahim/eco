#!/usr/bin/env python3
# lau.py - Combined Economist RSS using Selenium + selenium-recaptcha-solver
# Requires: selenium, selenium-recaptcha-solver, beautifulsoup4, feedparser, requests
# Run in an environment with Chrome and chromedriver installed.

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from selenium_recaptcha_solver import RecaptchaSolver
from bs4 import BeautifulSoup
import time
import sys

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

# Non-headless-looking user-agent (avoid obvious HeadlessChrome)
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
)

# WEBDRIVER
def create_webdriver(headless=True, ua=DEFAULT_UA):
    opts = webdriver.ChromeOptions()
    if headless:
        # use new headless mode where available
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-agent={ua}")
    # optional: reduce logging
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=opts)

# RECAPTCHA SOLVING (if present)
def solve_recaptcha_if_present(driver, solver, timeout=20):
    """
    Detect a reCAPTCHA iframe and attempt to solve it using the solver.
    Returns True if a solve was attempted, False otherwise.
    """
    try:
        # common iframe patterns
        iframe_xpath_candidates = [
            '//iframe[contains(@src, "recaptcha")]',
            '//iframe[@title="reCAPTCHA"]',
            '//iframe[contains(@title, "reCAPTCHA")]',
            '//iframe[contains(@src, "google.com/recaptcha")]',
        ]
        iframe = None
        for xp in iframe_xpath_candidates:
            try:
                iframe = driver.find_element(By.XPATH, xp)
                if iframe:
                    break
            except NoSuchElementException:
                continue

        if not iframe:
            return False

        # click checkbox / trigger solver (library provides click_recaptcha_v2)
        try:
            solver.click_recaptcha_v2(iframe=iframe)
            # give time for the challenge to resolve
            t0 = time.time()
            while time.time() - t0 < timeout:
                # if recaptcha removed or iframe no longer present, assume solved
                try:
                    _ = driver.find_element(By.XPATH, xp)
                    time.sleep(1)
                except NoSuchElementException:
                    break
            return True
        except Exception:
            # attempt audio-based solve if click_recaptcha_v2 failed
            try:
                solver.solve_recaptcha_v2_audio(iframe=iframe)
                return True
            except Exception:
                return False
    except Exception:
        return False

# EXTRACTION: XPath via Selenium first, then section+line-height fallback via BeautifulSoup
def extract_article_text_from_driver_html(html_fragment_or_page_source):
    if not html_fragment_or_page_source:
        return ""

    soup = BeautifulSoup(html_fragment_or_page_source, "html.parser")

    # If the content is a full page, try to find the precise section
    section_node = soup.find("section")
    paragraphs = []

    if section_node:
        for div in section_node.find_all("div", style=True):
            style = (div.get("style") or "").replace(" ", "").lower()
            if "line-height:28px" in style and "display:none" not in style:
                if div.find("figcaption"):
                    continue
                text = div.get_text(separator=" ", strip=True)
                if text:
                    paragraphs.append(text)

    # If nothing found with section method, attempt permissive div scan on the fragment/page
    if not paragraphs:
        # collect divs that look like article paragraphs
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

    # Dedupe small consecutive duplicates and return
    cleaned = []
    prev = None
    for p in paragraphs:
        if p == prev:
            continue
        cleaned.append(p)
        prev = p

    return "\n\n".join(cleaned).strip()

# Try to fetch node via Selenium XPath; return outerHTML on success
def fetch_node_outer_html_if_xpath_matches(driver, xpath):
    try:
        node = driver.find_element(By.XPATH, xpath)
        if node:
            outer = node.get_attribute("outerHTML")
            return outer or ""
    except NoSuchElementException:
        return ""
    except WebDriverException:
        return ""

# DATE PARSING
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

# MAIN FETCH LOOP
def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    items = []
    driver = None
    solver = None
    try:
        driver = create_webdriver(headless=True)
        solver = RecaptchaSolver(driver=driver)
    except Exception as e:
        # if solver init fails, still try without solver
        solver = None
        if driver is None:
            # critical failure creating webdriver
            raise

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

            # Attempt: open original page with Selenium (precise), solve recaptcha if necessary
            article_text = ""
            try:
                try:
                    driver.set_page_load_timeout(40)
                    driver.get(original_link)
                except TimeoutException:
                    # proceed with whatever loaded
                    pass
                time.sleep(2)  # let JS settle

                # if recaptcha present, try to solve
                solved = False
                if solver:
                    try:
                        solved = solve_recaptcha_if_present(driver, solver)
                    except Exception:
                        solved = False

                # try primary XPath on rendered DOM via Selenium
                outer = ""
                try:
                    outer = fetch_node_outer_html_if_xpath_matches(driver, PRIMARY_XPATH)
                except Exception:
                    outer = ""

                if outer:
                    article_text = extract_article_text_from_driver_html(outer)
                else:
                    # fallback: get full page source and extract section paragraphs
                    page_src = driver.page_source
                    article_text = extract_article_text_from_driver_html(page_src)

            except Exception:
                article_text = ""

            # image extraction from feed entry if available
            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get("url")

            pub_dt = parse_pubdate(entry)
            pub_str = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

            items.append(
                {
                    "title": entry.get("title", "").strip(),
                    "link": archive_link,
                    "original_link": original_link,
                    "description": article_text,
                    "pubDate": pub_str,
                    "pub_dt": pub_dt,
                    "image": image_url,
                }
            )

            count += 1
            time.sleep(1)

    # cleanup webdriver
    try:
        if driver:
            driver.quit()
    except Exception:
        pass

    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

# RSS CREATION
def create_rss(items, outpath="combined.xml"):
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:media": "http://search.yahoo.com/mrss/"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined Economist feed with full article text (Selenium + RecaptchaSolver)."

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

# RUN
if __name__ == "__main__":
    try:
        items = fetch_items(RSS_FEEDS, PER_FEED_LIMIT)
        create_rss(items)
    except Exception as e:
        # minimal error output (no extra words)
        print("ERROR:", repr(e), file=sys.stderr)
        try:
            # ensure driver quits on fatal error
            pass
        finally:
            raise
    print("combined.xml written")
