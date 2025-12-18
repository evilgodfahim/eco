#!/usr/bin/env python3
# lau.py - Combined Economist RSS using pyppeteer-stealth + GoogleRecaptchaBypass

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import asyncio
import time
import sys
import re
import random
from pyppeteer import launch
from pyppeteer_stealth import stealth
from GoogleRecaptchaBypass import AsyncBypass

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

def normalize_style(style_str):
    """Normalize style string by removing all whitespace"""
    if not style_str:
        return ""
    return re.sub(r'\s+', '', style_str.lower())

def is_content_div(div, style_norm):
    """Check if a div contains article content based on style"""
    if 'display:none' in style_norm:
        return False
    
    if div.find('figcaption'):
        return False
    
    if 'line-height:28px' in style_norm or 'line-height:24px' in style_norm:
        return True
    
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
    
    section = soup.find("section")
    search_root = section if section else soup
    
    all_divs = search_root.find_all("div", recursive=True)
    
    for div in all_divs:
        style = div.get("style", "")
        style_norm = normalize_style(style)
        
        if not is_content_div(div, style_norm):
            continue
        
        text_parts = []
        for child in div.children:
            if isinstance(child, str):
                text_parts.append(child.strip())
            elif child.name in ['span', 'small', 'strong', 'em', 'a']:
                txt = child.get_text(separator=" ", strip=True)
                if txt:
                    text_parts.append(txt)
        
        text = " ".join(text_parts).strip()
        
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

async def check_for_recaptcha(page):
    """Check if reCAPTCHA is present on the page"""
    try:
        # Check for reCAPTCHA iframe
        frames = page.frames
        for frame in frames:
            if 'recaptcha' in frame.url.lower():
                return True
    except:
        pass
    
    try:
        # Check page content for CAPTCHA indicators
        content = await page.content()
        captcha_indicators = [
            "recaptcha",
            "captcha",
            "verify you are human",
            "automated queries",
            "Try again later"
        ]
        
        content_lower = content.lower()
        for indicator in captcha_indicators:
            if indicator in content_lower:
                return True
    except:
        pass
    
    return False

async def solve_recaptcha_with_bypass(page, max_attempts=3):
    """Attempt to solve reCAPTCHA using GoogleRecaptchaBypass"""
    for attempt in range(max_attempts):
        try:
            print(f"  Attempting reCAPTCHA solve (attempt {attempt + 1}/{max_attempts})...", file=sys.stderr)
            
            # Wait a bit for reCAPTCHA to fully load
            await asyncio.sleep(random.uniform(2, 4))
            
            # Initialize GoogleRecaptchaBypass
            bypass = AsyncBypass(page)
            
            # Attempt to solve the reCAPTCHA
            result = await bypass.bypass()
            
            if result:
                print("  ✓ reCAPTCHA solved successfully!", file=sys.stderr)
                await asyncio.sleep(random.uniform(2, 4))
                return True
            else:
                print(f"  ✗ Solve attempt {attempt + 1} failed", file=sys.stderr)
                await asyncio.sleep(random.uniform(3, 6))
                
        except Exception as e:
            print(f"  ✗ Error solving reCAPTCHA: {e}", file=sys.stderr)
            await asyncio.sleep(random.uniform(3, 6))
    
    return False

async def human_like_scroll(page):
    """Simulate human-like scrolling behavior"""
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                const scrollHeight = document.body.scrollHeight;
                let currentPosition = 0;
                
                while (currentPosition < scrollHeight) {
                    const scrollAmount = Math.floor(Math.random() * 400) + 300;
                    window.scrollBy(0, scrollAmount);
                    currentPosition += scrollAmount;
                    await delay(Math.random() * 500 + 300);
                }
                
                window.scrollTo(0, 0);
                await delay(500);
            }
        """)
    except Exception as e:
        print(f"  Scroll error: {e}", file=sys.stderr)

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

async def fetch_items_async(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    """Fetch and process RSS feed items using Pyppeteer with stealth"""
    items = []
    
    # Launch browser with stealth mode
    browser = await launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--disable-extensions',
            '--disable-gpu',
        ],
        ignoreHTTPSErrors=True,
    )
    
    try:
        page = await browser.newPage()
        
        # Apply stealth mode
        await stealth(page)
        
        # Set viewport and user agent
        await page.setViewport({'width': 1920, 'height': 1080})
        await page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        
        # Additional stealth measures
        await page.evaluateOnNewDocument("""
            () => {
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
            }
        """)
        
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
                        await asyncio.sleep(delay)
                        
                        # Navigate to page
                        try:
                            await page.goto(archive_link, {
                                'waitUntil': 'networkidle2',
                                'timeout': 90000
                            })
                        except Exception as e:
                            print(f"  Navigation error: {e}", file=sys.stderr)
                            await page.goto(archive_link, {
                                'waitUntil': 'domcontentloaded',
                                'timeout': 90000
                            })
                        
                        print("Waiting for page to load...", file=sys.stderr)
                        await asyncio.sleep(random.uniform(3, 5))
                        
                        # Check for CAPTCHA
                        if await check_for_recaptcha(page):
                            print("⚠️  CAPTCHA detected! Attempting to solve...", file=sys.stderr)
                            
                            # Try to solve with GoogleRecaptchaBypass
                            solved = await solve_recaptcha_with_bypass(page, max_attempts=3)
                            
                            if not solved:
                                print("❌ CAPTCHA still present, skipping article", file=sys.stderr)
                                retry_count += 1
                                await asyncio.sleep(random.uniform(15, 25))
                                continue
                            else:
                                # Wait after solving
                                await asyncio.sleep(random.uniform(3, 5))
                        
                        # Simulate human behavior
                        await human_like_scroll(page)
                        await asyncio.sleep(random.uniform(1, 2))
                        
                        # Get page content
                        content = await page.content()
                        
                        if content:
                            print(f"✓ Extracted HTML: {len(content)} bytes", file=sys.stderr)
                            article_text = extract_article_text_from_html(content)
                        
                        print(f"✓ Extracted {len(article_text)} characters", file=sys.stderr)
                        
                        # Check if extraction was successful
                        if len(article_text) < 500:
                            print(f"⚠️  Short article text ({len(article_text)} chars)", file=sys.stderr)
                            
                            # Save debug info
                            if retry_count == 0:
                                debug_file = f"debug_{count}_{retry_count}.html"
                                with open(debug_file, "w", encoding="utf-8") as f:
                                    f.write(content)
                                print(f"Debug file saved: {debug_file}", file=sys.stderr)
                            
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"Retrying... (attempt {retry_count + 1}/{max_retries})", file=sys.stderr)
                                await asyncio.sleep(random.uniform(10, 15))
                        else:
                            break  # Success, exit retry loop
                            
                    except Exception as e:
                        print(f"❌ Error extracting article: {repr(e)}", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            await asyncio.sleep(random.uniform(10, 15))

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
        await browser.close()

    # Sort by date and limit
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]

def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    """Synchronous wrapper for async fetch_items_async"""
    return asyncio.get_event_loop().run_until_complete(
        fetch_items_async(feed_urls, per_feed_limit)
    )

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
