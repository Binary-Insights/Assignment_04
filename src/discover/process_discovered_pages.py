#!/usr/bin/env python3
"""Process company pages: Download HTML, extract links, and create provenance tracking.

Reads: data/company_pages.json (contains: homepage, about, product, careers, blog, linkedin)
Creates:
- data/raw/{company_slug}/{page_type}/{page_type}.html
- data/raw/{company_slug}/{page_type}/links_extracted.json  
- data/metadata/{company_slug}/discovered_pages_provenance.json

Usage:
  python src/discover/process_discovered_pages.py
  python src/discover/process_discovered_pages.py --companies World Labs --delay 2.0
"""

import argparse
import hashlib
import json
import logging
import os
import re
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
    
    # Disable Selenium's automatic chromedriver download
    os.environ['WDM_LOG'] = '0'
    os.environ['WDM_LOCAL'] = '1'
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Set Chrome binary path - use system installation
    chrome_bin = os.getenv('CHROME_BIN', '/usr/bin/chromium')
    logger.info(f"Using Chrome binary: {chrome_bin}")
    chrome_options.binary_location = chrome_bin
    
    try:
        # Use explicit ChromeDriver path - must use system installation
        chromedriver_path = os.getenv('CHROMEDRIVER_PATH', '/usr/bin/chromedriver')
        
        logger.info(f"Attempting to use ChromeDriver from: {chromedriver_path}")
        logger.info(f"ChromeDriver exists: {os.path.exists(chromedriver_path)}")
        
        # Create Service object with explicit path (disables automatic download)
        service = webdriver.chrome.service.Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.set_page_load_timeout(60)  # 60 second timeout
        logger.info("✓ Chrome driver initialized successfully")
        return driver
    except FileNotFoundError as e:
        logger.error(f"❌ ChromeDriver file not found: {chromedriver_path}")
        logger.error(f"  Make sure chromium-driver is installed in the container")
        raise
    except Exception as e:
        logger.error(f"❌ Failed to initialize Chrome driver: {e}")
        logger.error(f"  ChromeDriver path: {os.getenv('CHROMEDRIVER_PATH', '/usr/bin/chromedriver')}")
        logger.error(f"  Chrome binary: {os.getenv('CHROME_BIN', '/usr/bin/chromium')}")
        raise


