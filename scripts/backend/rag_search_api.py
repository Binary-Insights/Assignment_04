"""
FastAPI backend for RAG search endpoint.

Provides /rag/search endpoint for querying the Qdrant vector database.
Supports similarity search with configurable embedding providers.

Usage:
    python scripts/backend/rag_search_api.py
    
    # Or with custom settings:
    QDRANT_URL=http://localhost:6333 \
    EMBEDDING_PROVIDER=hf \
    python scripts/backend/rag_search_api.py

Environment variables:
    QDRANT_URL (default: http://localhost:6333)
    QDRANT_API_KEY (default: "")
    EMBEDDING_PROVIDER (choices: "openai", "hf"; default: auto-detect)
    EMBEDDING_MODEL (default: "text-embedding-3-small" for OpenAI, "all-MiniLM-L6-v2" for HF)
    API_HOST (default: 0.0.0.0)
    API_PORT (default: 8000)
    VERBOSE (set to "1" to enable debug logging)
"""

from __future__ import annotations

import os
import sys
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from qdrant_client import QdrantClient
except ImportError:
    QdrantClient = None


# ─────────────────────────────────────────────────────────────────────────────
#  Configuration & Logging
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  Configuration & Logging
# ─────────────────────────────────────────────────────────────────────────────
log_level = logging.INFO
if os.environ.get("VERBOSE", "0") in ("1", "true", "True"):
    log_level = logging.DEBUG

