#!/usr/bin/env python3
# lau.py - Combined Economist RSS using BotBrowser + Playwright CDP

import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import time
import sys
import os
import re
import random
import subprocess
import requests

# ------------------------------
# CONFIG
# ------------------------------

PER_FEED_LIMIT = 10
MAX_ITEMS = 500
ARCHIVE_PREFIX = "https://archive.is/o/nuunc/"
TIMEOUT_MS = 90000

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

# ------------------------------
# BotBrowser Configuration
# ------------------------------

BOTBROWSER_BINARY   = os.environ.get("BOTBROWSER_PATH", "./BotBrowser/dist/botbrowser")
BOTBROWSER_CDP_PORT = int(os.environ.get("BOTBROWSER_CDP_PORT", "9222"))
BOTBROWSER_PROFILE  = os.environ.get("BOTBROWSER_PROFILE", "")

_botbrowser_proc: subprocess.Popen | None = None


def _start_botbrowser() -> bool:
    """Launch a fresh BotBrowser process and wait for CDP to be ready."""
    global _botbrowser_proc

    # Kill any existing process first
    if _botbrowser_proc is not None and _botbrowser_proc.poll() is None:
        print(f"Killing existing BotBrowser (pid {_botbrowser_proc.pid})", file=sys.stderr)
        _botbrowser_proc.kill()
        try:
            _botbrowser_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        _botbrowser_proc = None

    if not os.path.isfile(BOTBROWSER_BINARY):
        print(f"⚠️  BotBrowser binary not found at '{BOTBROWSER_BINARY}'.", file=sys.stderr)
        return False

    cmd = [
        BOTBROWSER_BINARY,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--remote-debugging-port={BOTBROWSER_CDP_PORT}",
        "--remote-debugging-address=127.0.0.1",
        "--disable-blink-features=AutomationControlled",
    ]
    if BOTBROWSER_PROFILE:
        cmd.append(f"--bot-profile={BOTBROWSER_PROFILE}")

    print(f"Launching BotBrowser: {' '.join(cmd)}", file=sys.stderr)
    try:
        _botbrowser_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"⚠️  Failed to launch BotBrowser: {e}", file=sys.stderr)
        return False

    # Wait until CDP is reachable (up to 15 s)
    cdp_url = f"http://127.0.0.1:{BOTBROWSER_CDP_PORT}/json/version"
    for _ in range(30):
        try:
            r = requests.get(cdp_url, timeout=2)
            if r.status_code == 200:
                print(f"✓ BotBrowser CDP ready on port {BOTBROWSER_CDP_PORT}", file=sys.stderr)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    print("⚠️  BotBrowser CDP did not become ready within 15 s", file=sys.stderr)
    return False


def _ensure_botbrowser_running() -> bool:
    """Start BotBrowser if not already running."""
    global _botbrowser_proc
    if _botbrowser_proc is not None and _botbrowser_proc.poll() is None:
        return True
    return _start_botbrowser()


