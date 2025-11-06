#!/usr/bin/env python3
"""RAG-based Structured Extraction: Extract and normalize company data from web scrapes using LLM.

This script:
1. Reads text extracted from company web pages (data/raw/{company_slug}/{page_type}/text.txt)
2. Queries Qdrant vector database to retrieve relevant context
3. Uses instructor + OpenAI to extract structured data into Pydantic models
4. Normalizes messy text data into clean, structured format
5. Saves results as data/structured/{company_id}.json

The extraction follows the schema defined in rag_models.py:
- Company (legal_name, website, headquarters, founding date, funding, etc.)
- Event (funding rounds, M&A, product releases, etc.)
- Snapshot (headcount, job openings, pricing, etc.)
- Product (description, pricing model, integrations, etc.)
- Leadership (founders, executives, roles, etc.)
- Visibility (news mentions, GitHub stars, ratings, etc.)

Usage:
  python scripts/rag/structured_extraction.py
  python scripts/rag/structured_extraction.py --company-slug world_labs --verbose
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
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from langchain_text_splitters import RecursiveCharacterTextSplitter
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
FALLBACK_STRATEGY = 'qdrant_first'  # Can be: 'qdrant_only', 'raw_only', 'qdrant_first'

def setup_logging():
    """Setup logging for structured_extraction script."""
    log_dir = "data/logs"
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger('structured_extraction')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    file_handler = logging.FileHandler(f"{log_dir}/structured_extraction.log")
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


def get_qdrant_client():
    """Initialize Qdrant client for vector search."""
    logger = logging.getLogger('structured_extraction')
    
    # Try to connect to Qdrant (local or remote)
    qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333')
    qdrant_api_key = os.getenv('QDRANT_API_KEY', None)
    
    try:
        if qdrant_api_key:
            client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        else:
            client = QdrantClient(url=qdrant_url)
        logger.info(f"Connected to Qdrant at {qdrant_url}")
        return client
    except Exception as e:
        logger.warning(f"Failed to connect to Qdrant: {e}")
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
            model="text-embedding-3-small",
            api_key=api_key
        )
        logger.debug("Initialized OpenAI embeddings model")
        return embeddings
    except Exception as e:
        logger.error(f"Failed to initialize embeddings: {e}")
        raise


def index_company_pages_to_qdrant(
    company_slug: str, 
    pages_text: Dict[str, str],
    qdrant_client: Optional[QdrantClient],
    embeddings: Optional[OpenAIEmbeddings]
) -> Optional[str]:
    """Index company pages to Qdrant vector database and return collection name."""
    logger = logging.getLogger('structured_extraction')
    
    if not qdrant_client or not embeddings:
        logger.debug("Qdrant client or embeddings not available, skipping indexing")
        return None
    
    try:
        # Create collection name from company slug
        collection_name = f"company_{company_slug}".lower().replace('-', '_')
        
        # Check if collection already exists
        try:
            qdrant_client.get_collection(collection_name)
            logger.debug(f"Collection {collection_name} already exists")
        except Exception:
            # Collection doesn't exist, create it
            logger.info(f"Creating Qdrant collection: {collection_name}")
            
            # Get embedding dimension
            sample_embedding = embeddings.embed_query("test")
            embedding_dim = len(sample_embedding)
            
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
            )
            logger.debug(f"Created collection with {embedding_dim}-dim vectors")
        
        # Split and embed text from all pages
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
        )
        
        points = []
        point_id = 1
        chunks_per_source = {}  # Track chunks per source file
        
        logger.info(f"\nIndexing source files for {company_slug}:")
        logger.info(f"{'─' * 60}")
        
        for page_type, text in pages_text.items():
            if not text:
                continue
            
            # Log source file information
            source_file = f"data/raw/{company_slug}/{page_type}/text.txt"
            logger.info(f"  📄 Source: {source_file}")
            logger.info(f"     Content size: {len(text)} characters")
            
            # Split text into chunks
            chunks = text_splitter.split_text(text)
            chunks_per_source[page_type] = len(chunks)
            logger.info(f"     Chunks created: {len(chunks)} (500 chars, 100 char overlap)")
            
            for chunk_idx, chunk in enumerate(chunks, 1):
                try:
                    # Generate embedding
                    embedding = embeddings.embed_query(chunk)
                    
                    # Create point
                    point = PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "text": chunk,
                            "page_type": page_type,
                            "company_slug": company_slug,
                            "source_file": source_file,
                            "chunk_index": chunk_idx,
                        }
                    )
                    points.append(point)
                    point_id += 1
                except Exception as e:
                    logger.warning(f"Failed to embed chunk {chunk_idx} from {page_type}: {e}")
                    continue
            
            logger.info(f"     ✓ Processed {page_type}\n")
        
        if points:
            # Upsert points to Qdrant
            qdrant_client.upsert(
                collection_name=collection_name,
                points=points,
            )
            
            # Summary logging
            logger.info(f"{'─' * 60}")
            logger.info(f"✓ Indexed {len(points)} total chunks to Qdrant")
            logger.info(f"\nBreakdown by source:")
            for source, count in sorted(chunks_per_source.items()):
                logger.info(f"  • {source:15} → {count:3} chunks")
            logger.info(f"{'─' * 60}\n")
        
        return collection_name
        
    except Exception as e:
        logger.warning(f"Error indexing to Qdrant: {e}")
        return None


def search_qdrant_for_context(
    query: str,
    collection_name: str,
    qdrant_client: Optional[QdrantClient],
    embeddings: Optional[OpenAIEmbeddings],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Search Qdrant for relevant context using semantic search."""
    logger = logging.getLogger('structured_extraction')
    
    if not qdrant_client or not embeddings or not collection_name:
        logger.debug("Cannot search Qdrant - client/embeddings/collection missing")
        return []
    
    try:
        # Generate embedding for query
        query_embedding = embeddings.embed_query(query)
        
        # Search Qdrant
        logger.debug(f"🔍 Semantic search in Qdrant: '{query}'")
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=limit,
        )
        
        # Extract context from results with full source tracking
        context_docs = []
        for idx, result in enumerate(results, 1):
            doc = {
                "text": result.payload.get("text", ""),
                "page_type": result.payload.get("page_type", ""),
                "score": result.score,
                "source_file": result.payload.get("source_file", ""),
                "chunk_index": result.payload.get("chunk_index", ""),
                "point_id": result.id,
            }
            context_docs.append(doc)
            logger.debug(f"  🎯 Rank {idx}: {doc['source_file']} (chunk {doc['chunk_index']}, similarity: {result.score:.3f})")
        
        logger.debug(f"✅ Qdrant search returned {len(context_docs)} documents")
        return context_docs
        
    except Exception as e:
        logger.warning(f"❌ Error searching Qdrant: {e}")
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
        logger.warning(f"  ⚠️  No Qdrant sources found for {extraction_type}")
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
            logger.info(f"      • Point ID {doc['point_id']}: chunk {doc['chunk_index']} (similarity: {doc['score']:.3f})")
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
    if FALLBACK_STRATEGY == 'qdrant_only':
        logger.error(f"❌ Strategy 'qdrant_only': No Qdrant results for {extraction_type}, FAILING")
        return False
    elif FALLBACK_STRATEGY == 'raw_only':
        logger.warning(f"⚠️  Strategy 'raw_only': Ignoring Qdrant, using raw text for {extraction_type}")
        return True
    elif FALLBACK_STRATEGY == 'qdrant_first':
        logger.warning(f"⚠️  Strategy 'qdrant_first': Fallback to raw text for {extraction_type}")
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


