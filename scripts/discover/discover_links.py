#!/usr/bin/env python3
"""Discover key pages (homepage, about, product, careers, blog) for Forbes AI 50 companies.

Reads: data/forbes_ai50_seed.json
Writes: data/discover/company_pages_discovered.json, data/discover/company_pages.json

Fully automated - discovers URLs for:
- homepage
- /about
- /product or /platform
- /careers
- /blog or /news

Usage:
  python scripts/discover/discover_links.py
"""
import json
import logging
import os
import argparse
import time
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Scoring weights for different page types
SCORE_HOMEPAGE = 100
SCORE_ABOUT = 80
SCORE_PRODUCT = 70
SCORE_CAREERS = 60
SCORE_BLOG = 50

# Path keywords
ABOUT_KEYWORDS = ["about", "about-us", "company"]
PRODUCT_KEYWORDS = ["product", "products", "platform", "features", "solution", "solutions", "service", "services"]
CAREERS_KEYWORDS = ["careers", "career", "jobs", "job", "hiring", "work-with-us", "join-us", "team"]
BLOG_KEYWORDS = ["blog", "news", "press", "media", "insights", "resources", "articles", "posts"]

# Link text keywords
ABOUT_TEXT = ["about", "about us", "company", "who we are"]
PRODUCT_TEXT = ["product", "products", "platform", "features", "solution", "solutions", "service", "services"]
CAREERS_TEXT = ["careers", "career", "jobs", "join us", "work with us", "hiring"]
BLOG_TEXT = ["blog", "news", "press", "insights", "resources", "articles"]

# Penalize patterns for specific page types (avoid specific industry verticals for product pages)
PRODUCT_PENALTY_PATTERNS = [
    "/solutions/", "/industries/", "/financial-services", "/healthcare", 
    "/retail", "/manufacturing", "/education", "/legal", "/use-cases",
    "/case-studies", "/pricing", "/demo"  # Also avoid pricing and demo pages for main product
]

TRACKING_PARAMS = ["utm_source", "utm_medium", "utm_campaign", "_gl", "_ga", "icid", "athAsset"]

# Pages to skip
SKIP_PATTERNS = [
    "/contact", "/contact-us", "/privacy", "/terms", "/cookies",
    "/sitemap", "/404", "/search", "/help", "/support", "/faq",
    "/api/", "/cdn/", "/cdn-cgi/", "/static/", "/assets/",
    ".pdf", ".zip", ".doc", "/download"
]


def setup_logging():
    """Setup logging for discover_links script."""
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger('discover_links')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    file_handler = logging.FileHandler(f"{log_dir}/discover_links.log")
    file_handler.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def load_companies(path):
    """Load companies from JSON file."""
    logger = logging.getLogger('discover_links')
    logger.info(f"Loading companies from: {path}")
    
    if not os.path.exists(path):
        logger.error(f"Input file '{path}' not found")
        raise FileNotFoundError(f"Input file '{path}' not found")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            companies = json.load(f)
        logger.info(f"Successfully loaded {len(companies)} companies from {path}")
        return companies
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in '{path}': {e}")
        raise ValueError(f"Invalid JSON in '{path}': {e}")
    except Exception as e:
        logger.error(f"Error reading '{path}': {e}")
        raise IOError(f"Error reading '{path}': {e}")


def load_manual_overrides(path="scripts/discover/manual_overrides.json"):
    """Load manual overrides for companies with discovery issues."""
    logger = logging.getLogger('discover_links')
    if not os.path.exists(path):
        logger.debug(f"No manual overrides file found at {path}")
        return {}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            overrides = json.load(f)
        logger.info(f"Loaded manual overrides for {len(overrides)} companies from {path}")
        return overrides
    except Exception as e:
        logger.warning(f"Error loading manual overrides from {path}: {e}")
        return {}


