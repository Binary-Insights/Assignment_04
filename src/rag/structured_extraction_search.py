#!/usr/bin/env python3
"""RAG-based Structured Extraction: Extract and normalize company data using semantic search.

This script:
1. Reads text extracted from company web pages (data/raw/{company_slug}/{page_type}/text.txt)
2. Queries Pinecone vector database to retrieve relevant context
3. Uses instructor + OpenAI to extract structured data into Pydantic models
4. Normalizes messy text data into clean, structured format
5. Saves results as data/payloads/{company_slug}/{company_id}.json

The extraction follows the schema defined in rag_models.py:
- Company (legal_name, website, headquarters, founding date, funding, etc.)
- Event (funding rounds, M&A, product releases, etc.)
- Snapshot (headcount, job openings, pricing, etc.)
- Product (description, pricing model, integrations, etc.)
- Leadership (founders, executives, roles, etc.)
- Visibility (news mentions, GitHub stars, ratings, etc.)

NOTE: This script expects Pinecone to be already indexed. Run ingest_to_pinecone.py first.

Usage:
  python src/rag/structured_extraction.py --company-slug world_labs
  python src/rag/structured_extraction.py --company-slug world_labs --verbose
  python src/rag/structured_extraction.py --all
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import instructor
from openai import OpenAI
from pydantic import BaseModel, ValidationError, Field
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings

# Import Pydantic models
sys.path.insert(0, str(Path(__file__).parent))
from rag_models import (
    Company, Event, Snapshot, Product, Leadership, Visibility, 
    Payload, Provenance
)

# Load environment variables
load_dotenv()

# Global configuration
FALLBACK_STRATEGY = 'pinecone_first'  # Can be: 'pinecone_only', 'raw_only', 'pinecone_first'
USE_RAW_TEXT = False  # Set to True to skip Pinecone and use raw text directly
PINECONE_SEARCH_LIMIT = 10  # Increased from 5 to get more results per query
PINECONE_MIN_SIMILARITY = 0.0  # Minimum similarity score (0.0 = accept all results)


def setup_logging(script_name: str = 'structured_extraction'):
    """Setup logging for extraction script."""
    log_dir = "data/logs"
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    file_handler = logging.FileHandler(f"{log_dir}/{script_name}.log")
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


def get_llm_client():
    """Initialize OpenAI client with instructor patch."""
    logger = logging.getLogger('structured_extraction')
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error("OPENAI_API_KEY not set in environment")
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    # Create base OpenAI client
    base_client = OpenAI(api_key=api_key)
    
    # Patch with instructor - this modifies the client in place and returns it
    try:
        client = instructor.patch(
            base_client,
            mode=instructor.Mode.TOOLS,  # Use TOOLS mode for better compatibility
        )
        logger.info("Initialized OpenAI client with instructor (TOOLS mode)")
    except Exception as e:
        logger.warning(f"Failed to patch with TOOLS mode, trying MD_JSON: {e}")
        try:
            client = instructor.patch(
                base_client,
                mode=instructor.Mode.MD_JSON,
            )
            logger.info("Initialized OpenAI client with instructor (MD_JSON mode)")
        except Exception as e2:
            logger.warning(f"Failed to patch with MD_JSON mode, using standard: {e2}")
            client = instructor.patch(base_client)
            logger.info("Initialized OpenAI client with instructor (standard mode)")
    
    return client


def get_pinecone_client():
    """Initialize Pinecone client for vector search."""
    logger = logging.getLogger('structured_extraction')
    
    # Get Pinecone configuration from environment
    api_key = os.getenv('PINECONE_API_KEY')
    if not api_key:
        logger.error("PINECONE_API_KEY not set in environment")
        raise ValueError("PINECONE_API_KEY environment variable is required")
    
    index_name = os.getenv('PINECONE_INDEX_NAME', 'bigdata-assignment-04')
    logger.info(f"Attempting to connect to Pinecone index: {index_name}")
    
    try:
        # Initialize Pinecone client
        pc = Pinecone(api_key=api_key)
        
        # Get index reference
        index = pc.Index(index_name)
        
        # Test connection by getting index stats
        try:
            logger.info("Testing Pinecone connection...")
            stats = index.describe_index_stats()
            logger.info(f"✅ Successfully connected to Pinecone index '{index_name}'")
            logger.info(f"   Namespaces: {list(stats.namespaces.keys()) if stats.namespaces else 'default'}")
            logger.info(f"   Total vectors: {stats.total_vector_count}")
            return index
        except Exception as test_error:
            logger.error(f"❌ Failed to verify Pinecone connection: {test_error}")
            raise
    except Exception as e:
        logger.warning(f"Failed to connect to Pinecone: {e}")
        logger.info("Will proceed without vector search (using raw text instead)")
        return None


def get_embeddings_model():
    """Get OpenAI embeddings model."""
    logger = logging.getLogger('structured_extraction')
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error("OPENAI_API_KEY not set for embeddings")
        raise ValueError("OPENAI_API_KEY required for embeddings")
    
    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=api_key
        )
        logger.debug("Initialized OpenAI embeddings model (text-embedding-3-large, dimension: 3072)")
        return embeddings
    except Exception as e:
        logger.error(f"Failed to initialize embeddings: {e}")
        raise


def search_pinecone_for_context(
    query: str,
    company_slug: str,
    pinecone_index,
    embeddings: Optional[OpenAIEmbeddings],
    limit: int = 10,
    min_similarity: float = 0.0
) -> List[Dict[str, Any]]:
    """Search Pinecone for relevant context using semantic search with lenient matching."""
    logger = logging.getLogger('structured_extraction')
    
    if not pinecone_index or not embeddings:
        logger.debug("Cannot search Pinecone - index/embeddings missing")
        return []
    
    namespace = os.getenv('PINECONE_NAMESPACE', 'default')
    
    try:
        # Generate embedding for query
        query_embedding = embeddings.embed_query(query)
        
        # Search Pinecone without company filter - rely on semantic relevance
        # Note: We removed the company_slug filter because company_id (hyphenated) 
        # doesn't match company_slug (underscored) in metadata
        logger.debug(f"🔍 Searching Pinecone (namespace '{namespace}'): '{query}'")
        results = pinecone_index.query(
            vector=query_embedding,
            top_k=limit,
            namespace=namespace,
            include_metadata=True
        )
        
        # Extract context from results with full source tracking
        context_docs = []
        for idx, match in enumerate(results.matches, 1):
            # Filter by minimum similarity
            if match.score >= min_similarity:
                doc = {
                    "text": match.metadata.get("text", ""),
                    "page_type": match.metadata.get("page_type", ""),
                    "score": match.score,
                    "source_file": match.metadata.get("source_file", ""),
                    "chunk_index": match.metadata.get("chunk_index", ""),
                    "vector_id": match.id,
                }
                context_docs.append(doc)
                logger.debug(f"  🎯 Rank {idx}: {doc['source_file']} (chunk {doc['chunk_index']}, similarity: {match.score:.3f})")
        
        logger.debug(f"✅ Pinecone search returned {len(context_docs)} documents (filtered by min_similarity >= {min_similarity})")
        return context_docs
        
    except Exception as e:
        logger.warning(f"❌ Error searching Pinecone: {e}")
        return []


def log_extraction_sources(
    extraction_type: str,
    company_id: str,
    search_queries: List[str],
    context_docs: List[Dict[str, Any]]
) -> None:
    """Log detailed source information for validation."""
    logger = logging.getLogger('structured_extraction')
    
    if not context_docs:
        logger.warning(f"  ⚠️  No Pinecone sources found for {extraction_type}")
        return
    
    logger.info(f"\n  📊 {extraction_type.upper()} - Source Validation:")
    logger.info(f"  {'─' * 70}")
    
    # Group by source file
    sources_by_file = {}
    for doc in context_docs:
        source_file = doc.get('source_file', 'unknown')
        if source_file not in sources_by_file:
            sources_by_file[source_file] = []
        sources_by_file[source_file].append(doc)
    
    # Log each source
    for source_file in sorted(sources_by_file.keys()):
        docs = sources_by_file[source_file]
        logger.info(f"  Source: {source_file}")
        logger.info(f"    Chunks used: {len(docs)}")
        for doc in docs:
            logger.info(f"      • Vector ID {doc['vector_id']}: chunk {doc['chunk_index']} (similarity: {doc['score']:.3f})")
        logger.info(f"    Content preview: {docs[0]['text'][:100]}...")
    
    logger.info(f"  {'─' * 70}\n")


def should_use_fallback(context_docs: List[Dict[str, Any]], extraction_type: str) -> bool:
    """Determine if fallback should be used based on strategy and context availability."""
    logger = logging.getLogger('structured_extraction')
    
    global FALLBACK_STRATEGY
    
    if context_docs:
        # We have context, no fallback needed
        return False
    
    # No context available, check strategy
    if FALLBACK_STRATEGY == 'pinecone_only':
        logger.error(f"❌ Strategy 'pinecone_only': No Pinecone results for {extraction_type}, FAILING")
        return False
    elif FALLBACK_STRATEGY == 'raw_only':
        logger.warning(f"⚠️  Strategy 'raw_only': Ignoring Pinecone, using raw text for {extraction_type}")
        return True
    elif FALLBACK_STRATEGY == 'pinecone_first':
        logger.warning(f"⚠️  Strategy 'pinecone_first': Fallback to raw text for {extraction_type}")
        return True
    
    return False


def load_company_page_text(company_slug: str, page_type: str) -> Optional[str]:
    """Load extracted text from a company page."""
    logger = logging.getLogger('structured_extraction')
    
    text_file = f"data/raw/{company_slug}/{page_type}/text.txt"
    
    if not Path(text_file).exists():
        logger.debug(f"Text file not found: {text_file}")
        return None
    
    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        logger.debug(f"Loaded text from {text_file}: {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"Failed to load text from {text_file}: {e}")
        return None


def load_all_company_pages(company_slug: str) -> Dict[str, str]:
    """Load all extracted text pages for a company."""
    logger = logging.getLogger('structured_extraction')
    
    company_raw_dir = Path(f"data/raw/{company_slug}")
    if not company_raw_dir.exists():
        logger.warning(f"Company directory not found: {company_raw_dir}")
        return {}
    
    pages_text = {}
    page_types = [d.name for d in company_raw_dir.iterdir() if d.is_dir()]
    
    for page_type in sorted(page_types):
        text = load_company_page_text(company_slug, page_type)
        if text:
            pages_text[page_type] = text
            logger.info(f"Loaded {page_type} page: {len(text)} chars")
    
    logger.info(f"Loaded {len(pages_text)} pages for {company_slug}")
    return pages_text


def extract_company_info(
    client, 
    company_name: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> Optional[Company]:
    """Extract company information using LLM with instructor and Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting company info for {company_name}...")
    
    # Build search queries for company information
    search_queries = [
        f"company {company_name} legal name brand headquarters location founded",
        f"{company_name} website URL domain",
        f"{company_name} categories industry vertical",
        f"{company_name} funding raised valuation investment round",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for company info")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search
        for query in search_queries:
            docs = search_pinecone_for_context(query, company_name, pinecone_index, embeddings, limit=3)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Pinecone context for company extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:300]}"
                for doc in context_docs[:10]  # Limit to top 10 results
            ])
        else:
            logger.error("❌ No Pinecone results for company info - ABORTING")
            raise ValueError("No Pinecone context available and raw text mode is disabled")
    
    # Log extraction sources for validation
    log_extraction_sources("Company Info", company_name, search_queries, context_docs)
    
    prompt = f"""Extract company information for "{company_name}" from the following web content and context:

{context_text}

Return a structured Company record with all available information.
- Use ONLY explicitly stated information
- Generate company_id from the website domain (e.g., "world-labs" from "worldlabs.ai")
- Use null for missing fields
- Do NOT infer or guess
- Standardize dates to YYYY-MM-DD format"""
    
    try:
        # Use instructor's patched client with response_model
        company = client.chat.completions.create(
            model="gpt-4o",
            response_model=Company,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,  # Lower temperature for consistency
        )
        logger.info(f"✓ Successfully extracted company: {company.legal_name if hasattr(company, 'legal_name') else 'Unknown'}")
        return company
    except ValidationError as e:
        logger.error(f"Validation error extracting company: {e}")
        return None
    except Exception as e:
        logger.error(f"Error extracting company info: {e}", exc_info=True)
        return None


