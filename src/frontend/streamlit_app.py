import streamlit as st
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API URL from environment variable or use default
API_BASE = os.getenv("FASTAPI_URL", "http://localhost:8000")

st.set_page_config(page_title="PE Dashboard (AI 50)", layout="wide")
st.title("Project ORBIT – PE Dashboard for Forbes AI 50")

# Initialize session state for persisting outputs
if "structured_data" not in st.session_state:
    st.session_state.structured_data = None
if "rag_data" not in st.session_state:
    st.session_state.rag_data = None

try:
    response = requests.get(f"{API_BASE}/companies", timeout=5).json()
    # Extract companies from the response object
    companies = response.get("companies", []) if isinstance(response, dict) else response
except Exception as e:
    st.warning(f"⚠️ Failed to load companies: {e}")
    companies = []

names = [c["company_name"] for c in companies] if companies else ["ExampleAI"]
choice = st.selectbox("Select company", names)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Structured pipeline")
    if st.button("Generate (Structured)"):
        # Use company name directly
        try:
            # Call the new /dashboard/structured endpoint (POST)
            resp = requests.post(
                f"{API_BASE}/dashboard/structured",
                params={"company_name": choice},
                timeout=30  # Longer timeout for LLM generation
            )
            
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.structured_data = data  # Store in session state
                st.success(f"✅ Dashboard generated for {choice}")
            
            elif resp.status_code == 404:
                st.warning(f"⚠️ Structured payload not available for **{choice}**")
                st.info("The payload for this company hasn't been extracted yet. Please run the extraction pipeline first.")
            
            else:
                st.error(f"❌ Error: {resp.status_code}")
                try:
                    st.json(resp.json())
                except:
                    st.error(resp.text)
        
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timeout - LLM generation may be slow or API not responding")
        except Exception as e:
            st.error(f"❌ Error generating dashboard: {e}")
    
    # Display stored structured data if available
    if st.session_state.structured_data:
        data = st.session_state.structured_data
        
        # Create tabs for dashboard and payload
        struct_tab1, struct_tab2 = st.tabs(["Dashboard", "Structured Payload"])
        
        with struct_tab1:
            # Display the markdown dashboard
            if "markdown" in data and data["markdown"]:
                st.markdown(data["markdown"])
            else:
                st.warning("No dashboard content generated")
        
        with struct_tab2:
            # Load and display the structured JSON payload
            company_slug = data.get("company_slug", "")
            if company_slug:
                try:
                    import json
                    from pathlib import Path
                    
                    # Construct path to payload file
                    payload_path = Path("data/payloads") / f"{company_slug}.json"
                    
                    if payload_path.exists():
                        with open(payload_path, 'r') as f:
                            payload_json = json.load(f)
                        
                        # Display as markdown code block with JSON formatting
                        st.write("**Structured Payload (JSON):**")
                        st.json(payload_json)
                        
                        # Also provide a copy-friendly code block
                        st.write("**Raw JSON:**")
                        st.code(json.dumps(payload_json, indent=2), language="json")
                    else:
                        st.warning(f"❌ Payload file not found at: `{payload_path}`")
                
                except Exception as e:
                    st.error(f"❌ Failed to load payload: {e}")
            else:
                st.info("No company slug available to load payload")

with col2:
    st.subheader("RAG pipeline")
    if st.button("Generate (RAG)"):
        # Use company name directly
        try:
            # Call the new /dashboard/rag endpoint
            resp = requests.post(
                f"{API_BASE}/dashboard/rag",
                params={"company_name": choice},
                timeout=30  # Longer timeout for LLM generation
            )
            
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.rag_data = data  # Store in session state
                st.success(f"✅ Dashboard generated for {choice}")
            
            elif resp.status_code == 404:
                st.warning(f"⚠️ RAG collection not available for **{choice}**")
                st.info("The collection for this company hasn't been indexed yet. Please run the RAG indexing first.")
            
            else:
                st.error(f"❌ Error: {resp.status_code}")
                try:
                    st.json(resp.json())
                except:
                    st.error(resp.text)
        
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timeout - LLM generation may be slow or API not responding")
        except Exception as e:
            st.error(f"❌ Error generating dashboard: {e}")
    
    # Display stored RAG data if available
    if st.session_state.rag_data:
        data = st.session_state.rag_data
        
        # Create tabs for dashboard and context
        rag_tab1, rag_tab2 = st.tabs(["Dashboard", "Retrieved Context (Top-K)"])
        
        with rag_tab1:
            # Display the markdown dashboard
            if "markdown" in data and data["markdown"]:
                st.markdown(data["markdown"])
            else:
                st.warning("No dashboard content generated")
        
        with rag_tab2:
            # Display the retrieved context
            context_results = data.get("context_results", [])
            
            if context_results:
                st.write(f"**Retrieved {len(context_results)} context chunks:**")
                
                for idx, result in enumerate(context_results, 1):
                    similarity_score = result.get('similarity_score', 0)
                    with st.expander(f"Context {idx} (Score: {similarity_score:.4f})", expanded=idx == 1):
                        st.write("**Text:**")
                        st.write(result.get("text", ""))
                        
                        if result.get("metadata"):
                            st.write("**Metadata:**")
                            st.json(result.get("metadata", {}))
            else:
                st.info("No context results available")
