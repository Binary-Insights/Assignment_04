#!/usr/bin/env python3
"""
Debug script to test if context_results are being returned from the API.
"""

import sys
import os
import json
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)
    print(f"Loaded environment from: {env_path}")
except ImportError:
    print("dotenv not available, skipping .env loading")

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "rag"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "backend"))

def test_rag_extraction():
    """Test the RAG extraction module directly"""
    print("=" * 80)
    print("Testing RAG Extraction Module")
    print("=" * 80)
    
    try:
        from rag_pipeline import generate_dashboard_with_retrieval
        from qdrant_client import QdrantClient
        
        # Initialize Qdrant client
        QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
        QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
        
        print(f"\n1. Initializing Qdrant client at {QDRANT_URL}")
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None, check_compatibility=False)
        
        # Test with World Labs
        company_name = "World Labs"
        company_slug = "world-labs"
        
        print(f"\n2. Testing RAG extraction for: {company_name}")
        print(f"   Company slug: {company_slug}")
        
        # Call the function
        print(f"\n3. Calling generate_dashboard_with_retrieval()...")
        dashboard_markdown, search_results = generate_dashboard_with_retrieval(
            company_name=company_name,
            company_slug=company_slug,
            qdrant_client=client,
            llm_client=None,
            llm_model="gpt-4o",
            top_k=10
        )
        
        print(f"\n4. Results received:")
        print(f"   - Dashboard markdown length: {len(dashboard_markdown)} chars")
        print(f"   - Search results count: {len(search_results)}")
        
        if search_results:
            print(f"\n5. First result details:")
            first_result = search_results[0]
            print(f"   - Text: {first_result.get('text', '')[:100]}...")
            print(f"   - Similarity score: {first_result.get('similarity_score', 0)}")
            print(f"   - Metadata: {first_result.get('metadata', {})}")
            
            print(f"\n6. All results summary:")
            for idx, result in enumerate(search_results, 1):
                print(f"   Result {idx}: score={result.get('similarity_score', 0):.4f}, text_len={len(result.get('text', ''))}")
        else:
            print("\n5. ERROR: No search results returned!")
        
        print("\n✅ Test completed successfully")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_pydantic_serialization():
    """Test if Pydantic models serialize correctly"""
    print("\n" + "=" * 80)
    print("Testing Pydantic Serialization")
    print("=" * 80)
    
    try:
        from pydantic import BaseModel, Field
        from typing import List, Dict, Any
        
        class ChunkResult(BaseModel):
            id: int
            similarity_score: float
            text: str
            metadata: Dict[str, Any] = Field(default_factory=dict)
        
        class DashboardRAGResponse(BaseModel):
            company_name: str
            company_slug: str
            markdown: str = Field(description="Dashboard markdown content")
            context_results: List[ChunkResult] = Field(default_factory=list, description="Top-k context chunks retrieved from Qdrant")
            status: str = "success"
            message: str = ""
        
        # Create test response
        chunk1 = ChunkResult(
            id=1,
            similarity_score=0.95,
            text="This is test context",
            metadata={"source": "test"}
        )
        
        response = DashboardRAGResponse(
            company_name="Test Company",
            company_slug="test-company",
            markdown="# Test\n\nThis is a test",
            context_results=[chunk1],
            message="Test message"
        )
        
        # Serialize to dict
        response_dict = response.model_dump()
        
        print(f"\n1. Response serialized successfully")
        print(f"   - Company: {response_dict['company_name']}")
        print(f"   - Context results count: {len(response_dict['context_results'])}")
        
        if response_dict['context_results']:
            print(f"\n2. First context result:")
            result = response_dict['context_results'][0]
            print(f"   - ID: {result['id']}")
            print(f"   - Score: {result['similarity_score']}")
            print(f"   - Text: {result['text']}")
            print(f"   - Metadata: {result['metadata']}")
        
        # Try JSON serialization
        json_str = json.dumps(response_dict)
        print(f"\n3. JSON serialization: ✅ Success ({len(json_str)} chars)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during Pydantic test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 Testing Context Results Flow\n")
    
    # Test Pydantic first (should always work)
    pydantic_ok = test_pydantic_serialization()
    
    # Test RAG extraction
    rag_ok = test_rag_extraction()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Pydantic Serialization: {'✅ PASS' if pydantic_ok else '❌ FAIL'}")
    print(f"RAG Extraction Module: {'✅ PASS' if rag_ok else '❌ FAIL'}")
    print("=" * 80)
    
    sys.exit(0 if (pydantic_ok and rag_ok) else 1)
