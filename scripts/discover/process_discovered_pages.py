#!/usr/bin/env python3
"""Process discovered company pages: Download HTML, extract links, and create provenance tracking.

Reads: data/company_pages_discovered.json
Creates:
- data/raw/{company_slug}/{page_type}/{page_type}.html
- data/raw/{company_slug}/{page_type}/links_extracted.json  
- data/metadata/{company_slug}/discovered_pages_provenance.json

Usage:
  python scripts/discover/process_discovered_pages.py --input data/company_pages_discovered.json
  python scripts/discover/process_discovered_pages.py --companies World Labs --delay 2.0
"""

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import urlparse, urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def setup_logging():
    """Setup logging for process_discovered_pages script."""
    # Create logs directory if it doesn't exist
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create unique logger for process_discovered_pages
    logger = logging.getLogger('process_discovered_pages')
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(f"{log_dir}/process_discovered_pages.log")
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def slugify(text):
    """Convert text to slug format (lowercase, underscores instead of spaces)."""
    return text.lower().replace(' ', '_').replace('-', '_')


def create_directory_structure(company_slug, page_types=None):
    """Create directory structure for a company."""
    logger = logging.getLogger('process_discovered_pages')
    
    if page_types is None:
        page_types = ['about', 'product', 'careers', 'blog']
    
    directories = [
        f"data/raw/{company_slug}/{page_type}" for page_type in page_types
    ]
    directories.append(f"data/metadata/{company_slug}")
    
    created_dirs = []
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            created_dirs.append(directory)
            logger.debug(f"Created directory: {directory}")
    
    if created_dirs:
        logger.info(f"Created {len(created_dirs)} directories for {company_slug}")
    
    return directories


