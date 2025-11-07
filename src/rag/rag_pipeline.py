"""
RAG extraction for dashboard generation.

Retrieves context from Qdrant and uses LLM to generate investor-facing dashboard.
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

logger = logging.getLogger(__name__)


def get_dashboard_system_prompt() -> str:
    """Load the dashboard system prompt from the markdown file."""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "dashboard_system.md"
    
    if not prompt_path.exists():
        logger.warning(f"Dashboard system prompt not found at {prompt_path}")
        return ""
    
    try:
        return prompt_path.read_text()
    except Exception as e:
        logger.error(f"Failed to load dashboard prompt: {e}")
        return ""


def format_context_for_llm(search_results: List[Dict[str, Any]]) -> str:
    """Format search results into context for the LLM."""
    if not search_results:
        return "No context available."
    
    context_parts = []
    for i, result in enumerate(search_results, 1):
        text = result.get("text", "")
        metadata = result.get("metadata", {})
        score = result.get("similarity_score", 0)
        
        context_parts.append(f"### Source {i} (Score: {score:.3f})")
        context_parts.append(text)
        
        if metadata:
            if "source" in metadata:
                context_parts.append(f"**Source:** {metadata['source']}")
            if "page" in metadata:
                context_parts.append(f"**Page:** {metadata['page']}")
        
        context_parts.append("")
    
    return "\n".join(context_parts)


def generate_dashboard_markdown(
    company_name: str,
    search_results: List[Dict[str, Any]],
    llm_client: Any = None,
    llm_model: str = "gpt-4o",
    temperature: float = 0.1
) -> str:
    """
    Generate investor-facing dashboard markdown using RAG context and LLM.
    
    Args:
        company_name: Name of the company
        search_results: List of search results from Qdrant
        llm_client: OpenAI client (auto-initialized if None)
        llm_model: LLM model to use
        temperature: Temperature for LLM generation (0.0-2.0, default 0.1 for deterministic output)
    
    Returns:
        Markdown string with dashboard content
    """
    import os
    
    # Initialize LLM client if not provided
    if llm_client is None:
        try:
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set")
                return _generate_default_dashboard(company_name, search_results)
            llm_client = OpenAI(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return _generate_default_dashboard(company_name, search_results)
    
    # Load system prompt
    system_prompt = get_dashboard_system_prompt()
    if not system_prompt:
        logger.warning("Dashboard system prompt is empty, using default template")
        return _generate_default_dashboard(company_name, search_results)
    
    # Format context
    context = format_context_for_llm(search_results)
    
    # Build user message
    user_message = f"""
Generate an investor-facing diligence dashboard for {company_name}.

Use ONLY the provided context below. If information is not in the context, use "Not disclosed."

Context from company data:
{context}

Generate the dashboard with the following sections in order:
1. Company Overview
2. Business Model and GTM
3. Funding & Investor Profile
4. Growth Momentum
5. Visibility & Market Sentiment
6. Risks and Challenges
7. Outlook
8. Disclosure Gaps

Use markdown formatting with ## for section headers.
"""
    
    try:
        logger.info(f"Calling LLM to generate dashboard for {company_name} (temperature={temperature})")
        
        response = llm_client.chat.completions.create(
            model=llm_model,
            max_tokens=4096,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        
        dashboard_markdown = response.choices[0].message.content
        logger.info(f"Successfully generated dashboard for {company_name}")
        
        return dashboard_markdown
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        return _generate_default_dashboard(company_name, search_results)


def _generate_default_dashboard(
    company_name: str,
    search_results: List[Dict[str, Any]]
) -> str:
    """Generate a fallback dashboard when LLM is unavailable."""
    logger.info(f"Generating default dashboard for {company_name}")
    
    context = format_context_for_llm(search_results)
    
    dashboard = f"""# {company_name} - Investor Diligence Dashboard

## Company Overview
Not disclosed.

## Business Model and GTM
Not disclosed.

## Funding & Investor Profile
Not disclosed.

