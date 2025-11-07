"""
Airflow DAG: Batch RAG Pipeline for All 50 Forbes AI Companies

End-to-end RAG pipeline that:
1. Runs experimental_framework.py for all 50 companies
2. Ingests all chunks into Qdrant vector database

This DAG orchestrates the complete batch processing workflow.
"""

import os
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from airflow import DAG
from airflow.decorators import task

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
BASE_DIR = Path("/opt/airflow/workspace")
PYTHON_EXE = "python"

default_args = {
    "owner": "ai50_data_team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

logger = logging.getLogger("rag_batch_ingestion_dag")
logger.setLevel(logging.INFO)

# -------------------------------------------------------------------
# DAG Definition
# -------------------------------------------------------------------
with DAG(
    dag_id="rag_batch_ingest_all_companies",
    description="Batch RAG pipeline: experimental_framework for all 50 companies + ingest to Qdrant",
    default_args=default_args,
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2025, 11, 6),
    catchup=False,
    max_active_runs=1,
    tags=["rag", "qdrant", "batch", "all_companies"],
) as dag:

    # =====================================================
    # 1️⃣ Run experimental framework for ALL 50 companies
    # =====================================================
    @task(task_id="run_experimental_framework_batch")
    def run_experimental_framework_batch():
        """
        Run run_all_companies.py to process all 50 companies.
        
        This script will:
        - Load all company names from forbes_ai50_seed.json
        - Run experimental_framework.py for each company
        - Generate chunks_recursive.json and chunks_markdownheader.json for each
        - Save to data/rag_experiments/{company_slug}/
        """
        cmd = [
            PYTHON_EXE,
            "run_all_companies.py",
            "--verbose",
            "--keyword-method", "tfidf",  # Use fastest method for batch
        ]
        
        logger.info(f"🚀 Running experimental framework batch: {' '.join(cmd)}")
        logger.info("⏳ This will process all 50 Forbes AI companies...")
        
        res = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=3600  # 1 hour timeout for all companies
        )
        
        if res.returncode != 0:
            logger.error(f"❌ Experimental framework batch failed:\n{res.stderr}")
            raise RuntimeError(f"Batch processing failed: {res.stderr}")
        
        # Log summary
        logger.info(f"✅ Experimental framework batch completed")
        logger.info(f"Output:\n{res.stdout[-2000:]}")  # Last 2000 chars
        
        return {
            "status": "success",
            "message": "All companies processed"
        }

    # =====================================================
    # 2️⃣ Ingest all chunks into Qdrant
    # =====================================================
    @task(task_id="ingest_all_to_qdrant")
    def ingest_all_to_qdrant():
        """
        Ingest all generated chunks from all companies into Qdrant.
        
        This script will:
        - Read chunks_recursive.json from each company output
        - Create embeddings for each chunk
        - Upload to Qdrant collection 'rag_chunks'
        """
        cmd = [
            PYTHON_EXE,
            "src/rag/ingest_to_qdrant.py",
            "--input-dir", "data/rag_experiments",
            "--chunk-file", "chunks_recursive.json",
            "--collection", "rag_chunks",
        ]
        
        logger.info(f"🚀 Running Qdrant ingestion: {' '.join(cmd)}")
        logger.info("⏳ Ingesting all chunks into Qdrant...")
        
        res = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=1800  # 30 minute timeout for ingestion
        )
        
        if res.returncode != 0:
            logger.error(f"❌ Qdrant ingestion failed:\n{res.stderr}")
            raise RuntimeError(f"Qdrant ingestion failed: {res.stderr}")
        
        # Log summary
        logger.info(f"✅ Qdrant ingestion completed")
        logger.info(f"Output:\n{res.stdout[-2000:]}")  # Last 2000 chars
        
        return {
            "status": "success",
            "message": "All chunks ingested into Qdrant"
        }

    # =====================================================
    # 3️⃣ Verify Qdrant collection
    # =====================================================
    @task(task_id="verify_qdrant_collection")
    def verify_qdrant_collection():
        """
        Verify that chunks were successfully ingested into Qdrant.
        
        Runs a health check and collection info query.
        """
        import requests
        
        qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        collection_name = "rag_chunks"
        
        logger.info(f"🔍 Verifying Qdrant collection at {qdrant_url}")
        
        try:
            # Check health
            health_resp = requests.get(f"{qdrant_url}/health", timeout=10)
            if health_resp.status_code != 200:
                raise RuntimeError(f"Qdrant health check failed: {health_resp.status_code}")
            logger.info("✅ Qdrant health check passed")
            
            # Get collection info
            info_resp = requests.get(
                f"{qdrant_url}/collections/{collection_name}",
                timeout=10
            )
            
            if info_resp.status_code == 200:
                info = info_resp.json()
                vector_count = info.get("result", {}).get("points_count", 0)
                logger.info(f"✅ Collection '{collection_name}' exists with {vector_count} points")
                return {
                    "status": "success",
                    "collection": collection_name,
                    "vector_count": vector_count
                }
            else:
                logger.warning(f"⚠️  Collection info not available: {info_resp.status_code}")
                return {
                    "status": "warning",
                    "message": "Collection verification inconclusive"
                }
        
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            raise RuntimeError(f"Collection verification failed: {e}")

    # =====================================================
    # 4️⃣ Run structured extraction for ALL 50 companies
    # =====================================================
    @task(task_id="run_structured_extraction_batch")
    def run_structured_extraction_batch():
        """
        Run run_all_structured.py to process all 50 companies with structured extraction.
        
        This script will:
        - Load all company names from forbes_ai50_seed.json
        - Run structured_extraction.py for each company
        - Generate structured payloads based on Pydantic schema
        - Save to data/structured/{company_slug}.json for each
        """
        cmd = [
            PYTHON_EXE,
            "run_all_structured.py",
            "--verbose",
        ]
        
        logger.info(f"🚀 Running structured extraction batch: {' '.join(cmd)}")
        logger.info("⏳ This will process all 50 Forbes AI companies with structured extraction...")
        
        res = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=3600  # 1 hour timeout for all companies
        )
        
        if res.returncode != 0:
            logger.error(f"❌ Structured extraction batch failed:\n{res.stderr}")
            raise RuntimeError(f"Structured extraction failed: {res.stderr}")
        
        # Log summary
        logger.info(f"✅ Structured extraction batch completed")
        logger.info(f"Output:\n{res.stdout[-2000:]}")  # Last 2000 chars
        
        return {
            "status": "success",
            "message": "All companies extracted with structured pipeline"
        }

    # =====================================================
    # DAG Orchestration
    # =====================================================
    exp_task = run_experimental_framework_batch()
    ingest_task = ingest_all_to_qdrant()
    verify_task = verify_qdrant_collection()
    struct_task = run_structured_extraction_batch()

    # Sequential pipeline for RAG
    exp_task >> ingest_task >> verify_task
    
    # Parallel: Structured extraction runs alongside RAG
    exp_task >> struct_task