def _botbrowser_fetch_once(url: str) -> str | None:
    """Single attempt to fetch a URL via BotBrowser + Playwright CDP."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("⚠️  playwright is not installed.", file=sys.stderr)
        return None

    cdp_endpoint = f"http://127.0.0.1:{BOTBROWSER_CDP_PORT}"
    print(f"  BotBrowser GET: {url}", file=sys.stderr)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(cdp_endpoint)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                java_script_enabled=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            except PWTimeout:
                print(f"  ⚠️  BotBrowser navigation timed out for {url}", file=sys.stderr)
                page.close(); context.close(); browser.close()
                return None

            # Wait for networkidle (non-fatal if it times out)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeout:
                print(f"  networkidle timed out for {url} (non-fatal)", file=sys.stderr)

            # Human-like scroll
            try:
                page.evaluate("""
                    async () => {
                        const delay = ms => new Promise(r => setTimeout(r, ms));
                        const h = document.body.scrollHeight;
                        let pos = 0;
                        while (pos < h) {
                            const amt = Math.floor(Math.random() * 400) + 300;
                            window.scrollBy(0, amt);
                            pos += amt;
                            await delay(Math.random() * 500 + 300);
                        }
                        window.scrollTo(0, 0);
                        await delay(500);
                    }
                """)
            except Exception as e:
                print(f"  Scroll error (non-fatal): {e}", file=sys.stderr)

            html = page.content()
            page.close(); context.close(); browser.close()

    except Exception as e:
        print(f"  ⚠️  BotBrowser Playwright error for {url}: {e}", file=sys.stderr)
        return None

    if not html or len(html) < 500:
        print(f"  ⚠️  BotBrowser returned suspiciously short HTML ({len(html)} bytes) for {url}",
              file=sys.stderr)
        return None

    print(f"  ✓ BotBrowser received {len(html)} bytes", file=sys.stderr)
    return html


def botbrowser_get(url: str, retries: int = 2) -> str | None:
    """
    Fetch url via BotBrowser with automatic restart+retry on failure.
    """
    for attempt in range(1, retries + 1):
        if not _ensure_botbrowser_running():
            print(f"  ⚠️  BotBrowser not available (attempt {attempt}/{retries})", file=sys.stderr)
            time.sleep(2)
            continue

        # Restart if process died since we checked
        if _botbrowser_proc is None or _botbrowser_proc.poll() is not None:
            print(f"  ⚠️  BotBrowser died before fetch attempt {attempt} — restarting", file=sys.stderr)
            if not _start_botbrowser():
                time.sleep(2)
                continue

        result = _botbrowser_fetch_once(url)
        if result:
            return result

        # Fetch failed — check if process is still alive
        if _botbrowser_proc is not None and _botbrowser_proc.poll() is not None:
            print(f"  ⚠️  BotBrowser process exited (code {_botbrowser_proc.returncode}) "
                  f"after attempt {attempt} — will restart", file=sys.stderr)
        else:
            print(f"  ⚠️  BotBrowser fetch failed on attempt {attempt} — restarting for retry",
                  file=sys.stderr)

        if attempt < retries:
            _start_botbrowser()
            time.sleep(2)

    print(f"  ❌ BotBrowser: all {retries} attempts failed for {url}", file=sys.stderr)
    return None


def _botbrowser_shutdown():
    global _botbrowser_proc
    if _botbrowser_proc is not None and _botbrowser_proc.poll() is None:
        print(f"Shutting down BotBrowser (pid {_botbrowser_proc.pid})", file=sys.stderr)
        _botbrowser_proc.terminate()
        try:
            _botbrowser_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _botbrowser_proc.kill()
        _botbrowser_proc = None


# ------------------------------
# Article Text Extraction
# ------------------------------

def normalize_style(style_str):
    """Normalize style string by removing all whitespace."""
    if not style_str:
        return ""
    return re.sub(r'\s+', '', style_str.lower())


def is_content_div(div, style_norm):
    """Check if a div contains article content based on style."""
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
    """Extract article text with improved logic."""
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

    # Fallback: broader extraction if too few paragraphs found
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
                if not any(kw in text.lower() for kw in ['subscribe', 'sign in', 'menu', 'share this']):
                    paragraphs.append(text)
                    seen_texts.add(text)

    return "\n\n".join(paragraphs).strip()


# ------------------------------
# RSS Helpers
# ------------------------------

def parse_pubdate(entry):
    """Parse publication date from RSS entry."""
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
# Main Fetch Logic
# ------------------------------

def fetch_items(feed_urls, per_feed_limit=PER_FEED_LIMIT):
    """Fetch and process RSS feed items using BotBrowser."""
    items = []

    try:
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
                        print(f"\n[{count + 1}/{per_feed_limit}] Fetching: {archive_link}",
                              file=sys.stderr)

                        # Random delay before fetching
                        delay = random.uniform(5, 10)
                        print(f"Waiting {delay:.1f}s before request...", file=sys.stderr)
                        time.sleep(delay)

                        content = botbrowser_get(archive_link, retries=2)

                        if content:
                            print(f"✓ Extracted HTML: {len(content)} bytes", file=sys.stderr)
                            article_text = extract_article_text_from_html(content)
                            print(f"✓ Extracted {len(article_text)} characters", file=sys.stderr)

                            if len(article_text) < 500:
                                print(f"⚠️  Short article text ({len(article_text)} chars)",
                                      file=sys.stderr)

                                # Save debug HTML on first short-text attempt
                                if retry_count == 0:
                                    debug_file = f"debug_{count}_{retry_count}.html"
                                    with open(debug_file, "w", encoding="utf-8") as f:
                                        f.write(content)
                                    print(f"Debug file saved: {debug_file}", file=sys.stderr)

                                article_text = ""  # force retry
                                retry_count += 1
                                if retry_count < max_retries:
                                    print(f"Retrying... (attempt {retry_count + 1}/{max_retries})",
                                          file=sys.stderr)
                                    time.sleep(random.uniform(10, 15))
                            else:
                                break  # success

                        else:
                            print(f"❌ BotBrowser returned no content", file=sys.stderr)
                            retry_count += 1
                            if retry_count < max_retries:
                                time.sleep(random.uniform(10, 15))

                    except Exception as e:
                        print(f"❌ Error extracting article: {repr(e)}", file=sys.stderr)
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(random.uniform(10, 15))

                # Extract image from RSS entry
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
        _botbrowser_shutdown()

    # Sort by date and limit
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:MAX_ITEMS]


# ------------------------------
# RSS Output
# ------------------------------

def create_rss(items, outpath="combined.xml"):
    """Create RSS XML file from items."""
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


# ------------------------------
# Entry Point
# ------------------------------

if __name__ == "__main__":
    try:
        print("=" * 60, file=sys.stderr)
        print("Starting Economist RSS Scraper (BotBrowser)", file=sys.stderr)
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
