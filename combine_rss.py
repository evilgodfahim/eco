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
from webdriver_manager.chrome import ChromeDriverManager
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
    
    # Use webdriver-manager to automatically get the correct driver version
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_article_content(driver, url):
    try:
        logging.info(f"Fetching content from: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 15)
        
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)
            
            # Try Economist-specific selectors
            selectors = [
                "article[data-test-id='Article']",
                "article",
                "div[class*='article']",
                "div[class*='ds-layout-grid']",
                "section[class*='article']",
                "main"
            ]
            
            content = None
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        text = elements[0].text
                        if text and len(text) > 200:
                            logging.info(f"✓ Content found using: {selector} ({len(text)} chars)")
                            return text
                except:
                    continue
            
            # Fallback: Extract paragraphs
            logging.info("Trying paragraph extraction...")
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            
            content_paragraphs = []
            for p in paragraphs:
                text = p.text.strip()
                if len(text) > 50:
                    content_paragraphs.append(text)
            
            if content_paragraphs:
                content = "\n\n".join(content_paragraphs)
                logging.info(f"✓ Extracted {len(content_paragraphs)} paragraphs ({len(content)} chars)")
                return content
            
            # Last resort: body text
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
                
                full_content = fetch_article_content(driver, archive_link)
                
                description = full_content if full_content else entry.get("description", "No content available")
                
                all_items.append({
                    "title": entry.title,
                    "link": archive_link,
                    "description": description,
                    "pubDate": entry.get("published", datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
                })
                
                logging.info(f"[{idx}/{len(feed.entries)}] Added: {entry.title[:60]}...")
                
                time.sleep(2)
                
    finally:
        driver.quit()
        logging.info(f"\n{'='*60}")
        logging.info(f"Total articles collected: {len(all_items)}")
        logging.info(f"{'='*60}")
    
    return all_items

def generate_rss(items, output_file="combined.xml"):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "Combined Economist RSS Feed"
    ET.SubElement(channel, "link").text = "https://www.economist.com"
    ET.SubElement(channel, "description").text = "Aggregated articles from The Economist"
    
    for item in items:
        item_elem = ET.SubElement(channel, "item")
        ET.SubElement(item_elem, "title").text = item["title"]
        ET.SubElement(item_elem, "link").text = item["link"]
        ET.SubElement(item_elem, "description").text = item["description"]
        ET.SubElement(item_elem, "pubDate").text = item["pubDate"]
    
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    logging.info(f"RSS feed written to {output_file}")

if __name__ == "__main__":
    logging.info("Starting RSS feed aggregation...")
    
    # Use all feeds
    items = fetch_items(rss_feeds)
    
    if items:
        generate_rss(items)
        logging.info(f"✓ Successfully generated RSS feed with {len(items)} articles")
    else:
        logging.error("✗ No items collected")