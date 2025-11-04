from selenium.webdriver.chrome.service import Service
def sanitize_company_id(name):
    sanitized = name.lower()
    sanitized = ''.join(c if c.isalnum() else '_' for c in sanitized)
    sanitized = '_'.join(filter(None, sanitized.split('_')))
    return sanitized
"""
Lab 1: Web Scraper for Forbes AI 50 Companies
Fetches and stores company webpages (homepage, about, product, careers, blog)
with both raw HTML and clean text versions.
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib
import requests
from bs4 import BeautifulSoup
import html2text
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

# Logging setup
LOG_DIR = "data/logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('scraper')

# Page types and paths
PAGE_PATHS = {
    'homepage': ['/'],
    'about': ['/about', '/about-us', '/team', '/company'],
    'product': ['/product', '/platform', '/products', '/services', '/solutions'],
    'careers': ['/careers', '/jobs', '/join-us', '/team'],
    'blog': ['/blog', '/news', '/insights', '/articles', '/resources']
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

html2text_converter = html2text.HTML2Text()
html2text_converter.ignore_links = False
html2text_converter.body_width = 0

def setup_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    chromedriver_path = "chromedriver/linux64/141.0.7390.65/chromedriver"  # Update path as needed
    try:
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)
        logger.info("Selenium Chrome driver initialized.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Selenium driver: {e}")
        return None

def fetch_url(url):
    try:
        logger.info(f"Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None

# Selenium fallback
def fetch_url_selenium(driver, url):
    try:
        logger.info(f"Selenium fetching: {url}")
        driver.get(url)
        time.sleep(5)  # Wait for dynamic content
        html = driver.page_source
        return html
    except WebDriverException as e:
        logger.warning(f"Selenium failed for {url}: {e}")
        return None

def extract_text(html):
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for script in soup(['script', 'style', 'meta', 'link']):
            script.decompose()
        text = soup.get_text(separator='\n', strip=True)
        text = '\n'.join([line.strip() for line in text.split('\n') if line.strip()])
        return text
    except Exception as e:
        logger.warning(f"Failed to extract text: {e}")
        return ""

def extract_links(html):
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    links_list = []
    for a in soup.find_all("a", href=True):
        url = a["href"]
        text = a.get_text(strip=True)
        key = (url, text)
        if key not in seen:
            seen.add(key)
            links_list.append({"url": url, "text": text})
    return links_list

def save_page(company_id, page_type, url, html):
    page_dir = Path(f"data/raw/{company_id}/{page_type}")
    page_dir.mkdir(parents=True, exist_ok=True)
    # Save raw HTML
    html_file = page_dir / "raw.html"
    html_file.write_text(html, encoding="utf-8")
    # Save clean text
    text = extract_text(html)
    text_file = page_dir / "clean.txt"
    text_file.write_text(text, encoding="utf-8")
    # Save links
    links = extract_links(html)
    links_file = page_dir / "links_extracted.json"
    links_file.write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")
    # Save metadata
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    metadata = {
        "source_url": url,
        "crawled_at": datetime.now().isoformat(),
        "content_hash": content_hash,
        "content_size": len(html),
        "status": "success"
    }
    metadata_file = page_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info(f"Saved {page_type} for {company_id} to {page_dir}")
    return {
        "html_file": str(html_file),
        "text_file": str(text_file),
        "links_file": str(links_file),
        "metadata_file": str(metadata_file),
        "content_hash": content_hash,
        "content_size": len(html)
    }

def save_provenance(company_id, company, page_results):
    provenance = {
        "company_name": company["company_name"],
        "website": company["website"],
        "scraped_at": datetime.now().isoformat(),
        "pages": page_results
    }
    meta_dir = Path(f"data/metadata/{company_id}")
    meta_dir.mkdir(parents=True, exist_ok=True)
    provenance_file = meta_dir / "scrape_provenance.json"
    provenance_file.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    logger.info(f"Saved provenance for {company_id}")
    return str(provenance_file)

def scrape_company(company, driver=None):
    company_id = sanitize_company_id(company["company_name"])
    logger.info(f"\n=== Scraping {company['company_name']} ({company_id}) ===")
    page_results = {}
    for page_type, paths in PAGE_PATHS.items():
        found = False
        for path in paths:
            base_url = company["website"]
            url = urljoin(base_url, path)
            html = fetch_url(url)
            used_selenium = False
            if not html and driver:
                html = fetch_url_selenium(driver, url)
                used_selenium = bool(html)
            if html:
                result = save_page(company_id, page_type, url, html)
                page_results[page_type] = {
                    "success": True,
                    "url": url,
                    "files": result,
                    "used_selenium": used_selenium
                }
                found = True
                break
            time.sleep(0.5)
        if not found:
            page_results[page_type] = {
                "success": False,
                "url": None,
                "files": None
            }
            logger.warning(f"Could not fetch {page_type} for {company_id}")
        time.sleep(1)
    # Save provenance
    save_provenance(company_id, company, page_results)
    return page_results

def main():
    seed_file = Path("data/forbes_ai50_seed_verified.json")
    if not seed_file.exists():
        logger.error(f"Seed file not found: {seed_file}")
        return
    with open(seed_file, "r", encoding="utf-8") as f:
        companies = json.load(f)
    driver = setup_selenium_driver()
    for company in companies:
        scrape_company(company, driver)
    if driver:
        driver.quit()
    logger.info("Scraping complete.")

if __name__ == "__main__":
    main()
