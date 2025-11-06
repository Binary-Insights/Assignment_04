#!/usr/bin/env python3
"""Fetch Dow 30 list using Yahoo Finance and save tickers + official websites.

Usage:
  python src/discover/fetch_dow30_yfinance.py --output data/discover/dow30_companies.csv
"""
import argparse
import csv
import json
import logging
import os
import re
from urllib.parse import urljoin

import requests
import yfinance as yf
from bs4 import BeautifulSoup

# Dow 30 tickers as of 2024/2025 - these are the current constituents
DOW30_TICKERS = [
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD",
    "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG", "TRV", "UNH", "V", "VZ", "WMT"
]

HEADERS = {"User-Agent": "Project-LANTERN-Bot/1.0 (+https://example.com)"}

def setup_logging():
    """Setup logging for fetch_dow30_yfinance script."""
    # Create logs directory if it doesn't exist
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create unique logger for fetch_dow30_yfinance
    logger = logging.getLogger('fetch_dow30_yfinance')
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(f"{log_dir}/fetch_dow30_yfinance.log")
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


def get_company_info_yfinance(ticker):
    """Get company information using yfinance."""
    logger = logging.getLogger('fetch_dow30_yfinance')
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        company_name = info.get('longName') or info.get('shortName') or ticker
        website = info.get('website') or ""
        
        # Clean up website URL
        if website:
            # Remove tracking parameters
            if "?" in website:
                website = website.split("?")[0]
            # Ensure it starts with http
            if not website.startswith("http"):
                website = "https://" + website
        
        logger.debug(f"Yahoo Finance data for {ticker}: name={company_name}, website={website}")
        return company_name, website
        
    except Exception as e:
        logger.warning(f"Failed to get Yahoo Finance data for {ticker}: {e}")
        return ticker, ""


def find_wikipedia_link(company_name, ticker):
    """Find Wikipedia link for a company."""
    logger = logging.getLogger('fetch_dow30_yfinance')
    
    # Try searching Wikipedia for the company
    search_terms = [
        f"{company_name}",
        f"{company_name} company",
        f"{company_name} corporation",
        f"{ticker}"
    ]
    
    for search_term in search_terms:
        try:
            # Use Wikipedia search API
            search_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term.replace(' ', '_')}"
            response = requests.get(search_url, headers=HEADERS, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('type') == 'standard':
                    wiki_url = data.get('content_urls', {}).get('desktop', {}).get('page', '')
                    if wiki_url:
                        logger.debug(f"Found Wikipedia link for {ticker}: {wiki_url}")
                        return wiki_url
                        
        except Exception as e:
            logger.debug(f"Wikipedia search failed for {search_term}: {e}")
            continue
    
    # Fallback: construct likely Wikipedia URL
    company_wiki_name = company_name.replace(" ", "_").replace("&", "%26")
    fallback_url = f"https://en.wikipedia.org/wiki/{company_wiki_name}"
    
    try:
        # Check if the fallback URL exists
        response = requests.head(fallback_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            logger.debug(f"Using fallback Wikipedia link for {ticker}: {fallback_url}")
            return fallback_url
    except:
        pass
    
    logger.warning(f"No Wikipedia link found for {ticker}")
    return ""


def enhance_website_from_wikipedia(wiki_link, current_website):
    """Enhance website information from Wikipedia if current website is missing or incomplete."""
    logger = logging.getLogger('fetch_dow30_yfinance')
    
    if not wiki_link or current_website:
        return current_website
        
    logger.debug(f"Searching for website on Wikipedia: {wiki_link}")
    
    try:
        response = requests.get(wiki_link, headers=HEADERS, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Look for website in infobox
        infobox = soup.find("table", class_=lambda c: c and "infobox" in c)
        if infobox:
            for row in infobox.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    header_text = th.get_text(strip=True).lower()
                    if any(term in header_text for term in ["website", "url", "homepage"]):
                        a = td.find("a", href=True)
                        if a and a["href"].startswith("http"):
                            website_url = a["href"]
                            if "?" in website_url:
                                website_url = website_url.split("?")[0]
                            logger.debug(f"Found website from Wikipedia: {website_url}")
                            return website_url
        
    except Exception as e:
        logger.warning(f"Failed to enhance website from Wikipedia {wiki_link}: {e}")
    
    return current_website


def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Starting Dow 30 Companies Fetch (Yahoo Finance) ===")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/discover/dow30_companies.csv")
    args = parser.parse_args()
    
    logger.info(f"Arguments: output={args.output}")

    # Create output paths
    csv_output = args.output
    json_output = args.output.replace('.csv', '.json')
    logger.info(f"Output files: CSV={csv_output}, JSON={json_output}")

    # Create output directories if they don't exist
    csv_dir = os.path.dirname(csv_output)
    json_dir = os.path.dirname(json_output)
    
    if csv_dir and not os.path.exists(csv_dir):
        os.makedirs(csv_dir, exist_ok=True)
        logger.info(f"Created directory: {csv_dir}")
    
    if json_dir and json_dir != csv_dir and not os.path.exists(json_dir):
        os.makedirs(json_dir, exist_ok=True)
        logger.info(f"Created directory: {json_dir}")

    try:
        companies = []
        logger.info(f"Processing {len(DOW30_TICKERS)} Dow 30 companies")
        
        for i, ticker in enumerate(DOW30_TICKERS, 1):
            logger.info(f"Processing {i}/{len(DOW30_TICKERS)}: {ticker}")
            
            # Get company info from Yahoo Finance
            company_name, website = get_company_info_yfinance(ticker)
            
            # Find Wikipedia link
            wiki_link = find_wikipedia_link(company_name, ticker)
            
            # Enhance website info from Wikipedia if needed
            if not website:
                website = enhance_website_from_wikipedia(wiki_link, website)
            
            companies.append({
                "ticker": ticker,
                "name": company_name,
                "website": website,
                "wiki_link": wiki_link
            })
            
            logger.info(f"  {ticker}: {company_name}")
            if website:
                logger.info(f"    Website: {website}")
            if wiki_link:
                logger.info(f"    Wikipedia: {wiki_link}")

        # Write CSV and JSON files
        logger.info("=== Writing Output Files ===")
        with open(csv_output, "w", newline='', encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ticker", "name", "website", "wiki_link"])
            writer.writeheader()
            for c in companies:
                writer.writerow({k: c.get(k, "") or "" for k in writer.fieldnames})
        logger.info(f"Successfully wrote CSV file: {csv_output}")

        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(companies, f, indent=2)
        logger.info(f"Successfully wrote JSON file: {json_output}")

        success_msg = f"Wrote {len(companies)} companies to {csv_output} and {json_output}"
        print(success_msg)
        logger.info(f"=== COMPLETED SUCCESSFULLY === {success_msg}")
        
    except Exception as e:
        error_msg = f"Fatal error during execution: {e}"
        logger.error(error_msg)
        print(f"Error: {error_msg}")
        raise


if __name__ == "__main__":
    main()