def create_extraction_prompt(company_name: str, pages_text: Dict[str, str]) -> str:
    """Create a comprehensive prompt for LLM-based extraction."""
    
    # Combine all page texts
    combined_text = ""
    for page_type, text in pages_text.items():
        combined_text += f"\n\n## {page_type.upper()} PAGE:\n{text[:2000]}\n"
    
    prompt = f"""You are an expert data analyst extracting structured information about the company "{company_name}" from web pages.

EXTRACTED WEB CONTENT:
{combined_text}

Extract and normalize the following information from the web content:

1. **Company Information**: Legal name, brand name, website, headquarters location, founding year, categories
2. **Financial Information**: Total funding raised, last valuation, last funding round details
3. **Events**: Any funding rounds, M&A activities, product launches, partnerships, major hires, layoffs mentioned
4. **Products**: Product names, descriptions, pricing models, integrations, GitHub repos
5. **Leadership**: Founders and executives mentioned - name, role, start dates, backgrounds
6. **Visibility**: News mentions, GitHub stars, ratings (if available)

Guidelines:
- Use ONLY information explicitly mentioned in the web content
- For missing fields, leave them as null/empty - DO NOT infer or guess
- Standardize date formats to YYYY-MM-DD
- Extract company_id from website domain (e.g., world-labs from worldlabs.ai)
- Extract all person IDs from names (e.g., john-doe from John Doe)
- Include source URLs in provenance fields
- Be conservative with data - if uncertain, leave blank

Return structured data matching the Pydantic schemas."""
    
    return prompt


