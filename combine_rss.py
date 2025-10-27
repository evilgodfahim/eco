import os
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import re

# --------------------------
# CONFIG
# --------------------------
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

OUTPUT_FILE = "combined_feed.xml"
WAIT_TIME = 8
MAX_ARTICLES_PER_FEED = 5  # Set to None to process all articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --------------------------
# DRIVER SETUP
# --------------------------
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=chrome_options)

# --------------------------
# FETCH FROM ARCHIVE.IS
# --------------------------
def fetch_article_content(url):
    """Fetch full readable text from archive.is snapshot."""
    try:
        driver = setup_driver()
    except WebDriverException as e:
        logging.error(f"Selenium setup failed: {e}")
        return None

    try:
        logging.info(f"Fetching content from: {url}")
        driver.get(url)
        time.sleep(WAIT_TIME)

        # Find all frames and switch to the one that has visible text
        frames = driver.find_elements(By.TAG_NAME, "frame")
        if frames:
            logging.info(f"Found {len(frames)} frames, searching for readable content...")
            for frame in frames:
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(frame)
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    if len(body_text.strip()) > 400:
                        logging.info("Readable frame found.")
                        break
                except Exception:
                    continue

        # Parse article content
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # Extract from article section
        article_tag = soup.find("article")
        if not article_tag:
            # fallback: try main content divs
            possible_divs = soup.find_all("div")
            article_tag = max(possible_divs, key=lambda d: len(d.get_text(" ", strip=True)), default=None)

        if not article_tag:
            logging.warning("No readable article block found.")
            return None

        text = article_tag.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) > 300 else None

    except Exception as e:
        logging.error(f"Error fetching content: {e}")
        return None
    finally:
        driver.quit()

# --------------------------
# PARSE RSS
# --------------------------
def fetch_items(feed_url):
    try:
        logging.info(f"Parsing feed: {feed_url}")
        response = requests.get(feed_url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "xml")
        return soup.find_all("item")
    except Exception as e:
        logging.error(f"Failed to parse feed: {e}")
        return []

# --------------------------
# MAIN FUNCTION
# --------------------------
def combine_feeds(rss_feeds):
    logging.info("Starting RSS feed aggregation...")
    root = ET.Element("articles")
    
    total_articles = 0

    for feed_url in rss_feeds:
        logging.info(f"\n{'='*60}")
        logging.info(f"Processing feed: {feed_url}")
        logging.info(f"{'='*60}")
        
        items = fetch_items(feed_url)
        
        if not items:
            logging.warning(f"No items found in feed: {feed_url}")
            continue
        
        # Process articles per feed (limited or all)
        items_to_process = items[:MAX_ARTICLES_PER_FEED] if MAX_ARTICLES_PER_FEED else items
        
        for idx, item in enumerate(items_to_process, start=1):
            title = item.title.text if item.title else "No title"
            link = item.link.text if item.link else "No link"
            pub_date = item.pubDate.text if item.pubDate else "No date"
            desc = item.description.text if item.description else ""

            # Try to find archived version
            archive_link = f"https://archive.is/{link}"
            content = fetch_article_content(archive_link)

            article = ET.SubElement(root, "article")
            ET.SubElement(article, "title").text = title
            ET.SubElement(article, "link").text = link
            ET.SubElement(article, "archive").text = archive_link
            ET.SubElement(article, "pubDate").text = pub_date
            ET.SubElement(article, "description").text = desc
            ET.SubElement(article, "content").text = content or "No readable text found."
            ET.SubElement(article, "feed_source").text = feed_url

            total_articles += 1
            logging.info(f"Added article {idx} from this feed (Total: {total_articles}): {title}")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    
    logging.info(f"\n{'='*60}")
    logging.info(f"Feed aggregation complete!")
    logging.info(f"Total articles processed: {total_articles}")
    logging.info(f"Total feeds processed: {len(rss_feeds)}")
    logging.info(f"Saved to: {OUTPUT_FILE}")
    logging.info(f"{'='*60}")

# --------------------------
# RUN
# --------------------------
if __name__ == "__main__":
    combine_feeds(RSS_FEEDS)