def extract_events(
    client, 
    company_id: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> List[Event]:
    """Extract events (funding, M&A, partnerships, etc.) using LLM and Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting events for {company_id}...")
    
    # Build search queries for events - using content from pages
    search_queries = [
        f"{company_id} funding investment raised capital",
        f"{company_id} announcement news update",
        f"{company_id} partnership integration collaboration",
        f"{company_id} product launch release",
        f"{company_id} team hiring expansion",
        f"Series funding round investment",
    ]
    
    # Fallback queries if primary queries return no results
    fallback_queries = [
        "funding",
        "investment",
        "money",
        "capital",
        "announcement",
        "partnership",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    global FALLBACK_STRATEGY
    global PINECONE_SEARCH_LIMIT
    global PINECONE_MIN_SIMILARITY
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for events")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search with primary queries
        logger.debug(f"Trying primary search queries for events...")
        for query in search_queries:
            docs = search_pinecone_for_context(
                query, company_id, pinecone_index, embeddings, 
                limit=PINECONE_SEARCH_LIMIT,
                min_similarity=PINECONE_MIN_SIMILARITY
            )
            context_docs.extend(docs)
        
        # If no results, try fallback queries
        if not context_docs:
            logger.info(f"No results with primary queries, trying fallback queries...")
            for query in fallback_queries:
                docs = search_pinecone_for_context(
                    query, company_id, pinecone_index, embeddings, 
                    limit=PINECONE_SEARCH_LIMIT,
                    min_similarity=PINECONE_MIN_SIMILARITY
                )
                context_docs.extend(docs)
        
        if context_docs:
            logger.info(f"📊 Using {len(context_docs)} Pinecone results for events extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:20]  # Limit to top 20 results
            ])
        else:
            # No Pinecone results - check fallback strategy
            if FALLBACK_STRATEGY == 'pinecone_only':
                logger.error("❌ No Pinecone results for events - ABORTING (pinecone_only strategy)")
                raise ValueError("No Pinecone context available for events")
            else:
                logger.warning(f"⚠️  No Pinecone results for events - Falling back to raw text ({FALLBACK_STRATEGY})")
                context_text = json.dumps(pages_text, indent=2)[:3000]
    prompt = f"""Extract all significant events for company ID "{company_id}" from the web content:

{context_text}

Include:
- Funding rounds (Series A/B/C, seed, etc.) with amounts and dates
- M&A activities (acquisitions, mergers)
- Product launches and releases
- Partnerships and integrations
- Key hires and leadership changes
- Layoffs and restructuring
- Major milestones and achievements

For each event:
- Provide: event_type, occurred_on date (YYYY-MM-DD), title, description
- If it's a funding event, include amount_usd and valuation_usd
- Use only explicitly stated information
- Use null for missing fields

Return a list of Event objects."""
    
    try:
        # Define a wrapper model to handle list return
        class EventList(BaseModel):
            events: List[Event] = Field(default_factory=list)
        
        result = client.chat.completions.create(
            model="gpt-4o",
            response_model=EventList,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )
        
        logger.info(f"✓ Extracted {len(result.events)} events")
        return result.events
    except Exception as e:
        logger.warning(f"Error extracting events: {e}")
        return []


def extract_snapshots(
    client, 
    company_id: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> List[Snapshot]:
    """Extract business snapshots (headcount, products, pricing, etc.) using Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting snapshots for {company_id}...")
    
    # Search queries for snapshot data - using content from pages
    search_queries = [
        f"{company_id} team size headcount employees",
        f"{company_id} pricing model plans features",
        f"{company_id} products services offerings",
        f"{company_id} hiring jobs positions openings",
        f"{company_id} customers clients enterprise",
        f"AI artificial intelligence technology platform",
    ]
    
    # Fallback queries if primary queries return no results
    fallback_queries = [
        "team",
        "headcount",
        "employees",
        "pricing",
        "products",
        "hiring",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    global FALLBACK_STRATEGY
    global PINECONE_SEARCH_LIMIT
    global PINECONE_MIN_SIMILARITY
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for snapshots")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search with primary queries
        logger.debug(f"Trying primary search queries for snapshots...")
        for query in search_queries:
            docs = search_pinecone_for_context(
                query, company_id, pinecone_index, embeddings,
                limit=PINECONE_SEARCH_LIMIT,
                min_similarity=PINECONE_MIN_SIMILARITY
            )
            context_docs.extend(docs)
        
        # If no results, try fallback queries
        if not context_docs:
            logger.info(f"No results with primary queries, trying fallback queries...")
            for query in fallback_queries:
                docs = search_pinecone_for_context(
                    query, company_id, pinecone_index, embeddings,
                    limit=PINECONE_SEARCH_LIMIT,
                    min_similarity=PINECONE_MIN_SIMILARITY
                )
                context_docs.extend(docs)
        
        if context_docs:
            logger.info(f"📊 Using {len(context_docs)} Pinecone results for snapshots extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:20]
            ])
        else:
            # No Pinecone results - check fallback strategy
            if FALLBACK_STRATEGY == 'pinecone_only':
                logger.error("❌ No Pinecone results for snapshots - ABORTING (pinecone_only strategy)")
                raise ValueError("No Pinecone context available for snapshots")
            else:
                logger.warning(f"⚠️  No Pinecone results for snapshots - Falling back to raw text ({FALLBACK_STRATEGY})")
                context_text = json.dumps(pages_text, indent=2)[:3000]
    
    prompt = f"""Extract business snapshot information for company ID "{company_id}" from web content:

{context_text}

Extract current/recent:
- Headcount total and growth percentage
- Job openings count by department (engineering, sales, etc.)
- Hiring focus areas
- Pricing tiers and pricing model
- Active products
- Geographic presence (countries/regions)

Return a list of Snapshot objects with as_of date set to today.
Use only explicitly stated information. Use null for missing fields."""
    
    try:
        class SnapshotList(BaseModel):
            snapshots: List[Snapshot] = Field(default_factory=list)
        
        result = client.chat.completions.create(
            model="gpt-4o",
            response_model=SnapshotList,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )
        
        logger.info(f"✓ Extracted {len(result.snapshots)} snapshots")
        return result.snapshots
    except Exception as e:
        logger.warning(f"Error extracting snapshots: {e}")
        return []


def extract_products(
    client, 
    company_id: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> List[Product]:
    """Extract product information using Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting products for {company_id}...")
    
    # Search queries for product data - using content from pages
    search_queries = [
        f"{company_id} product features description",
        f"{company_id} pricing cost plans",
        f"{company_id} integration API platform",
        f"{company_id} use cases applications capabilities",
        f"{company_id} technology innovation",
        f"artificial intelligence computer vision pixel",
    ]
    
    # Fallback queries if primary queries return no results
    fallback_queries = [
        "product",
        "features",
        "pricing",
        "integration",
        "capability",
        "pixel",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    global FALLBACK_STRATEGY
    global PINECONE_SEARCH_LIMIT
    global PINECONE_MIN_SIMILARITY
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for products")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search with primary queries
        logger.debug(f"Trying primary search queries for products...")
        for query in search_queries:
            docs = search_pinecone_for_context(
                query, company_id, pinecone_index, embeddings,
                limit=PINECONE_SEARCH_LIMIT,
                min_similarity=PINECONE_MIN_SIMILARITY
            )
            context_docs.extend(docs)
        
        # If no results, try fallback queries
        if not context_docs:
            logger.info(f"No results with primary queries, trying fallback queries...")
            for query in fallback_queries:
                docs = search_pinecone_for_context(
                    query, company_id, pinecone_index, embeddings,
                    limit=PINECONE_SEARCH_LIMIT,
                    min_similarity=PINECONE_MIN_SIMILARITY
                )
                context_docs.extend(docs)
        
        if context_docs:
            logger.info(f"📊 Using {len(context_docs)} Pinecone results for products extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:20]
            ])
        else:
            # No Pinecone results - check fallback strategy
            if FALLBACK_STRATEGY == 'pinecone_only':
                logger.error("❌ No Pinecone results for products - ABORTING (pinecone_only strategy)")
                raise ValueError("No Pinecone context available for products")
            else:
                logger.warning(f"⚠️  No Pinecone results for products - Falling back to raw text ({FALLBACK_STRATEGY})")
                context_text = json.dumps(pages_text, indent=2)[:3000]
    
    prompt = f"""Extract product information for company ID "{company_id}" from web content:

{context_text}

For each product, extract:
- Product name and description
- Pricing model (seat, usage, tiered, etc.)
- Public pricing tiers and cost
- Integration partners and APIs
- GitHub repositories and open source projects
- Reference customers and case studies
- License type

Return a list of Product objects. Use only explicitly stated information."""
    
    try:
        class ProductList(BaseModel):
            products: List[Product] = Field(default_factory=list)
        
        result = client.chat.completions.create(
            model="gpt-4o",
            response_model=ProductList,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )
        
        logger.info(f"✓ Extracted {len(result.products)} products")
        return result.products
    except Exception as e:
        logger.warning(f"Error extracting products: {e}")
        return []


def extract_leadership(
    client, 
    company_id: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> List[Leadership]:
    """Extract leadership and team information using Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting leadership for {company_id}...")
    
    # Search queries for leadership data - using content from pages
    search_queries = [
        f"{company_id} founder CEO co-founder",
        f"{company_id} team leadership executive",
        f"{company_id} management leadership roles",
        f"{company_id} LinkedIn profile education background",
        f"{company_id} advisors investors board members",
        f"founding team members leaders executives",
    ]
    
    # Fallback queries if primary queries return no results
    fallback_queries = [
        "founder",
        "CEO",
        "executive",
        "team",
        "LinkedIn",
        "leader",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    global FALLBACK_STRATEGY
    global PINECONE_SEARCH_LIMIT
    global PINECONE_MIN_SIMILARITY
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for leadership")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search with primary queries
        logger.debug(f"Trying primary search queries for leadership...")
        for query in search_queries:
            docs = search_pinecone_for_context(
                query, company_id, pinecone_index, embeddings,
                limit=PINECONE_SEARCH_LIMIT,
                min_similarity=PINECONE_MIN_SIMILARITY
            )
            context_docs.extend(docs)
        
        # If no results, try fallback queries
        if not context_docs:
            logger.info(f"No results with primary queries, trying fallback queries...")
            for query in fallback_queries:
                docs = search_pinecone_for_context(
                    query, company_id, pinecone_index, embeddings,
                    limit=PINECONE_SEARCH_LIMIT,
                    min_similarity=PINECONE_MIN_SIMILARITY
                )
                context_docs.extend(docs)
        
        if context_docs:
            logger.info(f"� Using {len(context_docs)} Pinecone results for leadership extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:20]
            ])
        else:
            # No Pinecone results - check fallback strategy
            if FALLBACK_STRATEGY == 'pinecone_only':
                logger.error("❌ No Pinecone results for leadership - ABORTING (pinecone_only strategy)")
                raise ValueError("No Pinecone context available for leadership")
            else:
                logger.warning(f"⚠️  No Pinecone results for leadership - Falling back to raw text ({FALLBACK_STRATEGY})")
                context_text = json.dumps(pages_text, indent=2)[:3000]
    
    prompt = f"""Extract leadership and key team members for company ID "{company_id}" from web content:

{context_text}

For each person, extract:
- Full name
- Current role (CEO, CTO, CPO, Founder, Executive, etc.)
- Whether they are a founder
- Start date at company
- Education background and university
- LinkedIn profile URL
- Previous companies/roles and employment history

Generate person_id from full name (e.g., john-doe from John Doe).
Return a list of Leadership objects. Use only explicitly stated information."""
    
    try:
        class LeadershipList(BaseModel):
            leadership: List[Leadership] = Field(default_factory=list)
        
        result = client.chat.completions.create(
            model="gpt-4o",
            response_model=LeadershipList,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )
        
        logger.info(f"✓ Extracted {len(result.leadership)} leadership members")
        return result.leadership
    except Exception as e:
        logger.warning(f"Error extracting leadership: {e}")
        return []


def extract_visibility(
    client, 
    company_id: str, 
    pages_text: Dict[str, str],
    pinecone_index = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    namespace: Optional[str] = None
) -> Optional[Visibility]:
    """Extract visibility and public metrics using Pinecone search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting visibility for {company_id}...")
    
    # Search queries for visibility data - using content from pages
    search_queries = [
        f"{company_id} news mentions press coverage",
        f"{company_id} GitHub repository stars",
        f"{company_id} awards recognition industry",
        f"{company_id} media coverage publicity",
        f"{company_id} social media followers engagement",
        f"industry recognition metrics impact",
    ]
    
    # Fallback queries if primary queries return no results
    fallback_queries = [
        "news",
        "award",
        "GitHub",
        "rating",
        "recognition",
        "mention",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global USE_RAW_TEXT
    global FALLBACK_STRATEGY
    global PINECONE_SEARCH_LIMIT
    global PINECONE_MIN_SIMILARITY
    
    if USE_RAW_TEXT:
        logger.info(f"⚙️  Using raw text mode for visibility")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Pinecone search with primary queries
        logger.debug(f"Trying primary search queries for visibility...")
        for query in search_queries:
            docs = search_pinecone_for_context(
                query, company_id, pinecone_index, embeddings,
                limit=PINECONE_SEARCH_LIMIT,
                min_similarity=PINECONE_MIN_SIMILARITY
            )
            context_docs.extend(docs)
        
        # If no results, try fallback queries
        if not context_docs:
            logger.info(f"No results with primary queries, trying fallback queries...")
            for query in fallback_queries:
                docs = search_pinecone_for_context(
                    query, company_id, pinecone_index, embeddings,
                    limit=PINECONE_SEARCH_LIMIT,
                    min_similarity=PINECONE_MIN_SIMILARITY
                )
                context_docs.extend(docs)
        
        if context_docs:
            logger.info(f"📊 Using {len(context_docs)} Pinecone results for visibility extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:20]
            ])
        else:
            # No Pinecone results - check fallback strategy
            if FALLBACK_STRATEGY == 'pinecone_only':
                logger.error("❌ No Pinecone results for visibility - ABORTING (pinecone_only strategy)")
                raise ValueError("No Pinecone context available for visibility")
            else:
                logger.warning(f"⚠️  No Pinecone results for visibility - Falling back to raw text ({FALLBACK_STRATEGY})")
                context_text = json.dumps(pages_text, indent=2)[:3000]
    
    prompt = f"""Extract visibility and public metrics for company ID "{company_id}" from web content:

{context_text}

Extract:
- News mentions or press coverage indicators (count and sentiment)
- Sentiment indicators (positive/negative/neutral)
- GitHub repository stars or popularity metrics
- Glassdoor rating if available
- Awards or industry recognition
- Social media followers if mentioned

Return a Visibility object with as_of set to today. Use only explicitly stated metrics."""
    
    try:
        visibility = client.chat.completions.create(
            model="gpt-4o",
            response_model=Visibility,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
        )
        
        logger.info(f"✓ Extracted visibility metrics")
        return visibility
    except Exception as e:
        logger.warning(f"Error extracting visibility: {e}")
        return None


def process_company(company_slug: str, verbose: bool = False):
    """Process a single company: extract structured data using Pinecone vector search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Company: {company_slug}")
    logger.info(f"{'='*60}")
    
    pinecone_index = None
    embeddings = None
    namespace = None
    
    try:
        # Load all page texts
        pages_text = load_all_company_pages(company_slug)
        if not pages_text:
            logger.warning(f"No page texts found for {company_slug}")
            return None
        
        # Initialize LLM client
        client = get_llm_client()
        
        # Initialize Pinecone and embeddings (for searching, not indexing)
        logger.info("Initializing Pinecone for semantic search...")
        try:
            pinecone_index = get_pinecone_client()
            embeddings = get_embeddings_model()
        except Exception as e:
            logger.warning(f"Could not initialize Pinecone: {e}")
            logger.warning("Will use raw text mode instead")
            global USE_RAW_TEXT
            USE_RAW_TEXT = True
        
        # Extract structured data
        logger.info("Starting structured extraction with semantic search...")
        
        # 1. Extract company info
        company = extract_company_info(
            client, 
            company_slug, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        if not company:
            logger.error(f"Failed to extract company info for {company_slug}")
            return None
        
        company_id = company.company_id
        logger.info(f"Company ID: {company_id}")
        
        # 2. Extract events
        events = extract_events(
            client, 
            company_id, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        
        # 3. Extract snapshots
        snapshots = extract_snapshots(
            client, 
            company_id, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        
        # 4. Extract products
        products = extract_products(
            client, 
            company_id, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        
        # 5. Extract leadership
        leadership = extract_leadership(
            client, 
            company_id, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        
        # 6. Extract visibility
        visibility_list = []
        visibility = extract_visibility(
            client, 
            company_id, 
            pages_text,
            pinecone_index,
            embeddings,
            namespace
        )
        if visibility:
            visibility_list = [visibility]
        
        # Create payload
        payload = Payload(
            company_record=company,
            events=events,
            snapshots=snapshots,
            products=products,
            leadership=leadership,
            visibility=visibility_list,
            notes=f"Extracted with semantic search via Pinecone on {datetime.now().isoformat()}"
        )
        
        # Save results to data/payloads/
        payloads_dir = Path("data/payloads") 
        payloads_dir.mkdir(parents=True, exist_ok=True)
        
        payload_file = payloads_dir / f"{company_id}.json"
        with open(payload_file, 'w', encoding='utf-8') as f:
            json.dump(payload.model_dump(mode='json'), f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"\n✓ Saved extraction results to: {payload_file}")
        
        logger.info(f"  Company: {company.legal_name}")
        logger.info(f"  Events: {len(events)}")
        logger.info(f"  Snapshots: {len(snapshots)}")
        logger.info(f"  Products: {len(products)}")
        logger.info(f"  Leadership: {len(leadership)}")
        logger.info(f"  Visibility: {len(visibility_list)}")
        
        return payload
        
    except Exception as e:
        logger.error(f"Error processing company {company_slug}: {e}", exc_info=True)
        return None


def discover_companies_from_raw_data() -> List[str]:
    """Discover companies from raw data directory structure."""
    logger = logging.getLogger('structured_extraction')
    
    raw_dir = Path("data/raw")
    companies = []
    
    if not raw_dir.exists():
        logger.warning(f"Raw data directory not found: {raw_dir}")
        return companies
    
    for company_dir in raw_dir.iterdir():
        if company_dir.is_dir():
            company_slug = company_dir.name
            companies.append(company_slug)
    
    logger.info(f"Discovered {len(companies)} companies from raw data")
    return companies


def main():
    logger = setup_logging('structured_extraction')
    logger.info("=== Starting Structured Extraction (RAG with Pinecone) ===")
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Extract structured data from web scrapes using semantic search")
    parser.add_argument('--company-slug', type=str, help='Specific company slug to process')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--all', action='store_true', help='Process all companies')
    parser.add_argument(
        '--fallback-strategy',
        type=str,
        choices=['pinecone_only', 'raw_only', 'pinecone_first'],
        default='pinecone_only',
        help='Strategy for handling Pinecone failures: pinecone_only (fail if no Pinecone), raw_only (always use raw text), pinecone_first (prefer Pinecone, fallback to raw)'
    )
    
    args = parser.parse_args()
    
    # Store fallback strategy globally for use in extraction functions
    global FALLBACK_STRATEGY
    FALLBACK_STRATEGY = args.fallback_strategy
    logger.info(f"Fallback strategy: {args.fallback_strategy}")
    
    try:
        if args.company_slug:
            # Process specific company
            logger.info(f"Processing specific company: {args.company_slug}")
            result = process_company(args.company_slug, args.verbose)
            if result:
                logger.info(f"✓ Successfully processed {args.company_slug}")
            else:
                logger.error(f"✗ Failed to process {args.company_slug}")
                sys.exit(1)
        elif args.all:
            # Process all companies
            companies = discover_companies_from_raw_data()
            
            if not companies:
                logger.warning("No companies found in data/raw directory")
                return
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {len(companies)} companies")
            logger.info(f"{'='*60}\n")
            
            results = []
            for idx, company_slug in enumerate(companies, 1):
                logger.info(f"[{idx}/{len(companies)}] {company_slug}")
                result = process_company(company_slug, args.verbose)
                if result:
                    results.append({
                        'company_slug': company_slug,
                        'success': True,
                        'company_id': result.company_record.company_id
                    })
                else:
                    results.append({
                        'company_slug': company_slug,
                        'success': False
                    })
            
            # Summary
            logger.info(f"\n{'='*60}")
            logger.info("=== EXTRACTION COMPLETE ===")
            logger.info(f"{'='*60}")
            
            successful = sum(1 for r in results if r['success'])
            logger.info(f"Successfully processed: {successful}/{len(results)}")
            
            if successful > 0:
                logger.info("\nSuccessful companies:")
                for r in results:
                    if r['success']:
                        logger.info(f"  ✓ {r['company_slug']} → {r['company_id']}")
            
            failed = [r for r in results if not r['success']]
            if failed:
                logger.info("\nFailed companies:")
                for r in failed:
                    logger.info(f"  ✗ {r['company_slug']}")
        else:
            parser.print_help()
            logger.error("Please specify --company-slug <slug>, --all, or use --help")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
