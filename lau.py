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
import re

from selenium_recaptcha_solver import RecaptchaSolver

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

# Multiple XPath patterns to try
XPATH_PATTERNS = [
    "/html/body/center/div[4]/div/div[1]/div/div/div[1]/div/div/div[3]/div/main/article/div/div[1]/div[3]/div/section",
    "//article//section",
    "//main//article//section",
    "//article",
]

def create_webdriver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    chromedriver_path = ChromeDriverManager().install()
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def solve_recaptcha_if_present(driver, solver, timeout=20):
    try:
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
        try:
            solver.click_recaptcha_v2(iframe=iframe)
            t0 = time.time()
            while time.time() - t0 < timeout:
                try:
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

def normalize_style(style_str):
    """Normalize style string by removing all whitespace"""
    if not style_str:
        return ""
    return re.sub(r'\s+', '', style_str.lower())

def is_content_div(div, style_norm):
    """Check if a div contains article content based on style"""
    # Skip if display:none
    if 'display:none' in style_norm:
        return False
    
    # Skip figcaptions
    if div.find('figcaption'):
        return False
    
    # Look for content indicators - line-height is key
    if 'line-height:28px' in style_norm or 'line-height:24px' in style_norm:
        return True
    
    # Also check font-size as indicator
    if ('font-size:20px' in style_norm or 'font-size:17px' in style_norm) and 'line-height' in style_norm:
        return True
    
    return False

def extract_article_text_from_html(html_content):
    """Extract article text with improved logic"""
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, "html.parser")
    paragraphs = []
    seen_texts = set()  # Track unique texts to avoid duplicates
    
    # First try to find the section element
    section = soup.find("section")
    search_root = section if section else soup
    
    # Find all divs in the content area
    all_divs = search_root.find_all("div", recursive=True)
    
    for div in all_divs:
        style = div.get("style", "")
        style_norm = normalize_style(style)
        
        if not is_content_div(div, style_norm):
            continue
        
        # Get direct text from this div (not from nested elements)
        text_parts = []
        for child in div.children:
            if isinstance(child, str):
                text_parts.append(child.strip())
            elif child.name in ['span', 'small', 'strong', 'em', 'a']:
                # Include text from inline elements
                txt = child.get_text(separator=" ", strip=True)
                if txt:
                    text_parts.append(txt)
        
        text = " ".join(text_parts).strip()
        
        # Filter out very short texts and check for duplicates
        if len(text) > 20 and text not in seen_texts:
            # Avoid nested duplicates - check if this text is substring of existing
            is_duplicate = False
            for existing in seen_texts:
                if text in existing or existing in text:
                    # Keep the longer version
                    if len(text) > len(existing):
                        paragraphs = [p for p in paragraphs if p != existing]
                        seen_texts.discard(existing)
                    else:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                paragraphs.append(text)
                seen_texts.add(text)
    
    # If we didn't find much, try a more permissive approach
    if len(paragraphs) < 3:
        paragraphs = []
        seen_texts = set()
        
        # Look for all divs with substantial text
        for div in all_divs:
            style = div.get("style", "")
            style_norm = normalize_style(style)
            
            if 'display:none' in style_norm:
                continue
            if div.find('figcaption'):
                continue
            
            # Get text
            text = div.get_text(separator=" ", strip=True)
            
            # More permissive length check
            if len(text) > 50 and text not in seen_texts:
                # Check it's not a navigation or UI element
                if not any(keyword in text.lower() for keyword in ['subscribe', 'sign in', 'menu', 'share this']):
                    paragraphs.append(text)
                    seen_texts.add(text)
    
    return "\n\n".join(paragraphs).strip()

def fetch_node_outer_html_with_xpaths(driver, xpath_list):
    """Try multiple XPath patterns to find the content"""
    for xpath in xpath_list:
        try:
            node = driver.find_element(By.XPATH, xpath)
            if node:
                html = node.get_attribute("outerHTML")
                if html and len(html) > 100:  # Ensure we got substantial content
                    return html
        except Exception:
            continue
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
    solver = RecaptchaSolver(driver=driver)

    try:
        for feed_url in feed_urls:
            print(f"Processing feed: {feed_url}", file=sys.stderr)
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
                    print(f"Fetching: {archive_link}", file=sys.stderr)
                    try:
                        driver.set_page_load_timeout(40)
                        driver.get(archive_link)
                    except TimeoutException:
                        pass
                    time.sleep(2)

                    # Attempt recaptcha solve if present
                    try:
                        solve_recaptcha_if_present(driver, solver)
                    except Exception:
                        pass

                    # Try multiple XPath patterns
                    outer_html = fetch_node_outer_html_with_xpaths(driver, XPATH_PATTERNS)
                    
                    if outer_html:
                        article_text = extract_article_text_from_html(outer_html)
                    
                    # Fallback to full page source if XPaths didn't work
                    if not article_text or len(article_text) < 200:
                        print("Using fallback to page source", file=sys.stderr)
                        page_src = driver.page_source
                        article_text = extract_article_text_from_html(page_src)
                    
                    print(f"Extracted {len(article_text)} characters", file=sys.stderr)
                    
                except Exception as e:
                    print(f"Error extracting article: {repr(e)}", file=sys.stderr)
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
        print(f"combined.xml written with {len(items)} items")
    except Exception as e:
        print("ERROR:", repr(e), file=sys.stderr)
        raise
