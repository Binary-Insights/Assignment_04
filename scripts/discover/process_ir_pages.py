#!/usr/bin/env python3
"""Process IR pages: Download HTML, extract links, and create provenance tracking.

Reads: data/discover/ir_pages.json
Creates:
- data/raw/{ticker}/html/{ticker}_ir_page.html
- data/raw/{ticker}/links/links_extracted.json  
- data/metadata/{ticker}/discover_provenance.json

Usage:
  python src/discover/process_ir_pages.py --input data/discover/ir_pages.json
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
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
    """Setup logging for process_ir_pages script."""
    # Create logs directory if it doesn't exist
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create unique logger for process_ir_pages
    logger = logging.getLogger('process_ir_pages')
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(f"{log_dir}/process_ir_pages.log")
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


def create_directory_structure(ticker):
    """Create directory structure for a company ticker."""
    logger = logging.getLogger('process_ir_pages')
    
    directories = [
        f"data/raw/{ticker}/ir_page",  # Changed to ir_page directory for complete webpage
        f"data/raw/{ticker}/links", 
        f"data/metadata/{ticker}"
    ]
    
    created_dirs = []
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            created_dirs.append(directory)
            logger.debug(f"Created directory: {directory}")
    
    if created_dirs:
        logger.info(f"Created {len(created_dirs)} directories for {ticker}")
    
    return directories


def setup_selenium_driver():
    """Setup Chrome driver with options for webpage saving."""
    logger = logging.getLogger('process_ir_pages')
    logger.info("Setting up Selenium Chrome driver")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Disable images and CSS for faster loading (optional)
    # chrome_options.add_argument("--disable-images")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)  # 60 second timeout
        logger.info("Chrome driver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        raise


def download_webpage_with_selenium(driver, url, ticker):
    """Download complete webpage using Selenium, similar to browser 'Save Page As'."""
    logger = logging.getLogger('process_ir_pages')
    logger.info(f"Loading webpage with Selenium: {url}")
    
    try:
        # Navigate to the page
        driver.get(url)
        
        # Wait for page to load
        logger.info("Waiting for page to load completely...")
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # Additional wait for dynamic content
        time.sleep(5)
        
        # Get final URL after redirects
        final_url = driver.current_url
        logger.info(f"Page loaded successfully, final URL: {final_url}")
        
        # Get page source (fully rendered HTML)
        page_source = driver.page_source
        page_title = driver.title
        
        logger.info(f"Retrieved rendered HTML (size: {len(page_source)} chars, title: '{page_title}')")
        
        # Create webpage directory
        webpage_dir = f"data/raw/{ticker}/ir_page"
        os.makedirs(webpage_dir, exist_ok=True)
        
        # Save main HTML file
        main_html_file = f"{webpage_dir}/index.html"
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
            'title': page_title,
            'download_timestamp': datetime.now().isoformat(),
            'main_html_file': main_html_file,
            'content_hash': content_hash,
            'content_size': len(page_source),
            'saved_resources': saved_resources
        }
        
        metadata_file = f"{webpage_dir}/webpage_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(webpage_metadata, f, indent=2)
        
        logger.info(f"Saved webpage metadata to: {metadata_file}")
        
        return {
            'success': True,
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
            'error': 'Page load timeout',
            'download_timestamp': datetime.now().isoformat()
        }
    except WebDriverException as e:
        logger.error(f"WebDriver error loading {url}: {e}")
        return {
            'success': False,
            'error': f'WebDriver error: {str(e)}',
            'download_timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Unexpected error loading webpage {url}: {e}")
        return {
            'success': False,
            'error': str(e),
            'download_timestamp': datetime.now().isoformat()
        }


def save_webpage_resources(driver, webpage_dir, base_url):
    """Save CSS, JS, and image resources referenced in the page."""
    logger = logging.getLogger('process_ir_pages')
    logger.info("Attempting to save webpage resources...")
    
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
        
        logger.info(f"Saved {len(saved_resources)} webpage resources")
        
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


def extract_links_from_html(html_file, ticker):
    """Extract links from HTML file, similar to extract_links.py logic."""
    logger = logging.getLogger('process_ir_pages')
    logger.info(f"Extracting links from: {html_file}")
    
    try:
        # Read the HTML file
        with open(html_file, "r", encoding="utf-8", errors='ignore') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, "lxml")
        
        # Use a set to track seen (url, text) pairs - same logic as extract_links.py
        seen = set()
        links_list = []
        
        for a in soup.find_all("a", href=True):
            url = a["href"]
            text = a.get_text(strip=True)
            key = (url, text)
            
            if key not in seen:
                seen.add(key)
                links_list.append({"url": url, "text": text})
        
        # Save links to JSON file
        links_filename = f"data/raw/{ticker}/links/links_extracted.json"
        with open(links_filename, "w", encoding="utf-8") as f:
            json.dump(links_list, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Extracted {len(links_list)} unique links, saved to: {links_filename}")
        
        return {
            'success': True,
            'links_count': len(links_list),
            'links_file': links_filename,
            'extraction_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to extract links from {html_file}: {e}")
        return {
            'success': False,
            'error': str(e),
            'extraction_timestamp': datetime.now().isoformat()
        }


def extract_links_from_selenium(driver, ticker):
    """Extract links directly from Selenium driver (rendered page)."""
    logger = logging.getLogger('process_ir_pages')
    logger.info("Extracting links from rendered page via Selenium")
    
    try:
        # Get all anchor elements with href
        link_elements = driver.find_elements(By.TAG_NAME, "a")
        
        # Use a set to track seen (url, text) pairs - same logic as extract_links.py
        seen = set()
        links_list = []
        
        for element in link_elements:
            try:
                url = element.get_attribute("href")
                text = element.text.strip()
                
                if url:  # Only process if href exists
                    key = (url, text)
                    
                    if key not in seen:
                        seen.add(key)
                        links_list.append({"url": url, "text": text})
            except Exception as e:
                logger.debug(f"Error extracting link: {e}")
                continue
        
        # Save links to JSON file
        links_filename = f"data/raw/{ticker}/links/links_extracted.json"
        with open(links_filename, "w", encoding="utf-8") as f:
            json.dump(links_list, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Extracted {len(links_list)} unique links from rendered page, saved to: {links_filename}")
        
        return {
            'success': True,
            'links_count': len(links_list),
            'links_file': links_filename,
            'extraction_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to extract links from rendered page: {e}")
        return {
            'success': False,
            'error': str(e),
            'extraction_timestamp': datetime.now().isoformat()
        }


def filter_pdf_links(ticker):
    """Filter PDF links from extracted links and save separately."""
    logger = logging.getLogger('process_ir_pages')
    logger.info(f"Filtering PDF links for {ticker}")
    
    links_file = f"data/raw/{ticker}/links/links_extracted.json"
    
    try:
        # Read the extracted links
        with open(links_file, 'r', encoding='utf-8') as f:
            all_links = json.load(f)
        
        logger.debug(f"Loaded {len(all_links)} total links from {links_file}")
        
        # Filter PDF links using multiple criteria
        pdf_links = []
        pdf_patterns = [
            '.pdf',
            '.PDF',
            'filetype=pdf',
            'format=pdf',
            '/pdf/',
            'annual-report',
            '10-k',
            '10-q',
            '8-k',
            'quarterly-report',
            'earnings-report',
            'financial-report'
        ]
        
        for link in all_links:
            url = link.get('url', '').lower()
            text = link.get('text', '').lower()
            
            # Check if URL contains PDF indicators
            is_pdf_url = any(pattern.lower() in url for pattern in pdf_patterns)
            
            # Check if link text suggests PDF content
            pdf_text_indicators = [
                'pdf', 'download', 'report', 'annual', 'quarterly', 'earnings',
                '10-k', '10-q', '8-k', 'sec filing', 'financial', 'investor packet'
            ]
            is_pdf_text = any(indicator in text for indicator in pdf_text_indicators)
            
            # Include if either URL or text suggests PDF
            if is_pdf_url or (is_pdf_text and len(text) > 0):
                pdf_links.append({
                    'url': link['url'],
                    'text': link['text'],
                    'classification': {
                        'pdf_url_match': is_pdf_url,
                        'pdf_text_match': is_pdf_text,
                        'confidence': 'high' if is_pdf_url else 'medium'
                    }
                })
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_pdf_links = []
        for link in pdf_links:
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_pdf_links.append(link)
        
        # Save PDF links to separate file
        pdf_links_file = f"data/raw/{ticker}/links/pdf_links.json"
        with open(pdf_links_file, 'w', encoding='utf-8') as f:
            json.dump(unique_pdf_links, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Filtered {len(unique_pdf_links)} PDF links from {len(all_links)} total links")
        logger.info(f"Saved PDF links to: {pdf_links_file}")
        
        # Log some examples of found PDF links
        high_confidence = [link for link in unique_pdf_links if link['classification']['confidence'] == 'high']
        if high_confidence:
            logger.debug(f"High confidence PDF links found:")
            for i, link in enumerate(high_confidence[:3], 1):
                logger.debug(f"  {i}. {link['url'][:60]}... ({link['text'][:30]}...)")
        
        return {
            'success': True,
            'total_links': len(all_links),
            'pdf_links_count': len(unique_pdf_links),
            'high_confidence_count': len(high_confidence),
            'pdf_links_file': pdf_links_file,
            'filtering_timestamp': datetime.now().isoformat()
        }
        
    except FileNotFoundError:
        logger.error(f"Links file not found: {links_file}")
        return {
            'success': False,
            'error': f'Links file not found: {links_file}',
            'filtering_timestamp': datetime.now().isoformat()
        }
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in links file {links_file}: {e}")
        return {
            'success': False,
            'error': f'Invalid JSON in links file: {e}',
            'filtering_timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error filtering PDF links for {ticker}: {e}")
        return {
            'success': False,
            'error': str(e),
            'filtering_timestamp': datetime.now().isoformat()
        }


def create_provenance_record(ticker, ir_page_info, download_result, extraction_result, pdf_filtering_result=None):
    """Create provenance record for the processing."""
    logger = logging.getLogger('process_ir_pages')
    
    provenance = {
        'company': {
            'ticker': ticker,
            'name': ir_page_info.get('name'),
            'homepage': ir_page_info.get('homepage'),
            'ir_page': ir_page_info.get('ir_page')
        },
        'processing': {
            'script': 'process_ir_pages.py',
            'version': '1.1',
            'timestamp': datetime.now().isoformat(),
            'process_id': os.getpid()
        },
        'validation': ir_page_info.get('validation', {}),
        'download': download_result,
        'link_extraction': extraction_result,
        'pdf_filtering': pdf_filtering_result or {'success': False, 'reason': 'Not performed'},
        'files_created': []
    }
    
    # Add created files to provenance
    if download_result.get('success'):
        provenance['files_created'].append({
            'type': 'webpage',
            'path': download_result.get('webpage_dir'),
            'main_html': download_result.get('main_html_file'),
            'size_bytes': download_result.get('content_length'),
            'hash': download_result.get('content_hash'),
            'saved_resources': download_result.get('saved_resources_count', 0)
        })
    
    if extraction_result.get('success'):
        provenance['files_created'].append({
            'type': 'links_json',
            'path': extraction_result.get('links_file'),
            'links_count': extraction_result.get('links_count')
        })
    
    if pdf_filtering_result and pdf_filtering_result.get('success'):
        provenance['files_created'].append({
            'type': 'pdf_links_json',
            'path': pdf_filtering_result.get('pdf_links_file'),
            'pdf_links_count': pdf_filtering_result.get('pdf_links_count'),
            'high_confidence_count': pdf_filtering_result.get('high_confidence_count')
        })
    
    # Save provenance file
    provenance_file = f"data/metadata/{ticker}/discover_provenance.json"
    with open(provenance_file, 'w', encoding='utf-8') as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Created provenance record: {provenance_file}")
    return provenance_file


def process_company(company_data, driver):
    """Process a single company's IR page using Selenium."""
    logger = logging.getLogger('process_ir_pages')
    
    ticker = company_data.get('ticker', 'UNKNOWN')
    name = company_data.get('name', 'UNKNOWN')
    ir_page = company_data.get('ir_page')
    
    logger.info(f"=== Processing {ticker} ({name}) ===")
    
    if not ir_page:
        logger.warning(f"No IR page found for {ticker}, skipping")
        return {
            'ticker': ticker,
            'success': False,
            'reason': 'No IR page available'
        }
    
    try:
        # Create directory structure
        create_directory_structure(ticker)
        
        # Download webpage with Selenium
        logger.info(f"Step 1: Downloading webpage with Selenium for {ticker}")
        download_result = download_webpage_with_selenium(driver, ir_page, ticker)
        
        # Extract links from rendered page
        extraction_result = {'success': False}
        if download_result.get('success'):
            logger.info(f"Step 2: Extracting links from rendered page for {ticker}")
            extraction_result = extract_links_from_selenium(driver, ticker)
        else:
            logger.warning(f"Skipping link extraction for {ticker} due to webpage download failure")
        
        # Filter PDF links (only if link extraction succeeded)
        pdf_filtering_result = {'success': False}
        if extraction_result.get('success'):
            logger.info(f"Step 3: Filtering PDF links for {ticker}")
            pdf_filtering_result = filter_pdf_links(ticker)
        else:
            logger.warning(f"Skipping PDF filtering for {ticker} due to link extraction failure")
        
        # Create provenance record
        logger.info(f"Step 4: Creating provenance record for {ticker}")
        provenance_file = create_provenance_record(ticker, company_data, download_result, extraction_result, pdf_filtering_result)
        
        success = (download_result.get('success', False) and 
                  extraction_result.get('success', False) and 
                  pdf_filtering_result.get('success', False))
        logger.info(f"=== Completed {ticker}: {'SUCCESS' if success else 'PARTIAL/FAILED'} ===")
        
        return {
            'ticker': ticker,
            'success': success,
            'download_success': download_result.get('success', False),
            'extraction_success': extraction_result.get('success', False),
            'pdf_filtering_success': pdf_filtering_result.get('success', False),
            'links_count': extraction_result.get('links_count', 0),
            'pdf_links_count': pdf_filtering_result.get('pdf_links_count', 0),
            'saved_resources': download_result.get('saved_resources_count', 0),
            'provenance_file': provenance_file
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing {ticker}: {e}")
        return {
            'ticker': ticker,
            'success': False,
            'error': str(e)
        }


def load_ir_pages(input_file):
    """Load IR pages data from JSON file."""
    logger = logging.getLogger('process_ir_pages')
    logger.info(f"Loading IR pages from: {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter out companies without IR pages
        valid_companies = [company for company in data if company.get('ir_page')]
        skipped = len(data) - len(valid_companies)
        
        logger.info(f"Loaded {len(data)} companies, {len(valid_companies)} have IR pages")
        if skipped > 0:
            logger.warning(f"Skipped {skipped} companies without IR pages")
        
        return valid_companies
        
    except Exception as e:
        logger.error(f"Failed to load IR pages from {input_file}: {e}")
        raise


def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Starting IR Pages Processing ===")
    
    parser = argparse.ArgumentParser(description="Process IR pages: download HTML and extract links")
    parser.add_argument("--input", default="data/discover/ir_pages.json", help="Input JSON file with IR pages")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    parser.add_argument("--tickers", nargs='+', help="Specific tickers to process (e.g., --tickers NVDA AAPL MSFT)")
    parser.add_argument("--limit", type=int, help="Limit number of companies to process")
    args = parser.parse_args()
    
    logger.info(f"Arguments: input={args.input}, delay={args.delay}, tickers={args.tickers}, limit={args.limit}")
    
    try:
        # Load IR pages data
        companies = load_ir_pages(args.input)
        
        if not companies:
            logger.warning("No companies with IR pages found, exiting")
            return
        
        # Filter by specific tickers if provided
        if args.tickers:
            companies = [c for c in companies if c.get('ticker') in args.tickers]
            logger.info(f"Filtered to {len(companies)} companies based on tickers: {args.tickers}")
        
        # Limit number of companies if specified
        if args.limit and args.limit > 0:
            companies = companies[:args.limit]
            logger.info(f"Limited to first {len(companies)} companies")
        
        if not companies:
            logger.warning("No companies to process after filtering, exiting")
            return
        
        # Setup Selenium driver
        logger.info("Initializing Selenium WebDriver")
        driver = setup_selenium_driver()
        
        try:
            # Process each company
            results = []
            successful = 0
            failed = 0
            
            logger.info(f"=== Processing {len(companies)} companies ===")
            
            for i, company in enumerate(companies, 1):
                ticker = company.get('ticker', f'COMPANY_{i}')
                logger.info(f"Processing {i}/{len(companies)}: {ticker}")
                
                result = process_company(company, driver)
                results.append(result)
                
                if result['success']:
                    successful += 1
                    logger.info(f"  ✓ Success: {result['links_count']} links, {result.get('pdf_links_count', 0)} PDFs, {result.get('saved_resources', 0)} resources")
                else:
                    failed += 1
                    error_msg = result.get('error', result.get('reason', 'Unknown error'))
                    logger.warning(f"  ✗ Failed: {error_msg}")
                    
                    # Log partial successes
                    if result.get('download_success'):
                        logger.info(f"    - Webpage download: SUCCESS")
                    if result.get('extraction_success'):
                        logger.info(f"    - Link extraction: SUCCESS ({result.get('links_count', 0)} links)")
                    if result.get('pdf_filtering_success'):
                        logger.info(f"    - PDF filtering: SUCCESS ({result.get('pdf_links_count', 0)} PDFs)")
                
                # Delay between requests
                if i < len(companies):
                    logger.debug(f"Sleeping for {args.delay} seconds")
                    time.sleep(args.delay)
        
        finally:
            # Always close the driver
            logger.info("Closing Selenium WebDriver")
            driver.quit()
        
        # Final summary
        logger.info("=== PROCESSING COMPLETE ===")
        logger.info(f"Total companies: {len(companies)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        
        # Log any failures
        failed_companies = [r for r in results if not r['success']]
        if failed_companies:
            logger.warning("Failed companies:")
            for result in failed_companies:
                reason = result.get('reason') or result.get('error', 'Unknown error')
                logger.warning(f"  {result['ticker']}: {reason}")
        
        print(f"\n=== Summary ===")
        print(f"Processed: {len(companies)} companies")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Check logs: data/logs/process_ir_pages.log")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()