def setup_selenium_driver():
    """Setup Chrome driver with options for webpage saving."""
    logger = logging.getLogger('process_discovered_pages')
    logger.info("Setting up Selenium Chrome driver")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)  # 60 second timeout
        logger.info("Chrome driver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        raise


def download_webpage_with_selenium(driver, url, company_slug, page_type):
    """Download complete webpage using Selenium, similar to browser 'Save Page As'."""
    logger = logging.getLogger('process_discovered_pages')
    logger.info(f"Loading webpage with Selenium: {url} ({page_type})")
    
    try:
        # Navigate to the page
        driver.get(url)
        
        # Wait for page to load
        logger.info("Waiting for page to load completely...")
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # Additional wait for dynamic content
        time.sleep(2)
        
        # Get final URL after redirects
        final_url = driver.current_url
        logger.info(f"Page loaded successfully, final URL: {final_url}")
        
        # Get page source (fully rendered HTML)
        page_source = driver.page_source
        page_title = driver.title
        
        logger.info(f"Retrieved rendered HTML (size: {len(page_source)} chars, title: '{page_title}')")
        
        # Create webpage directory
        webpage_dir = f"data/raw/{company_slug}/{page_type}"
        os.makedirs(webpage_dir, exist_ok=True)
        
        # Save main HTML file with page type name
        main_html_file = f"{webpage_dir}/{page_type}.html"
        with open(main_html_file, 'w', encoding='utf-8') as f:
            f.write(page_source)
        
        logger.info(f"Saved main HTML to: {main_html_file}")
        
        # Calculate content hash
        content_hash = hashlib.sha256(page_source.encode('utf-8')).hexdigest()
        
        # Try to save additional resources (CSS, JS, images)
        saved_resources = save_webpage_resources(driver, webpage_dir, final_url)
        
        # Create a metadata file for the webpage
        webpage_metadata = {
            'original_url': url,
            'final_url': final_url,
            'page_type': page_type,
            'title': page_title,
            'download_timestamp': datetime.now().isoformat(),
            'main_html_file': main_html_file,
            'content_hash': content_hash,
            'content_size': len(page_source),
            'saved_resources': saved_resources
        }
        
        metadata_file = f"{webpage_dir}/{page_type}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(webpage_metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved webpage metadata to: {metadata_file}")
        
        return {
            'success': True,
            'page_type': page_type,
            'final_url': final_url,
            'title': page_title,
            'content_length': len(page_source),
            'content_hash': content_hash,
            'webpage_dir': webpage_dir,
            'main_html_file': main_html_file,
            'metadata_file': metadata_file,
            'saved_resources_count': len(saved_resources),
            'download_timestamp': datetime.now().isoformat()
        }
        
    except TimeoutException:
        logger.error(f"Timeout loading page: {url}")
        return {
            'success': False,
            'page_type': page_type,
            'error': 'Page load timeout',
            'download_timestamp': datetime.now().isoformat()
        }
    except WebDriverException as e:
        logger.error(f"WebDriver error loading {url}: {e}")
        return {
            'success': False,
            'page_type': page_type,
            'error': f'WebDriver error: {str(e)}',
            'download_timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Unexpected error loading webpage {url}: {e}")
        return {
            'success': False,
            'page_type': page_type,
            'error': str(e),
            'download_timestamp': datetime.now().isoformat()
        }


def save_webpage_resources(driver, webpage_dir, base_url):
    """Save CSS, JS, and image resources referenced in the page."""
    logger = logging.getLogger('process_discovered_pages')
    logger.debug("Attempting to save webpage resources...")
    
    saved_resources = []
    
    try:
        # Create subdirectories for resources
        css_dir = f"{webpage_dir}/css"
        js_dir = f"{webpage_dir}/js"
        images_dir = f"{webpage_dir}/images"
        
        for dir_path in [css_dir, js_dir, images_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        # Get all CSS links
        css_links = driver.find_elements(By.TAG_NAME, "link")
        for link in css_links:
            try:
                rel = link.get_attribute("rel")
                href = link.get_attribute("href")
                if rel == "stylesheet" and href:
                    resource_url = urljoin(base_url, href)
                    filename = os.path.basename(urlparse(href).path) or "style.css"
                    saved_file = download_resource(resource_url, f"{css_dir}/{filename}")
                    if saved_file:
                        saved_resources.append({"type": "css", "url": resource_url, "file": saved_file})
            except Exception as e:
                logger.debug(f"Failed to save CSS resource: {e}")
        
        # Get all script sources
        script_tags = driver.find_elements(By.TAG_NAME, "script")
        for script in script_tags:
            try:
                src = script.get_attribute("src")
                if src:
                    resource_url = urljoin(base_url, src)
                    filename = os.path.basename(urlparse(src).path) or "script.js"
                    saved_file = download_resource(resource_url, f"{js_dir}/{filename}")
                    if saved_file:
                        saved_resources.append({"type": "js", "url": resource_url, "file": saved_file})
            except Exception as e:
                logger.debug(f"Failed to save JS resource: {e}")
        
        # Get all images
        img_tags = driver.find_elements(By.TAG_NAME, "img")
        for img in img_tags[:10]:  # Limit to first 10 images to avoid too many downloads
            try:
                src = img.get_attribute("src")
                if src and not src.startswith("data:"):  # Skip data URLs
                    resource_url = urljoin(base_url, src)
                    filename = os.path.basename(urlparse(src).path) or "image.png"
                    saved_file = download_resource(resource_url, f"{images_dir}/{filename}")
                    if saved_file:
                        saved_resources.append({"type": "image", "url": resource_url, "file": saved_file})
            except Exception as e:
                logger.debug(f"Failed to save image resource: {e}")
        
        logger.debug(f"Saved {len(saved_resources)} webpage resources")
        
    except Exception as e:
        logger.warning(f"Error saving webpage resources: {e}")
    
    return saved_resources


def download_resource(url, filepath):
    """Download a single resource file."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        return filepath
    except Exception:
        return None


def extract_links_from_html(html_file, company_slug, page_type):
    """Extract links from HTML file."""
    logger = logging.getLogger('process_discovered_pages')
    logger.info(f"Extracting links from: {html_file}")
    
    try:
        # Read the HTML file
        with open(html_file, "r", encoding="utf-8", errors='ignore') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, "lxml")
        
        # Use a set to track seen (url, text) pairs
        seen = set()
        links_list = []
        
        for a in soup.find_all("a", href=True):
            url = a['href'].strip()
            text = a.get_text(strip=True)
            
            if url and (url, text) not in seen:
                links_list.append({'url': url, 'text': text})
                seen.add((url, text))
        
        # Save links to JSON file
        links_filename = f"data/raw/{company_slug}/{page_type}/links_extracted.json"
        with open(links_filename, "w", encoding="utf-8") as f:
            json.dump(links_list, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Extracted {len(links_list)} unique links, saved to: {links_filename}")
        
        return {
            'success': True,
            'page_type': page_type,
            'links_count': len(links_list),
            'links_file': links_filename,
            'extraction_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to extract links from {html_file}: {e}")
        return {
            'success': False,
            'page_type': page_type,
            'error': str(e),
            'extraction_timestamp': datetime.now().isoformat()
        }


def create_provenance_record(company_name, company_slug, pages_results):
    """Create provenance record for the processing."""
    logger = logging.getLogger('process_discovered_pages')
    
    provenance = {
        'company': {
            'name': company_name,
            'slug': company_slug,
            'website': ''  # Will be updated if available
        },
        'processing': {
            'script': 'process_discovered_pages.py',
            'version': '1.0',
            'timestamp': datetime.now().isoformat(),
            'process_id': os.getpid()
        },
        'pages_processed': pages_results,
        'files_created': [],
        'summary': {
            'total_pages': len(pages_results),
            'successful_downloads': sum(1 for r in pages_results if r.get('download_success')),
            'successful_extractions': sum(1 for r in pages_results if r.get('extraction_success')),
            'total_links_extracted': sum(r.get('links_count', 0) for r in pages_results if r.get('extraction_success'))
        }
    }
    
    # Add created files to provenance
    for page_result in pages_results:
        if page_result.get('download_success'):
            provenance['files_created'].append({
                'type': 'webpage_html',
                'page_type': page_result.get('page_type'),
                'path': page_result.get('main_html_file'),
                'size_bytes': page_result.get('content_length'),
                'hash': page_result.get('content_hash')
            })
        
        if page_result.get('extraction_success'):
            provenance['files_created'].append({
                'type': 'links_json',
                'page_type': page_result.get('page_type'),
                'path': page_result.get('links_file'),
                'links_count': page_result.get('links_count')
            })
    
    # Save provenance file
    provenance_file = f"data/metadata/{company_slug}/discovered_pages_provenance.json"
    with open(provenance_file, 'w', encoding='utf-8') as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Created provenance record: {provenance_file}")
    return provenance_file


def process_company_pages(company_data, driver):
    """Process all discovered pages for a single company."""
    logger = logging.getLogger('process_discovered_pages')
    
    company_name = company_data.get('company_name', 'UNKNOWN')
    company_slug = slugify(company_name)
    website = company_data.get('website', '')
    discovered_pages = company_data.get('discovered_pages', {})
    
    logger.info(f"=== Processing {company_name} ===")
    logger.info(f"Website: {website}")
    
    if not discovered_pages:
        logger.warning(f"No discovered pages found for {company_name}, skipping")
        return {
            'company_name': company_name,
            'company_slug': company_slug,
            'success': False,
            'reason': 'No discovered pages available'
        }
    
    try:
        # Create directory structure
        page_types = [page_type for page_type in discovered_pages.keys() if discovered_pages[page_type]]
        create_directory_structure(company_slug, page_types)
        
        pages_results = []
        
        # Process each page type
        for page_type, pages in discovered_pages.items():
            if not pages:
                logger.info(f"  No pages found for {page_type}")
                continue
            
            logger.info(f"  Processing {page_type} pages ({len(pages)} found)...")
            
            # Process the first/primary page for this type
            page_info = pages[0]  # Get the first page (usually the primary one)
            page_url = page_info.get('url')
            
            if not page_url:
                logger.warning(f"  No URL found for {page_type}, skipping")
                pages_results.append({
                    'page_type': page_type,
                    'success': False,
                    'reason': 'No URL available'
                })
                continue
            
            logger.info(f"  Step 1: Downloading {page_type} page from {page_url}")
            download_result = download_webpage_with_selenium(driver, page_url, company_slug, page_type)
            
            page_result = {
                'page_type': page_type,
                'url': page_url,
                'download_success': download_result.get('success', False),
                'download_timestamp': download_result.get('download_timestamp')
            }
            
            # Extract links from downloaded page
            extraction_result = {'success': False}
            if download_result.get('success'):
                logger.info(f"  Step 2: Extracting links from {page_type} page")
                html_file = download_result.get('main_html_file')
                extraction_result = extract_links_from_html(html_file, company_slug, page_type)
                page_result['extraction_success'] = extraction_result.get('success', False)
                page_result['links_count'] = extraction_result.get('links_count', 0)
                page_result['links_file'] = extraction_result.get('links_file')
            else:
                logger.warning(f"  Skipping link extraction for {page_type} due to download failure")
                page_result['extraction_success'] = False
                page_result['links_count'] = 0
            
            page_result['success'] = page_result['download_success'] and page_result['extraction_success']
            
            if page_result.get('success'):
                logger.info(f"  ✓ {page_type.upper()}: SUCCESS ({page_result.get('links_count')} links)")
            else:
                logger.info(f"  ✗ {page_type.upper()}: FAILED")
            
            pages_results.append(page_result)
    
        # Create provenance record
        logger.info(f"Step 3: Creating provenance record for {company_name}")
        provenance_file = create_provenance_record(company_name, company_slug, pages_results)
        
        overall_success = all(r.get('success', False) for r in pages_results)
        logger.info(f"=== Completed {company_name}: {'SUCCESS' if overall_success else 'PARTIAL/FAILED'} ===")
        
        return {
            'company_name': company_name,
            'company_slug': company_slug,
            'success': overall_success,
            'pages_processed': len(pages_results),
            'pages_results': pages_results,
            'provenance_file': provenance_file
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing {company_name}: {e}")
        return {
            'company_name': company_name,
            'company_slug': company_slug,
            'success': False,
            'error': str(e)
        }


def load_discovered_pages(input_file):
    """Load discovered pages data from JSON file."""
    logger = logging.getLogger('process_discovered_pages')
    logger.info(f"Loading discovered pages from: {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded {len(data)} companies from {input_file}")
        return data
        
    except Exception as e:
        logger.error(f"Failed to load discovered pages from {input_file}: {e}")
        raise


def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Starting Discovered Pages Processing ===")
    
    # Hardcoded configuration
    input_file = "data/company_pages_discovered.json"
    companies_to_process = None  # Process all companies, or set to list like ['World Labs']
    limit = None  # No limit, or set to a number like 5
    
    logger.info(f"Configuration: input={input_file}, companies={companies_to_process}, limit={limit}")
    
    try:
        # Load discovered pages
        companies = load_discovered_pages(input_file)
        
        # Filter by specific companies if requested
        if companies_to_process:
            companies = [c for c in companies if c.get('company_name') in companies_to_process]
            logger.info(f"Filtered to {len(companies)} specified companies")
        
        # Apply limit if specified
        if limit:
            companies = companies[:limit]
            logger.info(f"Limited to {len(companies)} companies")
        
        if not companies:
            logger.warning("No companies to process")
            return
        
        # Initialize Selenium WebDriver
        logger.info(f"Initializing Selenium WebDriver")
        driver = setup_selenium_driver()
        
        try:
            logger.info(f"=== Processing {len(companies)} companies ===")
            
            results = []
            for idx, company in enumerate(companies, 1):
                logger.info(f"Processing {idx}/{len(companies)}: {company.get('company_name')}")
                result = process_company_pages(company, driver)
                results.append(result)
            
            # Summarize results
            logger.info("\n=== PROCESSING COMPLETE ===")
            logger.info(f"Total companies: {len(results)}")
            
            successful = [r for r in results if r.get('success')]
            partial = [r for r in results if not r.get('success') and r.get('pages_processed', 0) > 0]
            failed = [r for r in results if not r.get('success') and r.get('pages_processed', 0) == 0]
            
            logger.info(f"Fully successful: {len(successful)}")
            logger.info(f"Partially successful: {len(partial)}")
            logger.info(f"Failed: {len(failed)}")
            
            if successful:
                logger.info("\nSuccessful companies:")
                for r in successful:
                    logger.info(f"  ✓ {r.get('company_name')}")
            
            if partial:
                logger.info("\nPartially successful companies:")
                for r in partial:
                    pages = r.get('pages_results', [])
                    successful_pages = sum(1 for p in pages if p.get('success'))
                    logger.info(f"  ◐ {r.get('company_name')}: {successful_pages}/{len(pages)} pages")
            
            if failed:
                logger.info("\nFailed companies:")
                for r in failed:
                    logger.info(f"  ✗ {r.get('company_name')}: {r.get('reason', 'Unknown error')}")
        
        finally:
            logger.info("Closing Selenium WebDriver")
            driver.quit()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