def extract_company_info(
    client, 
    company_name: str, 
    pages_text: Dict[str, str],
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> Optional[Company]:
    """Extract company information using LLM with instructor and Qdrant search."""
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
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for company info")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=3)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for company extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:300]}"
                for doc in context_docs[:10]  # Limit to top 10 results
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for company info - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results, using raw text instead")
            context_text = json.dumps(pages_text, indent=2)[:3000]
    
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
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> List[Event]:
    """Extract events (funding, M&A, partnerships, etc.) using LLM and Qdrant search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting events for {company_id}...")
    
    # Build search queries for events
    search_queries = [
        f"funding rounds Series A B C seed investment capital raised",
        f"M&A acquisition merger merger company",
        f"product launch release announcement",
        f"partnership partnership collaboration integration",
        f"hiring jobs positions team expansion layoffs",
        f"milestones achievements awards recognition",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for events")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=2)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for events extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:15]  # Limit to top 15 results
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for events - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results for events, using raw text instead")
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
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> List[Snapshot]:
    """Extract business snapshots (headcount, products, pricing, etc.) using Qdrant search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting snapshots for {company_id}...")
    
    # Search queries for snapshot data
    search_queries = [
        f"headcount employees team size headcount growth hiring",
        f"pricing tiers pricing model pricing plans subscription",
        f"products features product offerings services",
        f"geographic presence countries regions locations",
        f"job openings hiring positions vacancies",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for snapshots")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=3)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for snapshots extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:15]
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for snapshots - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results for snapshots, using raw text instead")
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
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> List[Product]:
    """Extract product information using Qdrant search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting products for {company_id}...")
    
    # Search queries for product data
    search_queries = [
        f"product name product description features",
        f"pricing model pricing tiers pricing plans cost",
        f"integrations partners integrations APIs",
        f"GitHub repository source code open source",
        f"customers clients reference accounts",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for products")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=3)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for products extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:12]
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for products - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results for products, using raw text instead")
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
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> List[Leadership]:
    """Extract leadership and team information using Qdrant search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting leadership for {company_id}...")
    
    # Search queries for leadership data
    search_queries = [
        f"founder co-founder CEO CTO CPO founder",
        f"executive team leadership management",
        f"CEO founder name role",
        f"LinkedIn profile background education",
        f"previous company employment history",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for leadership")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=3)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for leadership extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:15]
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for leadership - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results for leadership, using raw text instead")
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
    qdrant_client: Optional[QdrantClient] = None,
    embeddings: Optional[OpenAIEmbeddings] = None,
    collection_name: Optional[str] = None
) -> Optional[Visibility]:
    """Extract visibility and public metrics using Qdrant search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"Extracting visibility for {company_id}...")
    
    # Search queries for visibility data
    search_queries = [
        f"news mentions press coverage media articles",
        f"GitHub stars repository rating metrics",
        f"Glassdoor rating employee reviews",
        f"awards recognition industry recognition",
        f"social media followers engagement",
    ]
    
    # Determine search strategy
    context_docs = []
    context_text = ""
    
    global FALLBACK_STRATEGY
    
    if FALLBACK_STRATEGY == 'raw_only':
        logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for visibility")
        context_text = json.dumps(pages_text, indent=2)[:3000]
    else:
        # Try Qdrant search
        for query in search_queries:
            docs = search_qdrant_for_context(query, collection_name, qdrant_client, embeddings, limit=2)
            context_docs.extend(docs)
        
        if context_docs:
            logger.info("📊 Using Qdrant context for visibility extraction")
            context_text = "\n\n".join([
                f"[{doc['page_type']}] {doc['text'][:250]}"
                for doc in context_docs[:10]
            ])
        elif FALLBACK_STRATEGY == 'qdrant_only':
            logger.error("❌ Strategy 'qdrant_only': No Qdrant results for visibility - ABORTING")
            raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
        else:  # qdrant_first
            logger.warning("⚠️  Fallback: Qdrant returned no results for visibility, using raw text instead")
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


def process_company(company_slug: str, company_name: str, verbose: bool = False):
    """Process a single company: extract structured data using Qdrant vector search."""
    logger = logging.getLogger('structured_extraction')
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Company: {company_name} ({company_slug})")
    logger.info(f"{'='*60}")
    
    qdrant_client = None
    embeddings = None
    collection_name = None
    
    try:
        # Load all page texts
        pages_text = load_all_company_pages(company_slug)
        if not pages_text:
            logger.warning(f"No page texts found for {company_slug}")
            return None
        
        # Initialize LLM client
        client = get_llm_client()
        
        # Initialize Qdrant and embeddings
        logger.info("Initializing Qdrant vector database...")
        qdrant_client = get_qdrant_client()
        embeddings = get_embeddings_model()
        
        # Index company pages to Qdrant
        if qdrant_client and embeddings:
            collection_name = index_company_pages_to_qdrant(
                company_slug, 
                pages_text,
                qdrant_client,
                embeddings
            )
            if collection_name:
                logger.info(f"✓ Indexed to Qdrant collection: {collection_name}")
        
        # Extract structured data
        logger.info("Starting structured extraction with semantic search...")
        
        # 1. Extract company info
        company = extract_company_info(
            client, 
            company_name, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
        )
        if not company:
            logger.error(f"Failed to extract company info for {company_name}")
            return None
        
        company_id = company.company_id
        logger.info(f"Company ID: {company_id}")
        
        # 2. Extract events
        events = extract_events(
            client, 
            company_id, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
        )
        
        # 3. Extract snapshots
        snapshots = extract_snapshots(
            client, 
            company_id, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
        )
        
        # 4. Extract products
        products = extract_products(
            client, 
            company_id, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
        )
        
        # 5. Extract leadership
        leadership = extract_leadership(
            client, 
            company_id, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
        )
        
        # 6. Extract visibility
        visibility_list = []
        visibility = extract_visibility(
            client, 
            company_id, 
            pages_text,
            qdrant_client,
            embeddings,
            collection_name
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
            notes=f"Extracted with semantic search via Qdrant on {datetime.now().isoformat()}"
        )
        
        # Save results to data/structured/
        structured_dir = Path("data/structured")
        structured_dir.mkdir(parents=True, exist_ok=True)
        
        structured_file = structured_dir / f"{company_id}.json"
        with open(structured_file, 'w', encoding='utf-8') as f:
            json.dump(payload.model_dump(mode='json'), f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"\n✓ Saved structured data to: {structured_file}")
        
        # Also save to data/payloads/ for payload access
        payloads_dir = Path("data/payloads")
        payloads_dir.mkdir(parents=True, exist_ok=True)
        
        payload_file = payloads_dir / f"{company_id}.json"
        with open(payload_file, 'w', encoding='utf-8') as f:
            json.dump(payload.model_dump(mode='json'), f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✓ Saved payload data to: {payload_file}")
        
        logger.info(f"  Company: {company.legal_name}")
        logger.info(f"  Events: {len(events)}")
        logger.info(f"  Snapshots: {len(snapshots)}")
        logger.info(f"  Products: {len(products)}")
        logger.info(f"  Leadership: {len(leadership)}")
        logger.info(f"  Visibility: {len(visibility_list)}")
        
        return payload
        
    except Exception as e:
        logger.error(f"Error processing company {company_name}: {e}", exc_info=True)
        return None


def discover_companies_from_raw_data() -> List[tuple]:
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
            # Convert slug back to title case as company name
            company_name = company_slug.replace('_', ' ').title()
            companies.append((company_slug, company_name))
    
    logger.info(f"Discovered {len(companies)} companies from raw data")
    return companies


def main():
    logger = setup_logging()
    logger.info("=== Starting Structured Extraction (RAG) ===")
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Extract structured data from web scrapes")
    parser.add_argument('--company-slug', type=str, help='Process specific company by slug')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument(
        '--fallback-strategy',
        type=str,
        choices=['qdrant_only', 'raw_only', 'qdrant_first'],
        default='qdrant_first',
        help='Strategy for handling Qdrant failures: qdrant_only (fail if no Qdrant), raw_only (always use raw text), qdrant_first (prefer Qdrant, fallback to raw)'
    )
    
    args = parser.parse_args()
    
    # Store fallback strategy globally for use in extraction functions
    global FALLBACK_STRATEGY
    FALLBACK_STRATEGY = args.fallback_strategy
    logger.info(f"Fallback strategy: {args.fallback_strategy}")
    
    try:
        # Discover companies to process
        if args.company_slug:
            companies = [(args.company_slug, args.company_slug.replace('_', ' ').title())]
            logger.info(f"Processing specific company: {args.company_slug}")
        else:
            companies = discover_companies_from_raw_data()
        
        if not companies:
            logger.warning("No companies to process")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {len(companies)} companies")
        logger.info(f"{'='*60}\n")
        
        results = []
        for idx, (company_slug, company_name) in enumerate(companies, 1):
            logger.info(f"[{idx}/{len(companies)}] {company_name}")
            result = process_company(company_slug, company_name, args.verbose)
            if result:
                results.append({
                    'company_slug': company_slug,
                    'company_name': company_name,
                    'success': True,
                    'company_id': result.company_record.company_id
                })
            else:
                results.append({
                    'company_slug': company_slug,
                    'company_name': company_name,
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
                    logger.info(f"  ✓ {r['company_name']} → {r['company_id']}")
        
        failed = [r for r in results if not r['success']]
        if failed:
            logger.info("\nFailed companies:")
            for r in failed:
                logger.info(f"  ✗ {r['company_name']}")
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
