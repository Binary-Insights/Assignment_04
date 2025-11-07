from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.models import Variable
from pathlib import Path
import json
import logging
import hashlib
from typing import List, Dict
import boto3

DATA_DIR = Path("/opt/airflow/data")
S3_BUCKET = "damg-assignment-04-airflow"
S3_PREFIX = "raw"
logger = logging.getLogger(__name__)

# Initialize S3 client
s3_client = boto3.client("s3")


def load_company_list(**context):
    """Load Forbes AI50 seed data and prepare for processing."""
    seed_path = DATA_DIR / "forbes_ai50_seed.json"
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")
    
    companies = json.loads(seed_path.read_text())
    logger.info(f"Loaded {len(companies)} companies from seed data")
    
    # Add company_id for tracking
    for i, c in enumerate(companies, 1):
        c["company_id"] = f"ai50_{i:02d}"
    
    return companies


def scrape_company_page(company: Dict, page_type: str = "main", **context) -> Dict:
    """
    Scrape a single company page.
    Args:
        company: Company dict with website URL
        page_type: Type of page to scrape (main, about, careers, blog)
    Returns:
        Dict with scrape results and metadata
    """
    company_id = company.get("company_id", "unknown")
    company_name = company.get("company_name", "unknown")
    website = company.get("website", "")
    
    logger.info(f"[{company_id}] Scraping {page_type} page for {company_name}: {website}")
    
    try:
        # TODO: Implement actual scraping logic
        # For now, return mock result
        result = {
            "company_id": company_id,
            "company_name": company_name,
            "page_type": page_type,
            "website": website,
            "status": "success",
            "scraped_at": context["ts"],
            "data": {"sample": "content"},  # Replace with actual scraped content
        }
        
        logger.info(f"[{company_id}] Successfully scraped {page_type} page")
        return result
        
    except Exception as e:
        logger.error(f"[{company_id}] Error scraping {page_type}: {str(e)}")
        return {
            "company_id": company_id,
            "company_name": company_name,
            "page_type": page_type,
            "status": "failed",
            "error": str(e),
            "scraped_at": context["ts"],
        }


def store_raw_to_cloud(companies: List[Dict], **context) -> Dict:
    """
    Store raw scraped data to S3 cloud storage structure.
    Creates: s3://damg-assignment-04-airflow/raw/<company_id>/metadata.json 
             + s3://damg-assignment-04-airflow/raw/<company_id>/<run_id>/pages/
    """
    run_id = context["run_id"]
    task_instance = context["ti"]
    
    # Pull scrape results from mapped task
    scrape_results = task_instance.xcom_pull(task_ids="scrape_company_pages")
    
    logger.info(f"Storing raw data for {len(companies)} companies to S3 (run: {run_id})")
    
    # Create metadata for each company
    ingest_summary = {
        "run_id": run_id,
        "timestamp": context["ts"],
        "total_companies": len(companies),
        "companies_processed": {},
        "s3_bucket": S3_BUCKET,
        "s3_prefix": S3_PREFIX,
    }
    
    for company in companies:
        company_id = company.get("company_id")
        company_name = company.get("company_name")
        
        # Store company metadata to S3
        metadata = {
            "company_id": company_id,
            "company_name": company_name,
            "website": company.get("website", ""),
            "linkedin": company.get("linkedin", ""),
            "hq_city": company.get("hq_city", ""),
            "hq_country": company.get("hq_country", ""),
            "ingestion_runs": [run_id],
        }
        
        metadata_key = f"{S3_PREFIX}/{company_id}/metadata.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2),
            ContentType="application/json",
        )
        logger.info(f"Stored metadata for {company_id} to s3://{S3_BUCKET}/{metadata_key}")
        
        # Store run metadata
        run_meta = {
            "run_id": run_id,
            "timestamp": context["ts"],
            "pages": {},
        }
        
        # Find scrape results for this company
        if scrape_results:
            for result in scrape_results:
                if result.get("company_id") == company_id:
                    page_type = result.get("page_type", "main")
                    run_meta["pages"][page_type] = {
                        "status": result.get("status"),
                        "scraped_at": result.get("scraped_at"),
                    }
                    
                    # Store page data to S3
                    if result.get("status") == "success":
                        page_key = f"{S3_PREFIX}/{company_id}/{run_id}/pages/{page_type}.json"
                        s3_client.put_object(
                            Bucket=S3_BUCKET,
                            Key=page_key,
                            Body=json.dumps(result.get("data", {}), indent=2),
                            ContentType="application/json",
                        )
                        logger.info(f"Stored {page_type} page for {company_id}")
        
        # Write run metadata to S3
        run_meta_key = f"{S3_PREFIX}/{company_id}/{run_id}/run_metadata.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=run_meta_key,
            Body=json.dumps(run_meta, indent=2),
            ContentType="application/json",
        )
        
        ingest_summary["companies_processed"][company_id] = {
            "company_name": company_name,
            "status": "processed",
        }
    
    # Write overall ingest log to S3
    ingest_log_key = f"{S3_PREFIX}/ingest_log.json"
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=ingest_log_key)
        existing_log = json.loads(response["Body"].read().decode("utf-8"))
    except s3_client.exceptions.NoSuchKey:
        existing_log = {}
    
    existing_log[run_id] = ingest_summary
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=ingest_log_key,
        Body=json.dumps(existing_log, indent=2),
        ContentType="application/json",
    )
    
    logger.info(f"Stored raw data for {len(companies)} companies to S3")
    return {
        "run_id": run_id,
        "companies_processed": len(companies),
        "output_location": f"s3://{S3_BUCKET}/{S3_PREFIX}/",
    }


with DAG(
    dag_id="ai50_full_ingest_dag",
    start_date=datetime(2025, 10, 31),
    schedule="@once",
    catchup=False,
    tags=["ai50", "orchestration"],
    description="Orchestrate full AI50 pipeline: discover → process → store",
) as dag:

    # Task 1: Trigger discover_ai50_dag
    trigger_discover = TriggerDagRunOperator(
        task_id="trigger_discover_ai50_dag",
        trigger_dag_id="discover_ai50_dag",
        wait_for_completion=True,
        poke_interval=30,  # Check every 30 seconds
    )

    # Task 2: Trigger process_pages_dag (after discover completes)
    trigger_process = TriggerDagRunOperator(
        task_id="trigger_process_pages_dag",
        trigger_dag_id="process_pages_dag",
        wait_for_completion=True,
        poke_interval=30,
    )

    # Task 3: Trigger store_ai50_data_dag (after process completes)
    trigger_store = TriggerDagRunOperator(
        task_id="trigger_store_ai50_data_dag",
        trigger_dag_id="store_ai50_data_dag",
        wait_for_completion=True,
        poke_interval=30,
    )

    # Define task dependencies: discover → process → store
    trigger_discover >> trigger_process >> trigger_store
