#!/usr/bin/env python3
"""Debug script to test context retrieval."""

import json
import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add rag module to path
sys.path.insert(0, str(Path(__file__).parent / "scripts" / "rag"))

from rag_pipeline import generate_dashboard_with_retrieval

# Test with World Labs
company_name = "World Labs"
company_slug = "world-labs"

try:
    # Initialize Qdrant client
    from qdrant_client import QdrantClient
    
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
    
    logger.info(f"Connecting to Qdrant at {qdrant_url}")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, check_compatibility=False)
    
    # Initialize LLM client
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    llm_client = OpenAI(api_key=api_key) if api_key else None
    
    logger.info(f"Testing dashboard generation for {company_name}")
    
    # Call the function
    dashboard, search_results = generate_dashboard_with_retrieval(
        company_name=company_name,
        company_slug=company_slug,
        qdrant_client=client,
        llm_client=llm_client,
        top_k=10
    )
    
    logger.info(f"✅ Retrieved {len(search_results)} results")
    
    if search_results:
        logger.info(f"First result text length: {len(search_results[0].get('text', ''))}")
        logger.info(f"First result score: {search_results[0].get('similarity_score', 0)}")
        print("\n" + "="*80)
        print(f"RESULTS SUMMARY:")
        print(f"  Total results: {len(search_results)}")
        print(f"  Dashboard length: {len(dashboard)}")
        print("="*80 + "\n")
        
        # Print each result summary
        for i, result in enumerate(search_results, 1):
            print(f"\nResult {i}:")
            print(f"  Score: {result.get('similarity_score', 0):.4f}")
            print(f"  Text length: {len(result.get('text', ''))}")
            print(f"  Text preview: {result.get('text', '')[:100]}...")
    else:
        logger.error("❌ No results returned!")
        
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    sys.exit(1)