## Growth Momentum
Not disclosed.

## Visibility & Market Sentiment
Not disclosed.

## Risks and Challenges
Not disclosed.

## Outlook
Not disclosed.

## Disclosure Gaps
**Available Context:**
{context}

**Note:** This is a fallback dashboard generated without LLM processing. 
For full dashboard generation, ensure OPENAI_API_KEY is set and the LLM is available.
"""
    
    return dashboard


def generate_dashboard_with_retrieval(
    company_name: str,
    company_slug: str,
    pinecone_index: Any,
    llm_client: Any = None,
    llm_model: str = "gpt-4o",
    top_k: int = 10,
    temperature: float = 0.1
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Complete pipeline: retrieve context from Pinecone and generate dashboard.
    
    Args:
        company_name: Display name of the company
        company_slug: Slug format for collection name (e.g., "world-labs")
        pinecone_index: Pinecone index instance (from pc.Index(index_name))
        llm_client: OpenAI client (optional)
        llm_model: LLM model to use
        top_k: Number of top results to retrieve
        temperature: LLM temperature (0.0-2.0, default 0.1 for deterministic output)
    
    Returns:
        Tuple of (dashboard_markdown, search_results_list)
    """
    import os
    
    logger.info(f"Generating dashboard with retrieval for {company_name}")
    
    # Build namespace - use underscores, not hyphens
    # Convert company_slug to use underscores for Pinecone namespace
    namespace = company_slug.replace("-", "_")
    
    # Create search query
    search_query = (
        f"company overview, business model, products, funding, investors, "
        f"revenue, growth, leadership, market presence, partnerships"
    )
    
    try:
        # Retrieve context from Pinecone using OpenAI embeddings
        logger.debug(f"Searching Pinecone namespace '{namespace}' for context")
        
        # Initialize OpenAI client for embeddings
        try:
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set for embeddings")
                return f"# Error Generating Dashboard for {company_name}\n\nOpenAI API key not configured.", []
            
            embed_client = OpenAI(api_key=api_key)
            
            # Get embedding for search query (use text-embedding-3-large for consistency)
            logger.debug("Creating query embedding with OpenAI (text-embedding-3-large)")
            embedding_response = embed_client.embeddings.create(
                model="text-embedding-3-large",
                input=search_query
            )
            query_embedding = embedding_response.data[0].embedding
            
        except Exception as e:
            logger.error(f"Failed to create OpenAI embedding: {e}")
            return f"# Error Generating Dashboard for {company_name}\n\nFailed to generate embeddings: {str(e)}", []
        
        # Search Pinecone with the embedding
        namespace_val = os.environ.get("PINECONE_NAMESPACE", "default")
        logger.debug(f"Querying Pinecone with namespace: {namespace_val}")
        
        search_result = pinecone_index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace=namespace_val,
            include_metadata=True
        )
        
        logger.info(f"DEBUG: Pinecone search returned {len(search_result.get('matches', []))} matches")
        
        # Convert results to expected format
        search_results = []
        for match in search_result.get("matches", []):
            metadata = match.get("metadata", {})
            logger.debug(f"DEBUG: Match {match['id']} - score: {match['score']}, has text: {'text' in metadata}")
            search_results.append({
                "text": metadata.get("text", ""),
                "similarity_score": match.get("score", 0),
                "metadata": {k: v for k, v in metadata.items() if k != "text"}
            })
        
        logger.info(f"Retrieved {len(search_results)} results from Pinecone")
        
        # Generate dashboard
        dashboard = generate_dashboard_markdown(
            company_name=company_name,
            search_results=search_results,
            llm_client=llm_client,
            llm_model=llm_model,
            temperature=temperature
        )
        
        return dashboard, search_results
        
    except Exception as e:
        logger.error(f"Dashboard generation with retrieval failed: {e}", exc_info=True)
        return f"# Error Generating Dashboard for {company_name}\n\nFailed to retrieve context: {str(e)}", []
