# 🚀 Project ORBIT: PE Dashboard Factory for Forbes AI 50
**DAMG 7245 – Fall 2025 – Binary Insights**

## Overview
Automates the extraction, embedding, retrieval, and structured-note generation of investment diligence data from **all Forbes AI 50 company websites**.  
Powered by **Apache Airflow**, **OpenAI GPT-4o**, **Selenium + ChromeDriver**, **LangChain**, **Pinecone**, **FastAPI**, **Streamlit**, and **AWS S3**, all containerized with **Docker + Docker Compose** for reproducible cloud deployment.

## Setup Instructions

---

## 1. Prerequisites
- **OS**: macOS, Linux, or Windows (WSL2)
- **Git**: Latest version
- **Docker**: 20.10+ and Docker Compose 2.0+
- **Python**: 3.11+ (for local dev)
- **API Keys**: 
  - OpenAI (required)
  - Pinecone (required for production)
  - AWS S3 (optional but recommended for cloud storage)

---

## 2. Clone the Repository
```bash
git clone https://github.com/Binary-Insights/Assignment_04.git
cd Assignment_04
```

---

## 3. Configure Environment Variables
Create a `.env` file in the project root:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Pinecone (for RAG pipeline)
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=bigdata-assignment-04
PINECONE_NAMESPACE=default

# AWS S3 (for cloud storage)
AWS_ACCESS_KEY_ID=your-aws-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET_NAME=damg-assignment-04-airflow

# Airflow Configuration
AIRFLOW_UID=$(id -u)
AIRFLOW__CORE__LOAD_EXAMPLES=False
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True
AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=10
```

---

## 4. Install Python Dependencies (Local Dev)
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5. Build & Start Docker
```bash
cd docker
docker-compose build --no-cache
docker-compose up -d
```

Wait 30–60 seconds for all services to initialize.

---

## 6. Verify Services
```bash
docker ps
```

Expected output:
- `airflow-scheduler`
- `airflow-webserver` (http://localhost:8080)
- `fastapi` (http://localhost:8000)
- `streamlit` (http://localhost:8501)

---

## 7. Access Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| **Airflow UI** | http://localhost:8080 | `airflow` / `airflow` |
| **FastAPI Docs** | http://localhost:8000/docs | N/A (Swagger) |
| **Streamlit Dashboard** | http://localhost:8501 | N/A (web) |

---

## 8. Run Pipelines

**Full Load (first-time):**
```bash
docker-compose exec airflow-webserver airflow dags trigger ai50_full_ingest_dag
```

**Daily Refresh:**
```bash
docker-compose exec airflow-webserver airflow dags trigger ai50_daily_refresh_dag
```

---

## 8a. Alternative DAGs

| DAG | Command | Purpose |
|-----|---------|---------|
| **Discover** | `airflow dags trigger discover_ai50_dag` | Fetch companies & discover pages |
| **Process Pages** | `airflow dags trigger process_pages_dag` | Scrape with Selenium |
| **Store to S3** | `airflow dags trigger store_ai50_data_dag` | Upload raw data & metadata |

---

## 9. Vector Indexing

```bash
python src/rag/ingest_to_pinecone.py --all --verbose
```

Chunks text (500 chars), generates embeddings, upserts to Pinecone.

---

## 10. Structured Extraction

```bash
python src/rag/structured_extraction.py --all --verbose
```

Extracts company records, events, products, leadership using GPT-4o + Instructor.

---

## 11. Generate Dashboards

**FastAPI:**
```bash
curl -X POST http://localhost:8000/dashboard/rag \
  -H "Content-Type: application/json" \
  -d '{"company_id": "world-labs"}'
```

**Streamlit:** Open http://localhost:8501, select company, choose pipeline.

---

## 12. Evaluate Pipelines

```bash
python src/backend/evaluate_rag_vs_structured.py
```

Scores both pipelines on factuality, schema adherence, provenance, hallucination, readability.

---

## 13. Stop Services

```bash
docker-compose down -v
```

---

## 14. Troubleshooting

| Issue | Fix |
|-------|-----|
| OpenAI error | Check `OPENAI_API_KEY` in `.env` |
| Pinecone failed | Verify `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` |
| Selenium timeout | Increase timeout or retry problematic sites |
| S3 upload fails | Check AWS credentials and bucket permissions |
| DAG not visible | Restart scheduler: `docker-compose restart airflow-scheduler` |
| Out of memory | Reduce `max_active_tasks_per_dag` in `.env` |
| Docker build fails | Run `docker system prune` with `--no-cache` |

---

## Architecture Diagram

![Project ORBIT Architecture](setup/architecture_diagram.png) — Visual system design and data flow

---

## Folder Structure

```
Assignment_04/
├── src/discover/               # Phase 0: Discovery
├── src/rag/                    # Phase 2-5: RAG & Structured
├── src/backend/                # Phase 4: API
├── src/frontend/               # Phase 4: UI
├── src/dags/                   # Alternative DAGs
├── dags/                       # Main orchestration DAGs
├── docker/                     # Containerization
├── data/                       # Raw, structured, vectors, payloads
├── chromedriver/               # Selenium
└── templates/                  # Prompt templates
```

---

## Key Features

✅ End-to-End Automation | ✅ Dual Pipelines (RAG & Structured)  
✅ LLM-Powered Discovery | ✅ JavaScript Rendering  
✅ Semantic Search (Pinecone) | ✅ Type-Safe Extraction  
✅ Airflow Orchestration | ✅ Streamlit Dashboard  
✅ Evaluation Framework | ✅ Cloud-Ready (Docker + S3)

---

## Links

📚 [Full Technical Codelabs](https://codelabs-preview.appspot.com/?file_id=1hCRRMtxdtcyp1OVLlNYxGbYM1qvOBnoxT4442yt5ZXY#0) — Detailed walkthrough  
📋 [Assignment Requirements](./Assignment.md) — Lab breakdown  
🎥 [Demo Video]() — Project walkthrough

---

## Tech Stack

Selenium | ChromeDriver | BeautifulSoup | AWS S3 | Apache Airflow | Pinecone | LangChain | Pydantic | Instructor | GPT-4o | OpenAI Embeddings | FastAPI | Streamlit | Docker

---

WE ATTEST THAT WE HAVEN'T USED ANY OTHER STUDENTS' WORK IN OUR ASSIGNMENT AND ABIDE BY THE POLICIES LISTED IN THE STUDENT HANDBOOK.





