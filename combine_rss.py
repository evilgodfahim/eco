import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import time
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
OUTPUT_FILE = "combined.xml"


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.binary_location = "/usr/local/bin/chrome/chrome"  # Adjust if needed

    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def fetch_article_content(url):
    """Fetch full article content using Selenium from the archived link."""
    try:
        driver = setup_driver()
    except WebDriverException as e:
        logging.error(f"Selenium driver setup failed: {e}")
        return None

    try:
        logging.info(f"Fetching content from: {url}")
        driver.get(url)
        time.sleep(10)  # Allow time for the page to load

        try:
            content = driver.find_element(By.CSS_SELECTOR, "article, .article__body-text, .article-content").text
            return content.strip()
        except NoSuchElementException:
            logging.warning("Content not found on page.")
            return None
        except TimeoutException:
            logging.warning("Page load timed out.")
            return None
    except Exception as e:
        logging.error(f"Unexpected error while fetching content: {e}")
        return None
    finally:
        driver.quit()


def fetch_items(feed_urls):
    """Parse RSS feeds and fetch up to 20 articles."""
    all_items = []
    count = 0
    MAX_ARTICLES = 20

    for feed_url in feed_urls:
        if count >= MAX_ARTICLES:
            break
        logging.info(f"Parsing feed: {feed_url}")

        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if count >= MAX_ARTICLES:
                break
            if not hasattr(entry, "link"):
                continue

            original_link = entry.link
            archive_link = ARCHIVE_PREFIX + original_link

            full_content = fetch_article_content(archive_link)
            if not full_content:
                full_content = entry.get("description", "")

            item = {
                "title": entry.title,
                "link": archive_link,
                "description": full_content,
                "pubDate": entry.get("published", datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
            }

            all_items.append(item)
            count += 1
            logging.info(f"Added article {count}: {entry.title}")

    return all_items


def save_to_xml(items, output_file):
    """Save all articles to combined.xml."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    title = ET.SubElement(channel, "title")
    title.text = "Combined Economist RSS Feed"
    link = ET.SubElement(channel, "link")
    link.text = "https://www.economist.com/"
    description = ET.SubElement(channel, "description")
    description.text = "A combined feed of selected Economist sections."

    for item in items:
        item_el = ET.SubElement(channel, "item")

        title_el = ET.SubElement(item_el, "title")
        title_el.text = item["title"]

        link_el = ET.SubElement(item_el, "link")
        link_el.text = item["link"]

        desc_el = ET.SubElement(item_el, "description")
        desc_el.text = item["description"]

        pub_el = ET.SubElement(item_el, "pubDate")
        pub_el.text = item["pubDate"]

    tree = ET.ElementTree(rss)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    logging.info(f"Saved {len(items)} articles to {output_file}")


if __name__ == "__main__":
    logging.info("Starting RSS feed aggregation...")
    items = fetch_items(rss_feeds)
    save_to_xml(items, OUTPUT_FILE)
    logging.info("Feed aggregation complete.")