#!/usr/bin/env python3
# lau.py - Combined Economist RSS using undetected-chromedriver for better bot evasion

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
import time
import sys
import re
import random

# CONFIG
PER_FEED_LIMIT = 1
MAX_ITEMS = 500
ARCHIVE_PREFIX = "https://archive.is/o/nuunc/"
RSS_FEEDS = [
    "https://www.economist.com/briefing/rss.xml",
    #"https://www.economist.com/the-economist-explains/rss.xml",
    #"https://www.economist.com/leaders/rss.xml",
    #"https://www.economist.com/asia/rss.xml",
    #"https://www.economist.com/china/rss.xml",
    #"https://www.economist.com/international/rss.xml",
    #"https://www.economist.com/united-states/rss.xml",
    #"https://www.economist.com/finance-and-economics/rss.xml",
    #"https://www.economist.com/the-world-this-week/rss.xml",
    #"https://www.economist.com/science-and-technology/rss.xml",
    #"https://www.economist.com/europe/rss.xml",
    #"https://www.economist.com/business/rss.xml",
    #"https://www.economist.com/graphic-detail/rss.xml",
    #"https://www.economist.com/rss/middle_east_and_africa_rss.xml",
    #"https://www.economist.com/the-americas/rss.xml",
]

# Multiple XPath patterns to try
XPATH_PATTERNS = [
    "/html/body/center/div[4]/div/div[1]/div/div/div[1]/div/div/div[3]/div/main/article/div/div[1]/div[3]/div/section",
    "//article//section",
    "//main//article//section",
    "//article",
]

