import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    service = Service('/usr/bin/chromedriver')  # Update path if needed
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_article_content(url):
    driver = setup_driver()
    try:
        logging.info(f"Fetching content from: {url}")
        driver.get(url)
        time.sleep(10)  # Wait for content to load
        
        try:
            # Adjust selector based on archive.is structure
            content = driver.find_element(By.CSS_SELECTOR, '.article-content').text
            return content
        except NoSuchElementException:
            logging.error("Content element not found")
            return None
        except TimeoutException:
            logging.error("Page load timed out")
            return None
    finally:
        driver.quit()

def fetch_items(feed_urls):
    all_items = []
    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if not hasattr(entry, "link"):
                continue
            original_link = entry.link
            archive_link = ARCHIVE_PREFIX + original_link
            
            # Fetch full article content
            full_content = fetch_article_content(archive_link)
            
            all_items.append({
                "title": entry.title,
                "link": archive_link,
                "description": full_content if full_content else entry.get("description", ""),
                "pubDate": entry.get("published", datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
            })
    return all_items
