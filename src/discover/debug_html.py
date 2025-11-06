#!/usr/bin/env python3
"""Debug script to inspect worldlabs.ai HTML structure"""

import requests
from bs4 import BeautifulSoup

url = "https://worldlabs.ai/"

print(f"Fetching: {url}")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
response = requests.get(url, headers=headers, timeout=10, verify=False)
print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)}\n")

# Print first 2000 chars of HTML
print("=== RAW HTML (first 2000 chars) ===")
print(response.text[:2000])
print("\n=== LOOKING FOR KEYWORDS ===")

text = response.text.lower()
keywords = ['career', 'job', 'join', 'team', 'work', 'ashby', 'href', '<a ', 'onclick', 'click']
for kw in keywords:
    count = text.count(kw)
    if count > 0:
        print(f"'{kw}': found {count} times")

# Check if it's a React/Next.js app
print("\n=== CHECKING FOR JS FRAMEWORKS ===")
if 'next.js' in text:
    print("✓ Next.js detected")
if 'react' in text:
    print("✓ React detected")
if '_next' in text:
    print("✓ Next.js assets detected (_next/)")
if 'script' in response.text:
    print(f"✓ Script tags found: {response.text.count('<script')}")