def normalize_url(url):
    """Remove tracking params and normalize URL."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in query_params.items() if k not in TRACKING_PARAMS}
    clean_query = "&".join(f"{k}={v[0]}" for k, v in clean_params.items())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, ""))


def get_base_domain(url):
    """Extract base domain (e.g., apple.com from www.apple.com)."""
    parsed = urlparse(url)
    parts = parsed.netloc.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return parsed.netloc


def score_candidate(url, link_text, page_type, homepage_url):
    """Score a candidate URL based on page type."""
    score = 0
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    path = parsed.path.lower()
    text = link_text.lower()
    base_domain = get_base_domain(homepage_url)
    
    # Skip unwanted patterns
    for pattern in SKIP_PATTERNS:
        if pattern in path or pattern in hostname:
            return -1000
    
    # Same domain bonus - reduced penalty for off-domain
    if base_domain in hostname:
        score += 40
    else:
        score -= 50  # Reduced from -100 to allow external services
    
    # Page type specific scoring
    if page_type == "about":
        for kw in ABOUT_KEYWORDS:
            if kw in path:
                score += 80
        for kw in ABOUT_TEXT:
            if kw in text:
                score += 60
    
    elif page_type == "product":
        # Penalize industry-specific solution pages for main product page
        for penalty_pattern in PRODUCT_PENALTY_PATTERNS:
            if penalty_pattern in path:
                score -= 100  # Strong penalty for industry verticals
        
        for kw in PRODUCT_KEYWORDS:
            if kw in path:
                score += 70
        for kw in PRODUCT_TEXT:
            if kw in text:
                score += 50
        
        # Bonus for main product pages (shorter, simpler paths)
        if path in ["/product", "/platform", "/products", ""]:
            score += 150  # Strong bonus for exact match main product pages
    
    elif page_type == "careers":
        # Penalize /team path - prefer explicit /careers path
        if "/team" in path:
            score -= 80  # Strong penalty for /team when looking for careers
        
        # Bonus for exact /careers or /jobs paths on company domain
        if path in ["/careers", "/jobs", "/join-us"]:
            score += 150  # Very strong bonus for proper internal careers pages
        
        for kw in CAREERS_KEYWORDS:
            if kw in path:
                score += 60
        for kw in CAREERS_TEXT:
            if kw in text:
                score += 40
    
    elif page_type == "blog":
        for kw in BLOG_KEYWORDS:
            if kw in path:
                score += 50
        for kw in BLOG_TEXT:
            if kw in text:
                score += 30
    
    # Penalize very long query strings
    if len(parsed.query) > 100:
        score -= 30
    
    # Prefer shorter paths for landing pages - but allow deeper paths
    if path.count('/') <= 2:
        score += 20
    elif path.count('/') <= 4:
        score += 5  # Still prefer but not penalize deeply nested
    
    # External recruiting platforms - only as FALLBACK (lower priority than internal pages)
    # These are OK to use but should not win over internal company careers pages
    if page_type == 'careers' and ('ashby' in hostname or 'lever' in hostname or 'greenhouse' in hostname):
        # If it's external recruiting platform, give a small penalty
        # This ensures internal /careers pages win, but allows recruiting links as fallback
        if base_domain not in hostname:
            score -= 30  # Modest penalty for external recruiting platforms to prefer internal pages
            # But still apply recruiting platform bonus to make it findable as fallback
            score += 50
    
    return score


def discover_candidates_from_page(url, page_type):
    """Scrape a page and return candidate links with scores."""
    logger = logging.getLogger('discover_links')
    logger.debug(f"Discovering {page_type} candidates from: {url}")
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        r.raise_for_status()
        logger.debug(f"Successfully fetched page (status: {r.status_code})")
    except requests.Timeout:
        logger.debug(f"Timeout fetching {url}")
        return []
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return []
    
    try:
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        logger.debug(f"Failed to parse HTML from {url}: {e}")
        return []
    
    candidates = []
    seen = set()
    
    for a in soup.find_all("a", href=True):
        try:
            href = a["href"]
            text = a.get_text(" ", strip=True)
            full_url = urljoin(url, href)
            normalized = normalize_url(full_url)
            
            if normalized in seen:
                continue
            seen.add(normalized)
            
            # Skip anchors, mailto, tel, javascript
            if normalized.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            
            # Must be http/https
            if not normalized.startswith(("http://", "https://")):
                continue
            
            score = score_candidate(normalized, text, page_type, url)
            if score > -100:
                candidates.append({
                    "url": normalized,
                    "text": text[:100],
                    "score": score,
                    "page_type": page_type
                })
        except Exception as e:
            logger.debug(f"Error processing link: {e}")
            continue
    
    logger.debug(f"Found {len(candidates)} candidates for {page_type}")
    return candidates


def probe_common_paths(homepage_url, page_type):
    """Probe common paths for the given page type."""
    logger = logging.getLogger('discover_links')
    parsed = urlparse(homepage_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = []
    
    # Common paths to probe for each page type - EXPANDED
    common_paths = {
        "about": ["/about", "/about-us", "/company", "/about-the-company", "/who-we-are", "/team", "/our-story", "/overview"],
        "product": ["/product", "/products", "/platform", "/features", "/solution", "/solutions", "/services", "/offerings", "/capabilities"],
        "careers": ["/careers", "/career", "/jobs", "/join-us", "/work-with-us", "/hiring", "/culture", "/working-here"],
        "blog": ["/blog", "/news", "/press", "/media", "/insights", "/resources", "/articles", "/posts", "/updates", "/updates/"]
    }
    
    for path in common_paths.get(page_type, []):
        probe_url = urljoin(base, path)
        
        try:
            response = requests.head(probe_url, headers=HEADERS, timeout=5, allow_redirects=True, verify=False)
            if response.status_code in [200, 301, 302, 303, 307, 308]:  # Accept redirects too
                final_url = response.url
                score = score_candidate(final_url, f"(probed: {path})", page_type, homepage_url)
                candidates.append({
                    "url": final_url,
                    "text": f"(probed: {path})",
                    "score": score,
                    "page_type": page_type
                })
                logger.debug(f"Probed {path}: found {final_url} (status: {response.status_code}, score: {score})")
        except Exception as e:
            logger.debug(f"Probe failed for {probe_url}: {e}")
            continue
    
    return candidates


def discover_page_links(homepage_url, page_type):
    """Discover links for a specific page type."""
    logger = logging.getLogger('discover_links')
    
    if not homepage_url:
        logger.warning("No homepage URL provided")
        return None, []
    
    logger.debug(f"Starting discovery for {page_type} page")
    
    # Collect candidates from homepage scraping
    candidates = discover_candidates_from_page(homepage_url, page_type)
    
    # Add probed common paths
    probed = probe_common_paths(homepage_url, page_type)
    candidates.extend(probed)
    
    if not candidates:
        logger.warning(f"No candidates found for {page_type}")
        return None, []
    
    # Sort by score (desc)
    candidates.sort(key=lambda x: (-x['score'], x['url']))
    
    # Return best candidate (accept even low scores if nothing else is available)
    if candidates:
        best_url = candidates[0]["url"]
        best_score = candidates[0]["score"]
        
        if best_score > 0:
            logger.info(f"Selected best {page_type} link: {best_url} (score: {best_score})")
        elif best_score >= -50:  # Allow moderately negative scores if no positive found
            logger.warning(f"Using best available {page_type} link despite low score: {best_url} (score: {best_score})")
        else:
            logger.warning(f"No acceptable candidates with reasonable score found for {page_type}")
            return None, candidates[:5]
        
        return best_url, candidates[:5]
    
    logger.warning(f"No candidates found for {page_type}")
    return None, []


def main():
    logger = setup_logging()
    logger.info("=== Starting Company Pages Discovery ===")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/forbes_ai50_seed.json")
    parser.add_argument("--output", default="data/company_pages.json")
    parser.add_argument("--discovered", default="data/company_pages_discovered.json")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N companies (useful for testing)")
    args = parser.parse_args()
    
    logger.info(f"Arguments: input={args.input}, output={args.output}, discovered={args.discovered}")
    
    # Create output directory
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    try:
        companies = load_companies(args.input)
        manual_overrides = load_manual_overrides()
        
        # Apply limit if specified
        if args.limit:
            companies = companies[:args.limit]
            logger.info(f"Processing limited to first {args.limit} companies")
        
        results = []
        discovered_results = []
        
        logger.info("=== Starting Company Processing ===")
        for idx, company in enumerate(companies, 1):
            company_name = company.get("company_name", "Unknown")
            website = company.get("website", "")
            
            logger.info(f"{idx}/{len(companies)}: Processing {company_name}")
            
            if not website:
                logger.warning(f"No website for {company_name}, skipping")
                results.append({
                    "company_name": company_name,
                    "website": website,
                    "pages": {
                        "homepage": website,
                        "about": None,
                        "product": None,
                        "careers": None,
                        "blog": None
                    }
                })
                discovered_results.append({
                    "company_name": company_name,
                    "website": website,
                    "discovered_pages": {
                        "about": [],
                        "product": [],
                        "careers": [],
                        "blog": []
                    }
                })
                continue
            
            # Discover each page type
            pages = {"homepage": website}
            discovered_pages = {}
            
            for page_type in ["about", "product", "careers", "blog"]:
                logger.debug(f"Discovering {page_type} for {company_name}")
                
                # Check if there's a manual override for this company and page type
                if company_name in manual_overrides and page_type in manual_overrides[company_name]:
                    override_url = manual_overrides[company_name][page_type]
                    logger.info(f"Using manual override for {page_type}: {override_url}")
                    best_url = override_url
                    discovered_pages[page_type] = [{
                        "url": override_url,
                        "text": f"(manual override: {page_type})",
                        "score": 1000,
                        "page_type": page_type
                    }]
                else:
                    best_url, candidates = discover_page_links(website, page_type)
                    discovered_pages[page_type] = candidates
                
                pages[page_type] = best_url
                time.sleep(args.delay)
            
            results.append({
                "company_name": company_name,
                "website": website,
                "pages": pages
            })
            
            discovered_results.append({
                "company_name": company_name,
                "website": website,
                "discovered_pages": discovered_pages
            })
            
            logger.info(f"  Discovered pages for {company_name}")
        
        # Write final results
        logger.info("=== Writing Output Files ===")
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Successfully wrote main results to: {args.output}")
        
        # Write discovered (raw) results
        with open(args.discovered, "w", encoding="utf-8") as f:
            json.dump(discovered_results, f, indent=2)
        logger.info(f"Successfully wrote discovery data to: {args.discovered}")
        
        print(f"\n✓ Wrote {len(results)} entries to {args.output}")
        print(f"✓ Wrote discovery data to {args.discovered}")
        
        # Summary
        complete_pages = sum(1 for r in results if all(r["pages"].values()))
        missing_pages = sum(1 for r in results if any(v is None for k, v in r["pages"].items() if k != "homepage"))
        
        logger.info(f"=== FINAL SUMMARY ===")
        logger.info(f"  Total companies processed: {len(results)}")
        logger.info(f"  Complete page sets: {complete_pages}")
        logger.info(f"  Missing pages: {missing_pages}")
        
        print(f"\nSummary:")
        print(f"  Total companies: {len(results)}")
        print(f"  Complete page sets: {complete_pages}")
        print(f"  Companies with missing pages: {missing_pages}")
        
        logger.info("=== COMPANY PAGES DISCOVERY COMPLETED SUCCESSFULLY ===")
        
    except Exception as e:
        logger.error(f"Fatal error during discovery: {e}")
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
