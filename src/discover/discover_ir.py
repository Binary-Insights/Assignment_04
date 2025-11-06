#!/usr/bin/env python3
"""Enhanced IR page discovery with scoring-based candidate selection.

Reads: data/discover/dow30_companies.json
Writes: data/discover/ir_pages.json, data/ir_pages_discovered.json

Fully automated - no manual overrides.

Usage:
  python src/discover/discover_ir.py --input data/dow30_companies.json
"""
import argparse
import json
import logging
import os
import re
import subprocess
import time
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Scoring weights
SCORE_SUBDOMAIN_IR = 100  # investors.company.com, ir.company.com
SCORE_PATH_IR = 80        # /investors, /investor-relations
SCORE_LINK_TEXT = 60      # "Investor Relations" in anchor text
SCORE_SAME_DOMAIN = 40    # Same base domain as homepage
SCORE_IR_HOMEPAGE = 50    # Bonus for actual IR landing pages
PENALTY_PRODUCT = -80     # Product/marketplace pages
PENALTY_EXTERNAL = -50    # External/unrelated domains
PENALTY_NON_LANDING = -100  # Contact, fact-sheet, careers pages

IR_SUBDOMAINS = ["investors", "ir", "investor"]
IR_PATH_KEYWORDS = ["investor", "investors", "investor-relations", "ir", "financials"]
IR_TEXT_KEYWORDS = ["investor relations", "investors", "investor", "sec filings", "quarterly results", "earnings", "financial information"]
PRODUCT_PATTERNS = ["/ip/", "/product/", "/products/", "/shop/", "/store/", "/buy/"]

# Non-landing page patterns (should be avoided)
NON_LANDING_PATTERNS = [
    "/contact", "/contact-us", "/fact-sheet", "/investor-fact-sheet",
    "/pipeline", "/careers", "/job", "/locations", "/media-kit",
    "/privacy", "/terms", "/cookies"
]

# IR homepage patterns (should be preferred)
IR_HOMEPAGE_PATTERNS = [
    "/home", "/investor-home", "/overview", "/default.aspx",
    "/investor-relations/default.aspx", "/investors/overview"
]

TRACKING_PARAMS = ["utm_source", "utm_medium", "utm_campaign", "_gl", "_ga", "icid", "athAsset"]

COMMON_IR_PATHS = [
    "/investors",
    "/investor-relations",
    "/ir",
    "/investor",
    "/investors/overview",
    "/investors/overview/default.aspx",
    "/investor-relations/default.aspx",
    "/investor/default.aspx",
    "/corpmcd/investors.html",  # McDonald's
    "/about/investors",
    "/investors.html",
    "/financial-info",
    "/financial-reports"

]

# Validation keywords for content analysis
IR_CONTENT_KEYWORDS = [
    'investor relations',
    'financial information',
    'quarterly results',
    'earnings',
    'annual report',
    'sec filings',
    'stock information',
    'shareholder',
    'press releases',
    'financial results',
    'corporate governance',
]


def setup_logging():
    """Setup logging for discover_ir script."""
    # Create logs directory if it doesn't exist
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create unique logger for discover_ir
    logger = logging.getLogger('discover_ir')
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(f"{log_dir}/discover_ir.log")
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


