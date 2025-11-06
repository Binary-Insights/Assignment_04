#!/usr/bin/env python3
"""
Test script to verify the FastAPI endpoint returns context_results
"""

import requests
import json
import time

API_BASE = "http://localhost:8000"
COMPANY_NAME = "World Labs"

print(f"\n🔍 Testing FastAPI endpoint: POST /dashboard/rag")
print(f"   Company: {COMPANY_NAME}")
print(f"   API Base: {API_BASE}\n")

try:
    print("1. Sending POST request...")
    response = requests.post(
        f"{API_BASE}/dashboard/rag",
        params={"company_name": COMPANY_NAME},
        timeout=30
    )
    
    print(f"   Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        print(f"\n2. Response structure:")
        print(f"   Keys: {list(data.keys())}")
        
        print(f"\n3. Response details:")
        print(f"   - company_name: {data.get('company_name')}")
        print(f"   - company_slug: {data.get('company_slug')}")
        print(f"   - status: {data.get('status')}")
        print(f"   - markdown length: {len(data.get('markdown', ''))}")
        print(f"   - context_results type: {type(data.get('context_results'))}")
        print(f"   - context_results count: {len(data.get('context_results', []))}")
        
        if data.get('context_results'):
            print(f"\n4. First context result:")
            first = data['context_results'][0]
            print(f"   - Keys: {list(first.keys())}")
            print(f"   - ID: {first.get('id')}")
            print(f"   - Similarity score: {first.get('similarity_score')}")
            print(f"   - Text length: {len(first.get('text', ''))}")
            print(f"   - Text preview: {first.get('text', '')[:100]}...")
            print(f"   - Metadata: {first.get('metadata', {})}")
            
            print(f"\n✅ SUCCESS - Context results are being returned!")
        else:
            print(f"\n❌ WARNING - No context results in response!")
            print(f"   Full response: {json.dumps(data, indent=2)[:500]}...")
    else:
        print(f"   Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print(f"❌ ERROR: Could not connect to API at {API_BASE}")
    print("   Make sure the FastAPI server is running:")
    print("   cd src/backend && python rag_search_api.py")
except Exception as e:
    print(f"❌ ERROR: {e}")

print("\n" + "=" * 80)