# Setup logging with both console and file handlers
log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# File handler
log_dir = Path("data/logs")
log_dir.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(log_dir / "rag_search_api.log")
file_handler.setFormatter(log_formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# Configuration from environment
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", None)  # None = auto-detect
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", None)  # None = use defaults
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

logger.info(f"QDRANT_URL: {QDRANT_URL}")
logger.info(f"EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER or 'auto-detect'}")


# ─────────────────────────────────────────────────────────────────────────────
#  Embedding Functions
# ─────────────────────────────────────────────────────────────────────────────
def embed_query_openai(query: str, model: str = "text-embedding-3-small") -> List[float]:
    """Embed a query using OpenAI API."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set for OpenAI embeddings")

    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(input=[query], model=model)
    return response.data[0].embedding


def embed_query_hf(query: str, model: str = "all-MiniLM-L6-v2") -> List[float]:
    """Embed a query using HuggingFace sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    model_instance = SentenceTransformer(model)
    embeddings = model_instance.encode([query], show_progress_bar=False)
    return embeddings[0].tolist()


def choose_embedding_provider(
    prefer_openai: bool = True, hf_model: str = "all-MiniLM-L6-v2"
) -> tuple[callable, str, str]:
    """
    Choose embedding provider and return (embed_fn, provider_name, model_name).
    
    Returns:
        Tuple of (embed_function, provider_name, model_name)
    """
    if prefer_openai and os.environ.get("OPENAI_API_KEY"):
        try:
            import openai  # Quick check
            model = EMBEDDING_MODEL or "text-embedding-3-small"
            return embed_query_openai, "openai", model
        except Exception as e:
            logger.warning(f"OpenAI import failed: {e}, will try HuggingFace")

    try:
        import sentence_transformers
        model = EMBEDDING_MODEL or hf_model
        return (lambda q: embed_query_hf(q, model=model)), f"hf", model
    except Exception:
        raise RuntimeError(
            "No embedding provider available. "
            "Install sentence-transformers or set OPENAI_API_KEY."
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    """Request model for RAG search."""
    
    query: str = Field(..., min_length=1, description="Search query")
    collection_name: str = Field(
        default="rag_chunks",
        description="Qdrant collection to search"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of top results to return"
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similarity score threshold (0-1). None = no threshold"
    )


class ChunkResult(BaseModel):
    """A single search result chunk."""
    
    id: int
    similarity_score: float
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Response model for RAG search."""
    
    query: str
    collection_name: str
    results: List[ChunkResult]
    total_results: int
    provider: str
    model: str


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    qdrant_url: str
    qdrant_connected: bool


# ─────────────────────────────────────────────────────────────────────────────
#  Qdrant Search Functions
# ─────────────────────────────────────────────────────────────────────────────
def search_qdrant(
    query_embedding: List[float],
    collection_name: str,
    top_k: int = 5,
    threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Search Qdrant collection for similar vectors.
    
    Args:
        query_embedding: Query vector
        collection_name: Qdrant collection name
        top_k: Number of results to return
        threshold: Similarity threshold (0-1)
    
    Returns:
        List of results with id, score, and payload
    """
    if QdrantClient is None:
        raise RuntimeError("qdrant-client not installed")

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    
    # Suppress warnings about client version mismatch
    logger.debug(f"Searching collection '{collection_name}' with top_k={top_k}")
    
    try:
        search_result = client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=threshold,
        )
        
        results = []
        for point in search_result:
            results.append({
                "id": point.id,
                "score": point.score,
                "payload": point.payload or {},
            })
        
        logger.debug(f"Found {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Qdrant search failed: {str(e)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI Application Lifespan
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    global embed_fn, provider_name, model_name
    
    logger.info("Starting RAG Search API...")
    
    try:
        # Determine provider preference
        prefer_openai = True
        if EMBEDDING_PROVIDER == "hf":
            prefer_openai = False
        elif EMBEDDING_PROVIDER == "openai":
            prefer_openai = True
        
        embed_fn, provider_name, model_name = choose_embedding_provider(
            prefer_openai=prefer_openai,
            hf_model="all-MiniLM-L6-v2"
        )
        
        logger.info(f"Using embedding provider: {provider_name} ({model_name})")
        
        # Test Qdrant connection
        if QdrantClient is not None:
            client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
            try:
                info = client.get_collection("rag_chunks")
                logger.info(f"Connected to Qdrant collection 'rag_chunks': {info.points_count} points")
            except Exception as e:
                logger.warning(f"Could not verify Qdrant collection: {e}")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG Search API...")


# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI Application
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RAG Search API",
    description="Vector similarity search against Qdrant database",
    version="1.0.0",
    lifespan=lifespan,
)

# Initialize embedding provider at module level
embed_fn = None
provider_name = None
model_name = None


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    qdrant_connected = False
    
    if QdrantClient is not None:
        try:
            client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
            client.get_collection("qdrant")  # Try to get collections
            qdrant_connected = True
        except Exception:
            qdrant_connected = False
    
    return HealthResponse(
        status="ok",
        qdrant_url=QDRANT_URL,
        qdrant_connected=qdrant_connected,
    )


@app.post("/rag/search", response_model=SearchResponse)
async def rag_search(request: SearchRequest) -> SearchResponse:
    """
    Search the RAG vector database for similar chunks.
    
    This endpoint:
    1. Embeds the query using the configured embedding provider
    2. Searches Qdrant for similar vectors
    3. Returns top-k chunks with metadata
    
    Query examples:
    - "funding and investment" - retrieves chunks about company funding
    - "leadership team" - retrieves chunks about company leaders
    - "what is spatial intelligence?" - retrieves relevant topic chunks
    - "careers and job opportunities" - retrieves job-related chunks
    
    Args:
        request: SearchRequest with query, collection_name, top_k, threshold
    
    Returns:
        SearchResponse with results
    
    Raises:
        HTTPException: If embedding or search fails
    """
    if embed_fn is None:
        raise HTTPException(
            status_code=500,
            detail="Embedding provider not initialized"
        )
    
    logger.info(f"Search request: query='{request.query}', collection='{request.collection_name}', top_k={request.top_k}")
    
    try:
        # Embed the query
        logger.debug("Embedding query...")
        query_embedding = embed_fn(request.query)
        logger.debug(f"Query embedded: {len(query_embedding)} dimensions")
        
        # Search Qdrant
        logger.debug("Searching Qdrant...")
        results = search_qdrant(
            query_embedding=query_embedding,
            collection_name=request.collection_name,
            top_k=request.top_k,
            threshold=request.threshold,
        )
        
        # Convert results to response model
        chunk_results = []
        for result in results:
            payload = result.get("payload", {})
            chunk_text = payload.get("text", "")
            
            # Extract just the first 500 chars for preview (full text available in metadata)
            text_preview = chunk_text[:500] if len(chunk_text) > 500 else chunk_text
            
            chunk_results.append(
                ChunkResult(
                    id=result["id"],
                    similarity_score=result["score"],
                    text=text_preview,
                    metadata=payload,
                )
            )
        
        logger.info(f"Returning {len(chunk_results)} results")
        
        return SearchResponse(
            query=request.query,
            collection_name=request.collection_name,
            results=chunk_results,
            total_results=len(chunk_results),
            provider=provider_name,
            model=model_name,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "RAG Search API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "search": "/rag/search",
            "docs": "/docs",
            "redoc": "/redoc",
        },
        "provider": provider_name,
        "model": model_name,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting RAG Search API on {API_HOST}:{API_PORT}")
    logger.info(f"Qdrant URL: {QDRANT_URL}")
    logger.info(f"API docs: http://{API_HOST}:{API_PORT}/docs")
    
    uvicorn.run(
        "rag_search_api:app",
        host=API_HOST,
        port=API_PORT,
        reload=os.environ.get("DEBUG", "0") == "1",
        log_level="debug" if log_level == logging.DEBUG else "info",
    )