def download_webpage_with_selenium(driver, url, company_slug, page_type):
    """Download complete webpage using Selenium, similar to browser 'Save Page As'.
    
    This function:
    1. Downloads and renders the complete webpage
    2. Saves all resources (CSS, JS, images, fonts, etc.)
    3. Rewrites URLs in HTML to point to local resources
    4. Creates comprehensive provenance metadata
    """
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
        
        # Step 1: Save all webpage resources (CSS, JS, images, fonts, etc.)
        logger.info("Step 1: Downloading and saving all webpage resources...")
        saved_resources = save_webpage_resources(driver, webpage_dir, final_url)
        logger.info(f"  Saved {len(saved_resources)} resources")
        
        # Step 2: Rewrite URLs in HTML to point to local resources
        logger.info("Step 2: Rewriting URLs in HTML to point to local resources...")
        modified_html = rewrite_html_urls(page_source, final_url, saved_resources, webpage_dir)
        
        # Step 3: Save main HTML file with rewritten URLs
        main_html_file = f"{webpage_dir}/{page_type}.html"
        with open(main_html_file, 'w', encoding='utf-8') as f:
            f.write(modified_html)
        
        logger.info(f"Saved main HTML to: {main_html_file}")
        
        # Calculate content hashes
        original_hash = hashlib.sha256(page_source.encode('utf-8')).hexdigest()
        modified_hash = hashlib.sha256(modified_html.encode('utf-8')).hexdigest()
        
        # Step 4: Create comprehensive metadata file
        webpage_metadata = {
            'original_url': url,
            'final_url': final_url,
            'page_type': page_type,
            'title': page_title,
            'download_timestamp': datetime.now().isoformat(),
            'main_html_file': main_html_file,
            'original_content_hash': original_hash,
            'modified_content_hash': modified_hash,
            'original_size': len(page_source),
            'modified_size': len(modified_html),
            'saved_resources': saved_resources,
            'resource_summary': {
                'total_resources': len(saved_resources),
                'by_type': count_resources_by_type(saved_resources),
                'total_bytes': sum(r.get('size_bytes', 0) for r in saved_resources)
            },
            'url_rewrites': {
                'total_rewrites': count_url_rewrites(page_source, modified_html),
                'local_resources_linked': True
            }
        }
        
        metadata_file = f"{webpage_dir}/{page_type}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(webpage_metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved comprehensive metadata to: {metadata_file}")
        logger.info(f"  Resources: {webpage_metadata['resource_summary']['total_resources']}")
        logger.info(f"  Total size: {webpage_metadata['resource_summary']['total_bytes']:,} bytes")
        
        return {
            'success': True,
            'page_type': page_type,
            'final_url': final_url,
            'title': page_title,
            'content_length': len(modified_html),
            'original_hash': original_hash,
            'modified_hash': modified_hash,
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


def rewrite_html_urls(html_content, base_url, saved_resources, webpage_dir):
    """Rewrite all URLs in HTML to point to local saved resources.
    
    Maps external resource URLs to local file paths so the saved page
    works completely offline.
    """
    logger = logging.getLogger('process_discovered_pages')
    modified_html = html_content
    rewrites_count = 0
    
    # Create URL mapping from external URLs to local paths
    url_mapping = {}
    for resource in saved_resources:
        original_url = resource.get('url')
        local_path = resource.get('file')
        
        if original_url and local_path:
            # Convert absolute path to relative path from webpage_dir
            try:
                rel_path = os.path.relpath(local_path, webpage_dir)
                url_mapping[original_url] = rel_path
            except Exception as e:
                logger.debug(f"Failed to create relative path for {original_url}: {e}")
    
    logger.debug(f"Created URL mapping for {len(url_mapping)} resources")
    
    # Replace all occurrences of external URLs with local paths
    for external_url, local_path in url_mapping.items():
        if external_url in modified_html:
            # Escape special regex characters in URL
            pattern = re.escape(external_url)
            modified_html = re.sub(pattern, local_path, modified_html)
            rewrites_count += modified_html.count(local_path)
    
    logger.debug(f"Rewrote {rewrites_count} URL references in HTML")
    
    # Also handle common resource attribute patterns
    # This catches any URLs that might be formatted differently
    try:
        soup = BeautifulSoup(modified_html, 'html.parser')
        
        # Rewrite link href attributes
        for link in soup.find_all('link', href=True):
            href = link['href']
            for external_url, local_path in url_mapping.items():
                if external_url in href:
                    link['href'] = local_path
        
        # Rewrite script src attributes
        for script in soup.find_all('script', src=True):
            src = script['src']
            for external_url, local_path in url_mapping.items():
                if external_url in src:
                    script['src'] = local_path
        
        # Rewrite img src attributes
        for img in soup.find_all('img', src=True):
            src = img['src']
            for external_url, local_path in url_mapping.items():
                if external_url in src:
                    img['src'] = local_path
        
        # Rewrite source tags in video/audio elements
        for source in soup.find_all('source', src=True):
            src = source['src']
            for external_url, local_path in url_mapping.items():
                if external_url in src:
                    source['src'] = local_path
        
        modified_html = str(soup.prettify())
        logger.debug("Rewritten HTML attributes using BeautifulSoup")
        
    except Exception as e:
        logger.warning(f"BeautifulSoup rewriting encountered issue: {e}, using fallback")
    
    return modified_html


def count_resources_by_type(saved_resources):
    """Count resources grouped by type."""
    count_by_type = {}
    for resource in saved_resources:
        res_type = resource.get('type', 'unknown')
        count_by_type[res_type] = count_by_type.get(res_type, 0) + 1
    return count_by_type


def count_url_rewrites(original_html, modified_html):
    """Estimate number of URL rewrites performed."""
    import re
    
    # Count differences in URL patterns
    original_urls = set(re.findall(r'https?://[^\s"\')<>]+', original_html))
    modified_urls = set(re.findall(r'(?:https?://|(?:\./|/))[^\s"\')<>]+', modified_html))
    
    # URLs that disappeared from original and weren't replaced
    rewritten_count = len([u for u in original_urls if not any(u in modified_html for u in original_urls)])
    
    return rewritten_count


def save_webpage_resources(driver, webpage_dir, base_url):
    """Save ALL webpage resources (CSS, JS, images, fonts, etc.) referenced in the page."""
    logger = logging.getLogger('process_discovered_pages')
    logger.debug("Attempting to save all webpage resources...")
    
    saved_resources = []
    
    try:
        # Create subdirectories for resources
        css_dir = f"{webpage_dir}/css"
        js_dir = f"{webpage_dir}/js"
        images_dir = f"{webpage_dir}/images"
        fonts_dir = f"{webpage_dir}/fonts"
        other_dir = f"{webpage_dir}/other"
        
        for dir_path in [css_dir, js_dir, images_dir, fonts_dir, other_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        # Get all CSS links
        logger.debug("Downloading CSS stylesheets...")
        css_links = driver.find_elements(By.TAG_NAME, "link")
        for link in css_links:
            try:
                rel = link.get_attribute("rel")
                href = link.get_attribute("href")
                if rel and "stylesheet" in rel and href:
                    resource_url = urljoin(base_url, href)
                    filename = os.path.basename(urlparse(href).path) or f"style_{len(saved_resources)}.css"
                    saved_file = download_resource(resource_url, f"{css_dir}/{filename}")
                    if saved_file:
                        file_size = os.path.getsize(saved_file)
                        saved_resources.append({
                            "type": "css",
                            "url": resource_url,
                            "file": saved_file,
                            "size_bytes": file_size
                        })
            except Exception as e:
                logger.debug(f"Failed to save CSS resource: {e}")
        
        logger.debug(f"Downloaded {sum(1 for r in saved_resources if r['type'] == 'css')} CSS files")
        
        # Get all script sources
        logger.debug("Downloading JavaScript files...")
        script_tags = driver.find_elements(By.TAG_NAME, "script")
        for script in script_tags:
            try:
                src = script.get_attribute("src")
                if src:
                    resource_url = urljoin(base_url, src)
                    filename = os.path.basename(urlparse(src).path) or f"script_{len(saved_resources)}.js"
                    saved_file = download_resource(resource_url, f"{js_dir}/{filename}")
                    if saved_file:
                        file_size = os.path.getsize(saved_file)
                        saved_resources.append({
                            "type": "js",
                            "url": resource_url,
                            "file": saved_file,
                            "size_bytes": file_size
                        })
            except Exception as e:
                logger.debug(f"Failed to save JS resource: {e}")
        
        logger.debug(f"Downloaded {sum(1 for r in saved_resources if r['type'] == 'js')} JS files")
        
        # Get all images (no limit - download all)
        logger.debug("Downloading images...")
        img_tags = driver.find_elements(By.TAG_NAME, "img")
        for img in img_tags:
            try:
                src = img.get_attribute("src")
                if src and not src.startswith("data:"):  # Skip data URLs
                    resource_url = urljoin(base_url, src)
                    filename = os.path.basename(urlparse(src).path) or f"image_{len(saved_resources)}.png"
                    saved_file = download_resource(resource_url, f"{images_dir}/{filename}")
                    if saved_file:
                        file_size = os.path.getsize(saved_file)
                        saved_resources.append({
                            "type": "image",
                            "url": resource_url,
                            "file": saved_file,
                            "size_bytes": file_size
                        })
            except Exception as e:
                logger.debug(f"Failed to save image resource: {e}")
        
        logger.debug(f"Downloaded {sum(1 for r in saved_resources if r['type'] == 'image')} images")
        
        # Get fonts from style elements and link tags
        logger.debug("Downloading font files...")
        font_urls = set()
        
        # Extract fonts from <style> tags
        style_tags = driver.find_elements(By.TAG_NAME, "style")
        for style in style_tags:
            content = style.get_attribute("innerHTML")
            if content:
                urls = re.findall(r'url\([\'"]?([^\)\'\"]+\.(?:woff2?|ttf|otf|eot))[\'"]?\)', content, re.IGNORECASE)
                font_urls.update(urls)
        
        # Extract fonts from link tags with font-related href
        for link in css_links:
            href = link.get_attribute("href")
            if href and any(ext in href.lower() for ext in ['.woff', '.ttf', '.otf', '.eot']):
                font_urls.add(href)
        
        for font_url in font_urls:
            try:
                resource_url = urljoin(base_url, font_url)
                filename = os.path.basename(urlparse(font_url).path) or f"font_{len(saved_resources)}.woff2"
                saved_file = download_resource(resource_url, f"{fonts_dir}/{filename}")
                if saved_file:
                    file_size = os.path.getsize(saved_file)
                    saved_resources.append({
                        "type": "font",
                        "url": resource_url,
                        "file": saved_file,
                        "size_bytes": file_size
                    })
            except Exception as e:
                logger.debug(f"Failed to save font resource: {e}")
        
        logger.debug(f"Downloaded {sum(1 for r in saved_resources if r['type'] == 'font')} font files")
        
        # Get other media (video, audio, etc.)
        logger.debug("Downloading other media files...")
        for tag_name in ['video', 'audio', 'source', 'iframe']:
            try:
                elements = driver.find_elements(By.TAG_NAME, tag_name)
                for element in elements:
                    # Check data, src, and srcset attributes
                    for attr in ['data', 'src', 'srcset']:
                        resource_url_str = element.get_attribute(attr)
                        if resource_url_str:
                            # Handle srcset with multiple URLs
                            for part in resource_url_str.split(','):
                                url_part = part.strip().split()[0]  # Get URL before size descriptor
                                if url_part.startswith('http'):
                                    resource_url = url_part
                                else:
                                    resource_url = urljoin(base_url, url_part)
                                
                                filename = os.path.basename(urlparse(resource_url).path) or f"media_{len(saved_resources)}"
                                saved_file = download_resource(resource_url, f"{other_dir}/{filename}")
                                if saved_file:
                                    file_size = os.path.getsize(saved_file)
                                    saved_resources.append({
                                        "type": "media",
                                        "url": resource_url,
                                        "file": saved_file,
                                        "size_bytes": file_size
                                    })
            except Exception as e:
                logger.debug(f"Failed to save {tag_name} media: {e}")
        
        logger.debug(f"Downloaded {sum(1 for r in saved_resources if r['type'] == 'media')} media files")
        logger.debug(f"Saved total {len(saved_resources)} webpage resources")
        
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


def extract_text_from_html(html_file, company_slug, page_type):
    """Extract meaningful text from HTML file and store it in a cleaned text file.
    
    This function:
    1. Parses the HTML and extracts meaningful text
    2. Removes scripts, styles, and boilerplate content
    3. Cleans whitespace and normalizes formatting
    4. Saves the cleaned text to a text file
    5. Creates comprehensive provenance metadata
    """
    logger = logging.getLogger('process_discovered_pages')
    logger.info(f"Extracting text from: {html_file}")
    
    try:
        # Read the HTML file
        with open(html_file, "r", encoding="utf-8", errors='ignore') as f:
            html_content = f.read()
        
        original_size = len(html_content)
        original_hash = hashlib.sha256(html_content.encode('utf-8')).hexdigest()
        
        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "noscript"]):
            script.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
            comment.extract()
        
        # Extract text
        text = soup.get_text(separator='\n', strip=True)
        
        # Clean up excessive whitespace
        lines = []
        for line in text.split('\n'):
            cleaned_line = ' '.join(line.split())  # Normalize internal whitespace
            if cleaned_line and len(cleaned_line.strip()) > 0:  # Skip empty lines
                lines.append(cleaned_line)
        
        # Join with newlines and clean up excessive blank lines
        cleaned_text = '\n'.join(lines)
        
        # Remove excessive newlines (more than 2 consecutive)
        cleaned_text = re.sub(r'\n\n+', '\n\n', cleaned_text)
        
        # Additional cleaning: remove common boilerplate patterns
        boilerplate_patterns = [
            r'(Cookie|cookie).*?(Accept|Decline|Preferences)',
            r'(Subscribe|Follow|Share).*?(Newsletter|Social Media)',
            r'(JavaScript|JavaScript must be enabled)',
        ]
        
        for pattern in boilerplate_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
        
        # Final whitespace cleanup
        cleaned_text = cleaned_text.strip()
        
        cleaned_size = len(cleaned_text)
        cleaned_hash = hashlib.sha256(cleaned_text.encode('utf-8')).hexdigest()
        
        # Save cleaned text to file
        page_dir = f"data/raw/{company_slug}/{page_type}"
        text_filename = f"{page_dir}/text.txt"
        
        with open(text_filename, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
        
        logger.info(f"Saved cleaned text to: {text_filename}")
        logger.info(f"  Original size: {original_size:,} bytes -> Cleaned size: {cleaned_size:,} bytes")
        logger.info(f"  Compression ratio: {(1 - cleaned_size/max(original_size, 1)) * 100:.1f}%")
        
        # Extract key statistics
        word_count = len(cleaned_text.split())
        line_count = len(cleaned_text.split('\n'))
        paragraph_count = len([p for p in cleaned_text.split('\n\n') if p.strip()])
        
        # Create comprehensive metadata
        text_metadata = {
            'source_html_file': html_file,
            'text_file': text_filename,
            'page_type': page_type,
            'extraction_timestamp': datetime.now().isoformat(),
            'source_statistics': {
                'html_size_bytes': original_size,
                'html_hash': original_hash
            },
            'cleaned_text_statistics': {
                'text_size_bytes': cleaned_size,
                'text_hash': cleaned_hash,
                'word_count': word_count,
                'line_count': line_count,
                'paragraph_count': paragraph_count,
                'avg_line_length': round(cleaned_size / max(line_count, 1), 2),
                'avg_words_per_line': round(word_count / max(line_count, 1), 2)
            },
            'processing': {
                'script_removal': True,
                'style_removal': True,
                'comment_removal': True,
                'whitespace_normalization': True,
                'boilerplate_removal': True,
                'compression_ratio': round((1 - cleaned_size / max(original_size, 1)) * 100, 2)
            }
        }
        
        # Save metadata
        metadata_filename = f"{page_dir}/text_extraction_metadata.json"
        with open(metadata_filename, 'w', encoding='utf-8') as f:
            json.dump(text_metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved text extraction metadata to: {metadata_filename}")
        
        return {
            'success': True,
            'page_type': page_type,
            'text_file': text_filename,
            'metadata_file': metadata_filename,
            'text_size': cleaned_size,
            'word_count': word_count,
            'extraction_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to extract text from {html_file}: {e}")
        return {
            'success': False,
            'page_type': page_type,
            'error': str(e),
            'extraction_timestamp': datetime.now().isoformat()
        }


def process_all_html_files_in_company(company_slug):
    """Process ALL HTML files in data/raw/{company_slug} to extract and clean text.
    
    Handles multiple page types and creates comprehensive provenance tracking.
    """
    logger = logging.getLogger('process_discovered_pages')
    
    company_raw_dir = Path(f"data/raw/{company_slug}")
    
    if not company_raw_dir.exists():
        logger.warning(f"Company directory not found: {company_raw_dir}")
        return {
            'company_slug': company_slug,
            'success': False,
            'reason': 'Directory not found',
            'pages_processed': 0
        }
    
    logger.info(f"\n=== Processing ALL HTML files for {company_slug} ===")
    
    # Find all page_type directories (e.g., careers, about, product, blog)
    page_type_dirs = [d for d in company_raw_dir.iterdir() if d.is_dir()]
    
    if not page_type_dirs:
        logger.warning(f"No page type directories found in {company_raw_dir}")
        return {
            'company_slug': company_slug,
            'success': False,
            'reason': 'No page directories found',
            'pages_processed': 0
        }
    
    all_text_results = []
    company_texts = {}  # Aggregate all texts
    
    for page_type_dir in sorted(page_type_dirs):
        page_type = page_type_dir.name
        html_file = page_type_dir / f"{page_type}.html"
        
        if not html_file.exists():
            logger.warning(f"  HTML file not found for {page_type}: {html_file}")
            continue
        
        logger.info(f"Processing {page_type} page...")
        
        # Extract text
        text_result = extract_text_from_html(str(html_file), company_slug, page_type)
        
        if text_result.get('success'):
            all_text_results.append({
                'page_type': page_type,
                'success': True,
                'text_file': text_result.get('text_file'),
                'text_size': text_result.get('text_size'),
                'word_count': text_result.get('word_count'),
                'metadata_file': text_result.get('metadata_file')
            })
            
            # Read the cleaned text for aggregation
            try:
                with open(text_result.get('text_file'), 'r', encoding='utf-8') as f:
                    company_texts[page_type] = f.read()
            except Exception as e:
                logger.error(f"Failed to read text file for aggregation: {e}")
        else:
            all_text_results.append({
                'page_type': page_type,
                'success': False,
                'error': text_result.get('error')
            })
    
    # Create company-level provenance record
    total_text_size = sum(r.get('text_size', 0) for r in all_text_results if r.get('success'))
    total_words = sum(r.get('word_count', 0) for r in all_text_results if r.get('success'))
    
    company_provenance = {
        'company_slug': company_slug,
        'processing_timestamp': datetime.now().isoformat(),
        'pages_processed': len(all_text_results),
        'pages_successful': sum(1 for r in all_text_results if r.get('success')),
        'pages_failed': sum(1 for r in all_text_results if not r.get('success')),
        'text_extraction_results': all_text_results,
        'aggregated_statistics': {
            'total_text_size_bytes': total_text_size,
            'total_word_count': total_words,
            'average_words_per_page': round(total_words / max(sum(1 for r in all_text_results if r.get('success')), 1), 2),
            'page_types_processed': [r.get('page_type') for r in all_text_results if r.get('success')]
        }
    }
    
    # Save company-level provenance
    metadata_dir = Path(f"data/metadata/{company_slug}")
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    provenance_file = metadata_dir / "text_extraction_provenance.json"
    with open(provenance_file, 'w', encoding='utf-8') as f:
        json.dump(company_provenance, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved company-level provenance: {provenance_file}")
    logger.info(f"\n=== TEXT EXTRACTION COMPLETE FOR {company_slug} ===")
    logger.info(f"  Pages processed: {company_provenance['pages_successful']}/{company_provenance['pages_processed']}")
    logger.info(f"  Total text size: {total_text_size:,} bytes")
    logger.info(f"  Total words: {total_words:,}")
    
    return {
        'company_slug': company_slug,
        'success': sum(1 for r in all_text_results if r.get('success')) > 0,
        'pages_processed': len(all_text_results),
        'pages_successful': sum(1 for r in all_text_results if r.get('success')),
        'provenance_file': str(provenance_file),
        'results': all_text_results
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
    """Process all company pages for a single company: both discovered and explicitly defined pages (about, product, careers, blog, homepage, linkedin)."""
    logger = logging.getLogger('process_discovered_pages')
    
    company_name = company_data.get('company_name', 'UNKNOWN')
    company_slug = slugify(company_name)
    website = company_data.get('website', '')
    linkedin_url = company_data.get('linkedin', '')
    
    # Try to get pages from different sources
    # Priority: "pages" field (from company_pages.json) > "discovered_pages" field (from company_pages_discovered.json)
    pages_dict = company_data.get('pages', {})
    discovered_pages = company_data.get('discovered_pages', {})
    
    logger.info(f"=== Processing {company_name} ===")
    logger.info(f"Website: {website}")
    if linkedin_url:
        logger.info(f"LinkedIn: {linkedin_url}")
    
    # If we have pages dict, use those; otherwise fall back to discovered_pages
    pages_to_process = {}
    if pages_dict:
        # Convert pages dict format to list format for consistent processing
        # pages dict: {"about": "url", "product": null, "careers": "url", ...}
        for page_type, page_url in pages_dict.items():
            if page_url and page_type not in ['homepage']:  # Skip homepage, we'll handle it separately
                pages_to_process[page_type] = [{'url': page_url}]
    else:
        pages_to_process = discovered_pages
    
    # Check if we have anything to process
    has_pages = any(pages_to_process.get(pt) for pt in pages_to_process)
    
    if not has_pages and not linkedin_url:
        logger.warning(f"No pages or LinkedIn URL found for {company_name}, skipping")
        return {
            'company_name': company_name,
            'company_slug': company_slug,
            'success': False,
            'reason': 'No pages or LinkedIn URL available'
        }
    
    try:
        # Create directory structure - include all page types
        page_types = [page_type for page_type in pages_to_process.keys() if pages_to_process[page_type]]
        if linkedin_url:
            page_types.append('linkedin')
        
        create_directory_structure(company_slug, page_types)
        
        pages_results = []
        
        # Process each page type
        for page_type, pages in pages_to_process.items():
            if not pages:
                logger.info(f"  No pages found for {page_type}")
                continue
            
            logger.info(f"  Processing {page_type} page...")
            
            # Process the first/primary page for this type
            page_info = pages[0] if isinstance(pages, list) else pages
            page_url = page_info.get('url') if isinstance(page_info, dict) else page_info
            
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
        
        # Process LinkedIn page if available
        if linkedin_url:
            logger.info(f"  Processing LinkedIn page...")
            page_type = 'linkedin'
            
            logger.info(f"  Step 1: Downloading LinkedIn page from {linkedin_url}")
            download_result = download_webpage_with_selenium(driver, linkedin_url, company_slug, page_type)
            
            page_result = {
                'page_type': page_type,
                'url': linkedin_url,
                'download_success': download_result.get('success', False),
                'download_timestamp': download_result.get('download_timestamp')
            }
            
            # Extract links from LinkedIn page
            extraction_result = {'success': False}
            if download_result.get('success'):
                logger.info(f"  Step 2: Extracting links from LinkedIn page")
                html_file = download_result.get('main_html_file')
                extraction_result = extract_links_from_html(html_file, company_slug, page_type)
                page_result['extraction_success'] = extraction_result.get('success', False)
                page_result['links_count'] = extraction_result.get('links_count', 0)
                page_result['links_file'] = extraction_result.get('links_file')
            else:
                logger.warning(f"  Skipping link extraction for LinkedIn due to download failure")
                page_result['extraction_success'] = False
                page_result['links_count'] = 0
            
            page_result['success'] = page_result['download_success'] and page_result['extraction_success']
            
            if page_result.get('success'):
                logger.info(f"  ✓ LINKEDIN: SUCCESS ({page_result.get('links_count')} links)")
            else:
                logger.info(f"  ✗ LINKEDIN: FAILED")
            
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
    input_file = "data/company_pages.json"
    companies_to_process = None  # Process all companies, or set to list like ['World Labs']
    limit = None  # No limit, or set to a number like 5
    extract_text = True  # Extract and clean text from HTML files
    
    logger.info(f"Configuration: input={input_file}, companies={companies_to_process}, limit={limit}, extract_text={extract_text}")
    
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
            
            # If text extraction is enabled, process all HTML files
            if extract_text:
                logger.info(f"\n=== PHASE 2: TEXT EXTRACTION AND CLEANING ===")
                text_results = []
                for result in results:
                    if result.get('success'):
                        company_slug = result.get('company_slug')
                        logger.info(f"\nExtracting text from: {company_slug}")
                        text_result = process_all_html_files_in_company(company_slug)
                        text_results.append(text_result)
            
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
