import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_article_content(driver, url):
    try:
        logging.info(f"Fetching content from: {url}")
        driver.get(url)
        
        # Wait for the archived content to load
        wait = WebDriverWait(driver, 15)
        
        # Based on your screenshot, the article content is in the main body
        # Archive.is wraps the original page, so we need to find the Economist article structure
        try:
            # Wait for body to be present
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)  # Give extra time for dynamic content
            
            # Try to find article content using various Economist-specific selectors
            selectors = [
                "article[data-test-id='Article']",  # Economist's article container
                "article",
                "div[class*='article']",
                "div[class*='ds-layout-grid']",  # Economist uses design system layout
                "section[class*='article']",
                "main"
            ]
            
            content = None
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        text = elements[0].text
                        if text and len(text) > 200:  # Ensure substantial content
                            logging.info(f"✓ Content found using: {selector} ({len(text)} chars)")
                            return text
                except:
                    continue
            
            # Fallback: Extract all paragraph text from the page
            logging.info("Trying paragraph extraction...")
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            
            # Filter out navigation/footer paragraphs and keep only article content
            content_paragraphs = []
            for p in paragraphs:
                text = p.text.strip()
                # Skip very short paragraphs (likely UI elements)
                if len(text) > 50:
                    content_paragraphs.append(text)
            
            if content_paragraphs:
                content = "\n\n".join(content_paragraphs)
                logging.info(f"✓ Extracted {len(content_paragraphs)} paragraphs ({len(content)} chars)")
                return content
            
            # Last resort: get all visible text and clean it
            logging.info("Trying full body text extraction...")
            body = driver.find_element(By.TAG_NAME, "body")
            all_text = body.text
            
            if len(all_text) > 500:
                logging.info(f"✓ Extracted body text ({len(all_text)} chars)")
                return all_text
                
        except TimeoutException:
            logging.warning("⚠ Timeout waiting for page elements")
        except NoSuchElementException:
            logging.warning("⚠ Required elements not found")
            
        logging.warning("✗ Content not found on page")
        return None
        
    except Exception as e:
        logging.error(f"✗ Error fetching content: {str(e)}")
        return None

def fetch_items(feed_urls):
    all_items = []
    driver = setup_driver()
    
    try:
        for feed_url in feed_urls:
            logging.info(f"\n{'='*60}")
            logging.info(f"Parsing feed: {feed_url}")
            logging.info(f"{'='*60}")
            
            feed = feedparser.parse(feed_url)
            
            for idx, entry in enumerate(feed.entries, 1):
                if not hasattr(entry, "link"):
                    continue
                
                original_link = entry.link
                archive_link = ARCHIVE_PREFIX + original_link
                
                # Fetch full article content
                full_content = fetch_article_content(driver, archive_link)
                
                # Use RSS description as fallback
                description = full_content if full_content else entry.get("description", "No content available")
                
                all_items.append({
                    "title": entry.title,
                    "link": archive_link,
                    "description": description,
                    "pubDate": entry.get("published", datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
                })
                
                logging.info(f"[{idx}/{len(feed.entries)}] Added: {entry.title[:60]}...")
                
                # Respectful delay between requests
                time.sleep(2)
                
    finally:
        driver.quit()
        logging.info(f"\n{'='*60}")
        logging.info(f"Total articles collected: {len(all_items)}")
        logging.info(f"{'='*60}")
    
    return all_items

# Test with a single article first
if __name__ == "__main__":
    logging.info("Starting RSS feed aggregation...")
    
    # Test with just one feed first
    test_feeds = [rss_feeds[0]]  # Just briefing feed
    items = fetch_items(test_feeds)
    
    logging.info(f"\n\nSample output:")
    if items:
        logging.info(f"Title: {items[0]['title']}")
        logging.info(f"Content length: {len(items[0]['description'])} characters")
        logging.info(f"First 500 chars: {items[0]['description'][:500]}...")