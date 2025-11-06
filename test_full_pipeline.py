#!/usr/bin/env python3
"""
Test script to simulate the full Streamlit + FastAPI flow for context results.
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
    print(f"✅ Loaded environment from: {env_path}")
    print(f"   OPENAI_API_KEY: {'Set' if os.environ.get('OPENAI_API_KEY') else 'NOT SET'}")
except ImportError:
    print("dotenv not available, skipping .env loading")

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "rag"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "backend"))

def test_full_pipeline():
    """Test the complete dashboard generation pipeline"""
    print("\n" + "=" * 80)
    print("Testing Full Dashboard Generation Pipeline")
    print("=" * 80)
    
    try:
        from rag_pipeline import generate_dashboard_with_retrieval
        from qdrant_client import QdrantClient
        from pydantic import BaseModel, Field
        from typing import List, Dict, Any
        
        # Define response models
        class ChunkResult(BaseModel):
            id: int
            similarity_score: float
            text: str
            metadata: Dict[str, Any] = Field(default_factory=dict)
        
        class DashboardRAGResponse(BaseModel):
            company_name: str
            company_slug: str
            markdown: str = Field(description="Dashboard markdown content")
            context_results: List[ChunkResult] = Field(default_factory=list)
            status: str = "success"
            message: str = ""
        
        # Initialize Qdrant client
        QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
        QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
        
        print(f"\n1. Initializing Qdrant client at {QDRANT_URL}")
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None, check_compatibility=False)
        
        # Test with World Labs
        company_name = "World Labs"
        company_slug = "world-labs"
        
        print(f"\n2. Generating dashboard for: {company_name}")
        
        # Call the function
        dashboard_markdown, search_results = generate_dashboard_with_retrieval(
            company_name=company_name,
            company_slug=company_slug,
            qdrant_client=client,
            llm_client=None,
            llm_model="gpt-4o",
            top_k=10
        )
        
        print(f"\n3. Converting results to Pydantic models...")
        
        # Convert search results to ChunkResult format (like the API does)
        context_results = []
        for result in search_results:
            chunk_result = ChunkResult(
                id=len(context_results),
                similarity_score=result.get("similarity_score", 0.0),
                text=result.get("text", ""),
                metadata=result.get("metadata", {})
            )
            context_results.append(chunk_result)
        
        # Create response
        response = DashboardRAGResponse(
            company_name=company_name,
            company_slug=company_slug,
            markdown=dashboard_markdown,
            context_results=context_results,
            status="success",
            message=f"Dashboard generated successfully for {company_name}"
        )
        
        print(f"\n4. Response created:")
        print(f"   - Company: {response.company_name}")
        print(f"   - Context results: {len(response.context_results)}")
        print(f"   - Dashboard length: {len(response.markdown)} chars")
        
        # Convert to JSON (what the API returns)
        response_dict = response.model_dump()
        json_response = json.dumps(response_dict)
        
        print(f"\n5. JSON response size: {len(json_response)} bytes")
        print(f"   - First 200 chars: {json_response[:200]}...")
        
        # Verify context_results are in the JSON
        parsed = json.loads(json_response)
        print(f"\n6. Parsed JSON verification:")
        print(f"   - context_results in response: {'context_results' in parsed}")
        print(f"   - context_results count: {len(parsed.get('context_results', []))}")
        
        if parsed.get('context_results'):
            first = parsed['context_results'][0]
            print(f"\n7. First context result in JSON:")
            print(f"   - ID: {first.get('id')}")
            print(f"   - Score: {first.get('similarity_score'):.4f}")
            print(f"   - Text length: {len(first.get('text', ''))}")
            print(f"   - Metadata keys: {list(first.get('metadata', {}).keys())}")
        
        print(f"\n✅ Full pipeline test completed successfully!")
        print(f"   Context results ARE being serialized correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 Testing Full Dashboard Generation + Context Results\n")
    success = test_full_pipeline()
    
    print("\n" + "=" * 80)
    print("RESULT")
    print("=" * 80)
    if success:
        print("✅ Context results are being generated and serialized correctly!")
        print("\nIf the frontend still isn't showing them, check:")
        print("   1. Is the FastAPI server running and returning 200 OK?")
        print("   2. Is the Streamlit app receiving the response?")
        print("   3. Check browser developer console for any JavaScript errors")
    else:
        print("❌ Pipeline test failed")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