def validate_ir_content(url):
    """
    Validate that a URL actually points to an IR page by analyzing content.
    
    Returns dict with is_valid, confidence, keywords_found, has_financial_elements
    """
    logger = logging.getLogger('discover_ir')
    logger.debug(f"Validating IR content for: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        response.raise_for_status()
        logger.debug(f"Successfully fetched validation page (status: {response.status_code})")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text().lower()
        
        # Count IR keyword matches
        keywords_found = sum(1 for keyword in IR_CONTENT_KEYWORDS if keyword in page_text)
        found_keywords = [kw for kw in IR_CONTENT_KEYWORDS if kw in page_text]
        logger.debug(f"Found {keywords_found} IR keywords: {found_keywords[:5]}...")
        
        # Check for financial elements
        has_tables = len(soup.find_all('table')) > 2
        has_sec_links = 'sec.gov' in page_text or '10-k' in page_text or '10-q' in page_text
        logger.debug(f"Financial elements: tables={has_tables}, sec_links={has_sec_links}")
        
        # Calculate confidence based primarily on content
        keyword_score = min(keywords_found / len(IR_CONTENT_KEYWORDS), 0.7)  # Increased weight
        elements_score = 0.15 if has_tables else 0.0
        elements_score += 0.15 if has_sec_links else 0.0
        
        confidence = keyword_score + elements_score
        is_valid = confidence > 0.25 or keywords_found >= 3
        
        logger.debug(f"Validation result: valid={is_valid}, confidence={confidence:.2f}, keywords={keywords_found}")
        
        # Lower threshold - if it has IR content, it's valid
        return {
            'is_valid': is_valid,  # 3+ keywords = valid
            'confidence': round(confidence, 2),
            'keywords_found': keywords_found,
            'has_financial_elements': has_tables or has_sec_links
        }
        
    except Exception as e:
        logger.warning(f"Failed to validate IR content for {url}: {e}")
        # If we can't fetch, skip validation (don't claim it's valid with 0 confidence)
        return {
            'is_valid': None,  # Unknown - couldn't validate
            'confidence': 0.0,
            'keywords_found': 0,
            'has_financial_elements': False,
            'error': str(e)
        }


def load_companies(path):
    """Load companies from JSON file. If file doesn't exist, run fetch_dow30.py to create it."""
    logger = logging.getLogger('discover_ir')
    logger.info(f"Loading companies from: {path}")
    
    if not os.path.exists(path):
        logger.warning(f"Input file '{path}' not found - will attempt to create it")
        print(f"⚠️  Input file '{path}' not found.")
        
        # Determine the output path for fetch_dow30.py based on the expected input path
        if path.endswith('.json'):
            csv_path = path.replace('.json', '.csv')
        else:
            csv_path = path + '.csv'
            
        logger.info(f"Attempting to run fetch_dow30.py with output: {csv_path}")
        print(f"🔄 Running fetch_dow30.py to create required files...")
        print(f"   Output will be: {csv_path} and {path}")
        
        try:
            # Run fetch_dow30.py with the correct output path
            result = subprocess.run([
                'python', 'src/discover/fetch_dow30.py', 
                '--output', csv_path
            ], capture_output=True, text=True, check=True)
            
            logger.info("Successfully executed fetch_dow30.py")
            print("✅ Successfully created company data files!")
            if result.stdout:
                print(f"   {result.stdout.strip()}")
                logger.info(f"fetch_dow30.py output: {result.stdout.strip()}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"fetch_dow30.py failed with return code {e.returncode}")
            print(f"❌ Failed to run fetch_dow30.py:")
            print(f"   Error: {e}")
            if e.stdout:
                print(f"   Output: {e.stdout}")
                logger.error(f"fetch_dow30.py stdout: {e.stdout}")
            if e.stderr:
                print(f"   Error details: {e.stderr}")
                logger.error(f"fetch_dow30.py stderr: {e.stderr}")
            raise FileNotFoundError(f"Could not create required input file '{path}'. Please run 'python src/fetch_dow30.py --output {csv_path}' manually.")
        
        except FileNotFoundError:
            logger.error("Could not find python executable or fetch_dow30.py script")
            raise FileNotFoundError(f"Could not find 'python' or 'src/discover/fetch_dow30.py'. Please ensure you're in the correct directory and have Python installed.")
    
    # Load the companies data
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


def normalize_url(url):
    """Remove tracking params and normalize URL."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    # Remove tracking params
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


def score_candidate(url, link_text, homepage_url):
    """Score a candidate IR URL."""
    score = 0
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    path = parsed.path.lower()
    text = link_text.lower()
    base_domain = get_base_domain(homepage_url)
    
    # STRONG REJECTION: Bad subdomains/paths (developer, app, solutions, claims, etc.)
    bad_subdomains = ["developer", "appsource", "apps", "marketplace", "shop", "store", "careers", "jobs", "nursing", "alumni", "choice", "research"]
    for bad_sub in bad_subdomains:
        if bad_sub in hostname:
            return -500  # Absolute rejection
    
    bad_paths = ["/solutions/", "/appexchange/", "/claimupload", "/claim", "/innovativemedicine", 
                 "/developer/", "/apps/", "/marketplace/", "/technologies/", "/artificial-intelligence",
                 "/environmental-sustainability", "/commerce/", "/gp/help/", "/smartphones/", "/icc/",
                 "nursing.", "alumni.", "choice.", "research."]
    for bad_path in bad_paths:
        if bad_path in path or bad_path in hostname:
            return -500  # Absolute rejection
    
    # BIG BONUS: IR subdomains (investors, ir, investor, stock)
    ir_bonus_domains = ["investors.", "ir.", "investor.", "stock."]
    for sub in ir_bonus_domains:
        if hostname.startswith(sub) or f".{sub}" in hostname:
            score += 200  # Huge bonus for IR subdomain
            break
    
    # Subdomain bonus
    for sub in IR_SUBDOMAINS:
        if hostname.startswith(f"{sub}.") or f".{sub}." in hostname:
            score += SCORE_SUBDOMAIN_IR
            break
    
    # Path keyword bonus
    for kw in IR_PATH_KEYWORDS:
        if kw in path:
            score += SCORE_PATH_IR
            break
    
    # Link text bonus
    for kw in IR_TEXT_KEYWORDS:
        if kw in text:
            score += SCORE_LINK_TEXT
            break
    
    # Same domain bonus
    if base_domain in hostname:
        score += SCORE_SAME_DOMAIN
    else:
        # Penalize external domains (unless they're known IR subdomains)
        if not any(sub in hostname for sub in IR_SUBDOMAINS):
            score += PENALTY_EXTERNAL
    
    # **FIX 1**: Penalty for non-landing pages (contact, fact-sheet, careers, commerce, etc.)
    for pattern in NON_LANDING_PATTERNS:
        if pattern in path:
            score += PENALTY_NON_LANDING
            break
    
    # **FIX 2**: Bonus for IR homepage patterns and positive IR keywords
    for pattern in IR_HOMEPAGE_PATTERNS:
        if pattern in path:
            score += SCORE_IR_HOMEPAGE
            break
    # Extra bonus for strong IR keywords in path or text
    positive_keywords = ["investor", "investors", "ir", "investor-relations", "financials", "sec-filings", "quarterly", "earnings", "results"]
    for pos in positive_keywords:
        if pos in path or pos in text:
            score += 40
            break
    
    # **FIX 3**: Bonus for base IR paths (shorter is better for landing pages)
    if path in ['/', ''] or (path.count('/') <= 2 and any(sub in hostname for sub in IR_SUBDOMAINS)):
        score += 30  # Bonus for simple IR landing pages
    
    # Product page penalty
    for pattern in PRODUCT_PATTERNS:
        if pattern in path:
            score += PENALTY_PRODUCT
            break
    
    # Penalize very long query strings (tracking/product IDs)
    if len(parsed.query) > 100:
        score -= 30
    
    return score


def discover_candidates_from_page(url):
    """Scrape a page and return candidate IR links with scores."""
    logger = logging.getLogger('discover_ir')
    logger.debug(f"Discovering candidates from homepage: {url}")
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.raise_for_status()
        logger.debug(f"Successfully fetched homepage (status: {r.status_code})")
    except Exception as e:
        logger.warning(f"Failed to fetch homepage {url}: {e}")
        return []
    
    soup = BeautifulSoup(r.text, "lxml")
    candidates = []
    seen = set()
    total_links = len(soup.find_all("a", href=True))
    logger.debug(f"Found {total_links} total links on homepage")
    
    processed = 0
    for a in soup.find_all("a", href=True):
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
        
        score = score_candidate(normalized, text, url)
        candidates.append({
            "url": normalized,
            "text": text[:100],
            "score": score
        })
        processed += 1
    
    logger.debug(f"Processed {processed} valid links, found {len(candidates)} candidates")
    # Log top scoring candidates
    top_candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)[:3]
    for i, cand in enumerate(top_candidates, 1):
        logger.debug(f"  Top {i}: {cand['url']} (score: {cand['score']})")
    
    return candidates


def probe_common_paths(homepage_url):
    """Probe common IR paths and subdomains, return valid URLs with scores."""
    logger = logging.getLogger('discover_ir')
    logger.debug(f"Probing common IR paths for: {homepage_url}")
    
    parsed = urlparse(homepage_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    base_domain = get_base_domain(homepage_url)
    candidates = []
    
    logger.debug(f"Base URL: {base}, Base domain: {base_domain}")
    
    # Probe common paths on main domain
    successful_probes = 0
    for path in COMMON_IR_PATHS:
        probe_url = urljoin(base, path)
        logger.debug(f"Probing path: {probe_url}")
        
        try:
            # Try HEAD first
            r = requests.head(probe_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code < 400:
                normalized = normalize_url(r.url)
                score = score_candidate(normalized, "", homepage_url)
                # BIG bonus for probed paths - these are known good patterns
                candidates.append({
                    "url": normalized,
                    "text": f"(probed: {path})",
                    "score": score + 150  # Increased bonus for common path success
                })
                logger.debug(f"  ✓ Found via HEAD: {normalized} (status: {r.status_code})")
                successful_probes += 1
        except Exception as e:
            # If HEAD fails, try GET (some sites block HEAD)
            try:
                r = requests.get(probe_url, headers=HEADERS, timeout=8, allow_redirects=True)
                if r.status_code < 400:
                    normalized = normalize_url(r.url)
                    score = score_candidate(normalized, "", homepage_url)
                    candidates.append({
                        "url": normalized,
                        "text": f"(probed GET: {path})",
                        "score": score + 150
                    })
                    logger.debug(f"  ✓ Found via GET: {normalized} (status: {r.status_code})")
                    successful_probes += 1
            except Exception as e2:
                logger.debug(f"  ✗ Failed to probe {path}: {e2}")
                continue
    
    # Also probe IR subdomains directly
    ir_subdomains_to_try = ["investors", "investor", "ir", "stock"]
    
    # Special case: Amazon uses ir.aboutamazon.com
    if "amazon.com" in base_domain:
        # Add the full domain as a special case
        try:
            probe_url = f"{parsed.scheme}://ir.aboutamazon.com/"
            r = requests.get(probe_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code < 400:
                normalized = normalize_url(r.url)
                score = score_candidate(normalized, "", homepage_url)
                candidates.append({
                    "url": normalized,
                    "text": "(probed: ir.aboutamazon.com)",
                    "score": score + 250  # Extra bonus for special case
                })
        except Exception:
            pass
    
    for subdomain in ir_subdomains_to_try:
        # Normal subdomain
        probe_url = f"{parsed.scheme}://{subdomain}.{base_domain}"
        
        try:
            # Try HEAD first
            r = requests.head(probe_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code < 400:
                normalized = normalize_url(r.url)
                score = score_candidate(normalized, "", homepage_url)
                # HUGE bonus for IR subdomain
                candidates.append({
                    "url": normalized,
                    "text": f"(probed subdomain: {subdomain})",
                    "score": score + 200  # Even bigger bonus for IR subdomain
                })
        except Exception:
            # If HEAD fails, try GET (some sites block HEAD)
            try:
                r = requests.get(probe_url, headers=HEADERS, timeout=8, allow_redirects=True)
                if r.status_code < 400:
                    normalized = normalize_url(r.url)
                    score = score_candidate(normalized, "", homepage_url)
                    candidates.append({
                        "url": normalized,
                        "text": f"(probed subdomain GET: {subdomain})",
                        "score": score + 200
                    })
            except Exception:
                continue
    
    return candidates


def discover_ir_page(homepage_url):
    """Discover IR page using scoring algorithm."""
    logger = logging.getLogger('discover_ir')
    
    if not homepage_url:
        logger.warning("No homepage URL provided")
        return None, [], None
    
    logger.info(f"Starting IR discovery for: {homepage_url}")
    
    # Collect candidates from homepage
    candidates = discover_candidates_from_page(homepage_url)
    logger.debug(f"Found {len(candidates)} candidates from homepage scraping")
    
    # Add probed paths
    probed = probe_common_paths(homepage_url)
    candidates.extend(probed)
    logger.debug(f"Found {len(probed)} candidates from probing, total: {len(candidates)}")
    
    if not candidates:
        logger.warning("No candidates found during discovery")
        return None, [], None
    
    # Sort by score (desc), then by path complexity (simpler paths preferred for tie-breaking ONLY)
    def sort_key(c):
        url = c['url']
        parsed = urlparse(url)
        path = parsed.path
        
        # Count path depth (fewer slashes = simpler landing page)
        path_depth = path.count('/')
        
        # Return tuple for sorting (higher score first, THEN lower depth for ties)
        return (-c['score'], path_depth, url)
    
    candidates.sort(key=sort_key)
    
    # Log top candidates
    logger.debug("Top 5 candidates after scoring:")
    for i, cand in enumerate(candidates[:5], 1):
        logger.debug(f"  {i}. {cand['url']} (score: {cand['score']})")
    
    # Return best candidate (if score > 0)
    if candidates and candidates[0]["score"] > 0:
        best_url = candidates[0]["url"]
        best_score = candidates[0]["score"]
        logger.info(f"Selected best candidate: {best_url} (score: {best_score})")
        
        # Validate the discovered IR page
        logger.debug("Validating selected IR page...")
        validation = validate_ir_content(best_url)
        
        return best_url, candidates[:5], validation
    
    logger.warning("No candidates with positive score found")
    return None, candidates[:5], None

# # Main output - what you actually use
# --output → "Here are the final IR pages I found for each company"

# # Debug output - how I found them  
# --discovered → "Here's everything I tried and how I scored each option"

def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Starting IR Page Discovery ===")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/discover/dow30_companies.json")
    parser.add_argument("--output", default="data/discover/ir_pages.json")
    parser.add_argument("--discovered", default="data/discover/ir_pages_discovered.json")
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--limit", type=int, default=1, help="Number of companies to process (default: 5)")
    args = parser.parse_args()

    logger.info(f"Arguments: input={args.input}, output={args.output}, discovered={args.discovered}, delay={args.delay}")

    try:
        companies = load_companies(args.input)

        results = []
        discovered_results = []

        logger.info("=== Starting Company Processing ===")
        for i, c in enumerate(companies, 1):
            ticker = c.get("ticker", "UNKNOWN")
            name = c.get("name", "UNKNOWN")
            homepage = c.get("website") or c.get("homepage")
            
            logger.info(f"Processing {i}/{len(companies)}: {ticker} ({name})")
            logger.info(f"  Homepage: {homepage}")
            print(f"Processing {ticker} ({name})...")
            
            # Discover IR page (fully automated)
            ir_page, candidates, validation = discover_ir_page(homepage)
            
            # Log discovery results
            if ir_page:
                logger.info(f"  ✓ Discovered IR page: {ir_page}")
            else:
                logger.warning(f"  ✗ No IR page found for {ticker}")
            
            # Display validation result
            if validation:
                is_valid = validation.get('is_valid')
                conf = validation.get('confidence', 0)
                kw = validation.get('keywords_found', 0)
                
                logger.info(f"  Validation: valid={is_valid}, confidence={conf}, keywords={kw}")
                
                if is_valid is True and conf > 0 and kw > 0:
                    print(f"  ✓ Validated (confidence: {conf}, {kw} IR keywords)")
                elif is_valid is None:
                    print(f"  ⚠ Could not validate (network/timeout error)")
                elif is_valid is False:
                    print(f"  ⚠ Low confidence (score: {conf})")
                else:
                    print(f"  ⚠ Validation uncertain")
            else:
                logger.warning(f"  No validation performed for {ticker}")
            
            results.append({
                "ticker": ticker,
                "name": name,
                "homepage": homepage,
                "ir_page": ir_page,
                "validation": validation
            })
            
            discovered_results.append({
                "ticker": ticker,
                "name": name,
                "homepage": homepage,
                "ir_page": ir_page,
                "candidates": candidates,
                "validation": validation
            })
            
            logger.debug(f"Sleeping for {args.delay} seconds before next company")
            time.sleep(args.delay)
        
        # Write final results
        logger.info("=== Writing Output Files ===")
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Successfully wrote main results to: {args.output}")
        
        # Write discovered (raw) results
        with open(args.discovered, "w", encoding="utf-8") as f:
            json.dump(discovered_results, f, indent=2)
        logger.info(f"Successfully wrote discovery data to: {args.discovered}")
        
        print(f"\nWrote {len(results)} entries to {args.output}")
        print(f"Wrote raw discovery data to {args.discovered}")
        
        # Summary
        discovered_count = sum(1 for r in results if r["ir_page"] is not None)
        null_count = sum(1 for r in results if r["ir_page"] is None)
        
        # Validation summary
        validated = [r for r in results if r.get('validation') and r['validation'].get('is_valid')]
        low_confidence = [r for r in results if r.get('validation') and not r['validation'].get('is_valid')]
        
        logger.info(f"=== FINAL SUMMARY ===")
        logger.info(f"  Total companies processed: {len(results)}")
        logger.info(f"  IR pages discovered: {discovered_count}")
        logger.info(f"  Failed/null results: {null_count}")
        logger.info(f"  Validated (high confidence): {len(validated)}")
        logger.info(f"  Low confidence/needs review: {len(low_confidence)}")
        
        print(f"\nSummary:")
        print(f"  Discovered: {discovered_count}")
        print(f"  Null/failed: {null_count}")
        print(f"\nValidation:")
        print(f"  Validated (high confidence): {len(validated)}")
        print(f"  Low confidence/needs review: {len(low_confidence)}")
        
        if low_confidence:
            print(f"\n⚠️  Low confidence IR pages (review recommended):")
            logger.warning("Low confidence IR pages found:")
            for r in low_confidence:
                conf = r['validation'].get('confidence', 0)
                print(f"    {r['ticker']}: {r['ir_page'][:60]}... (confidence: {conf})")
                logger.warning(f"  {r['ticker']}: {r['ir_page']} (confidence: {conf})")
        
        logger.info("=== IR DISCOVERY COMPLETED SUCCESSFULLY ===")
        
    except Exception as e:
        logger.error(f"Fatal error during IR discovery: {e}")
        print(f"Error: {e}")
        raise
        

if __name__ == "__main__":
    main()
