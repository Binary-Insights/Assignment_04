#!/usr/bin/env python3
"""Debug script to check link extraction from worldlabs.ai"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

url = "https://worldlabs.ai/"

print(f"Fetching: {url}")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
response = requests.get(url, headers=headers, timeout=10, verify=False)
print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)}")

soup = BeautifulSoup(response.text, "html.parser")

# Find all links
all_links = soup.find_all('a', href=True)
print(f"\nTotal <a> tags found: {len(all_links)}")

# Show first 20 links
print("\nFirst 20 links:")
for i, link in enumerate(all_links[:20]):
    href = link.get('href', '').strip()
    text = link.get_text(strip=True)
    print(f"  {i+1}. href='{href}' | text='{text}'")

# Look for career/job links
print("\n--- FILTERING FOR CAREER/JOB LINKS ---")
for link in all_links:
    href = link.get('href', '').strip()
    text = link.get_text(strip=True).lower()
    
    if any(keyword in text for keyword in ['career', 'job', 'join', 'team', 'work', 'hire', 'employ', 'recruit']):
        print(f"MATCH: href='{href}' | text='{text}'")
