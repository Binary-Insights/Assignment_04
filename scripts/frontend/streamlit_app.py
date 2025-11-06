import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="PE Dashboard (AI 50)", layout="wide")
st.title("Project ORBIT – PE Dashboard for Forbes AI 50")

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
        # Convert company name to slug format (lowercase, spaces/underscores to hyphens)
        company_slug = choice.lower().replace(" ", "-").replace("_", "-")
        
        try:
            # Try to fetch structured data for the selected company
            resp = requests.get(
                f"{API_BASE}/dashboard/structured",
                params={"company_slug": company_slug},
                timeout=5
            )
            
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"✅ Structured data loaded for {choice}")
                
                # Display the structured data
                if "data" in data and data["data"]:
                    structured_data = data["data"]
                    
                    # Create tabs for different data sections
                    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                        "Company Info",
                        "Events",
                        "Products",
                        "Leadership",
                        "Visibility",
                        "Raw JSON"
                    ])
                    
                    with tab1:
                        if "company_record" in structured_data:
                            st.json(structured_data["company_record"])
                        else:
                            st.info("No company record available")
                    
                    with tab2:
                        if "events" in structured_data and structured_data["events"]:
                            st.write(f"Total Events: {len(structured_data['events'])}")
                            st.json(structured_data["events"])
                        else:
                            st.info("No events available")
                    
                    with tab3:
                        if "products" in structured_data and structured_data["products"]:
                            st.write(f"Total Products: {len(structured_data['products'])}")
                            st.json(structured_data["products"])
                        else:
                            st.info("No products available")
                    
                    with tab4:
                        if "leadership" in structured_data and structured_data["leadership"]:
                            st.write(f"Total Leadership: {len(structured_data['leadership'])}")
                            st.json(structured_data["leadership"])
                        else:
                            st.info("No leadership data available")
                    
                    with tab5:
                        if "visibility" in structured_data and structured_data["visibility"]:
                            st.write(f"Total Visibility Records: {len(structured_data['visibility'])}")
                            st.json(structured_data["visibility"])
                        else:
                            st.info("No visibility data available")
                    
                    with tab6:
                        st.json(structured_data)
                else:
                    st.warning("No data found in response")
            
            elif resp.status_code == 404:
                st.warning(f"⚠️ Structured data not available for **{choice}**")
                st.info(f"The JSON file for this company hasn't been extracted yet. Please run the extraction pipeline first.")
            
            else:
                st.error(f"❌ Error: {resp.status_code}")
                st.json(resp.json())
        
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timeout - API not responding")
        except Exception as e:
            st.error(f"❌ Error fetching structured data: {e}")

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
                st.success(f"✅ Dashboard generated for {choice}")
                
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