def create_webdriver(headless=True):
    """Create undetected Chrome driver with better anti-detection"""
    options = uc.ChromeOptions()
    
    # Basic options
    if headless:
        options.add_argument("--headless=new")
    
    # Anti-detection options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Randomize user agent slightly
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    options.add_argument(f"user-agent={random.choice(user_agents)}")
    
    try:
        driver = uc.Chrome(options=options, version_main=None, use_subprocess=True)
        
        # Additional stealth measures
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = {
                    runtime: {}
                };
            '''
        })
        
        return driver
    except Exception as e:
        print(f"Error creating webdriver: {e}", file=sys.stderr)
        raise

def human_like_scroll(driver):
    """Simulate human-like scrolling behavior"""
    try:
        # Get page height
        total_height = driver.execute_script("return document.body.scrollHeight")
        
        # Scroll in chunks
        current_position = 0
        while current_position < total_height:
            scroll_amount = random.randint(300, 700)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            current_position += scroll_amount
            time.sleep(random.uniform(0.3, 0.8))
        
        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"Scroll error: {e}", file=sys.stderr)

def check_for_captcha(driver):
    """Check if CAPTCHA is present on the page"""
    try:
        # Check for common CAPTCHA indicators
        captcha_indicators = [
            "recaptcha",
            "captcha",
            "verify you are human",
            "automated queries",
            "Try again later"
        ]
        
        page_text = driver.page_source.lower()
        for indicator in captcha_indicators:
            if indicator in page_text:
                return True
        return False
    except Exception:
        return False

def wait_for_page_load(driver, timeout=30):
    """Wait for page to fully load"""
    try:
        start_time = time.time()
        while time.time() - start_time < timeout:
            ready_state = driver.execute_script("return document.readyState")
            if ready_state == "complete":
                return True
            time.sleep(0.5)
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
    seen_texts = set()
    
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
                txt = child.get_text(separator=" ", strip=True)
                if txt:
                    text_parts.append(txt)
        
        text = " ".join(text_parts).strip()
        
        # Filter out very short texts and check for duplicates
        if len(text) > 20 and text not in seen_texts:
            is_duplicate = False
            for existing in seen_texts:
                if text in existing or existing in text:
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
        
        for div in all_divs:
            style = div.get("style", "")
            style_norm = normalize_style(style)
            
            if 'display:none' in style_norm:
                continue
            if div.find('figcaption'):
                continue
            
            text = div.get_text(separator=" ", strip=True)
            
            if len(text) > 50 and text not in seen_texts:
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
                if html and len(html) > 100:
                    return html
        except Exception:
            continue
    return ""

def parse_pubdate(entry):
    """Parse publication date from RSS entry"""
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
    """Fetch and process RSS feed items"""
    items = []
    driver = None
    
    try:
        driver = create_webdriver(headless=True)
        
        for feed_url in feed_urls:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Processing feed: {feed_url}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            
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
                retry_count = 0
                max_retries = 2
                
                while retry_count < max_retries and not article_text:
                    try:
                        print(f"\n[{count + 1}/{per_feed_limit}] Fetching: {archive_link}", file=sys.stderr)
                        
                        # Random delay before fetching
                        delay = random.uniform(5, 10)
                        print(f"Waiting {delay:.1f}s before request...", file=sys.stderr)
                        time.sleep(delay)
                        
                        # Set timeout and navigate
                        driver.set_page_load_timeout(90)
                        driver.get(archive_link)
                        
                        # Wait for page to load
                        print("Waiting for page to load...", file=sys.stderr)
                        wait_for_page_load(driver, timeout=15)
                        time.sleep(random.uniform(3, 5))
                        
                        # Check for CAPTCHA
                        if check_for_captcha(driver):
                            print("⚠️  CAPTCHA detected! Waiting longer...", file=sys.stderr)
                            time.sleep(random.uniform(15, 25))
                            
                            if check_for_captcha(driver):
                                print("❌ CAPTCHA still present, skipping article", file=sys.stderr)
                                retry_count += 1
                                continue
                        
                        # Simulate human behavior
                        human_like_scroll(driver)
                        time.sleep(random.uniform(1, 2))
                        
                        # Try multiple XPath patterns
                        outer_html = fetch_node_outer_html_with_xpaths(driver, XPATH_PATTERNS)
                        
                        if outer_html:
                            print(f"✓ Extracted HTML fragment: {len(outer_html)} bytes", file=sys.stderr)
                            article_text = extract_article_text_from_html(outer_html)
                        
                        # Fallback to full page source
                        if not article_text or len(article_text) < 500:
                            print("Using fallback to page source", file=sys.stderr)
                            page_src = driver.page_source
                            article_text = extract_article_text_from_html(page_src)
                        
                        print(f"✓ Extracted {len(article_text)} characters", file=sys.stderr)
                        
                        # Check if extraction was successful
                        if len(article_text) < 500:
                            print(f"⚠️  Short article text ({len(article_text)} chars)", file=sys.stderr)
                            
                            # Save debug info
                            if retry_count == 0:
                                debug_file = f"debug_{count}_{retry_count}.html"
                                with open(debug_file, "w", encoding="utf-8") as f:
                                    f.write(driver.page_source)
                                print(f"Debug file saved: {debug_file}", file=sys.stderr)
                            
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"Retrying... (attempt {retry_count + 1}/{max_retries})", file=sys.stderr)
                                time.sleep(random.uniform(10, 15))
                        else:
                            break  # Success, exit retry loop
                            
                    except TimeoutException:
                        print("⚠️  Page load timeout", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(random.uniform(10, 15))
                    except Exception as e:
                        print(f"❌ Error extracting article: {repr(e)}", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(random.uniform(10, 15))

                # Extract image
                image_url = None
                if hasattr(entry, "media_content") and entry.media_content:
                    image_url = entry.media_content[0].get("url")
                elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get("url")

                # Parse publication date
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
                
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", file=sys.stderr)
    except Exception as e:
        print(f"\n❌ Fatal error: {repr(e)}", file=sys.stderr)
        raise
    finally:
        if driver:
            try:
                print("\nClosing browser...", file=sys.stderr)
                driver.quit()
            except Exception:
                pass

    # Sort by date and limit
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

def create_rss(items, outpath="combined.xml"):
    """Create RSS XML file from items"""
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:media": "http://search.yahoo.com/mrss/"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://yourusername.github.io/combined.xml"
    ET.SubElement(channel, "description").text = "Combined Economist feed with full article text."

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
        print("=" * 60, file=sys.stderr)
        print("Starting Economist RSS Scraper", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        
        items = fetch_items(RSS_FEEDS, PER_FEED_LIMIT)
        create_rss(items)
        
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"✓ SUCCESS: combined.xml written with {len(items)} items", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
    except Exception as e:
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"❌ ERROR: {repr(e)}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        raise
