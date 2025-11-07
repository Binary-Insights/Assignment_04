from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from pathlib import Path
import json
import logging
from typing import List, Dict
import boto3
import hashlib
import os

DATA_DIR = Path("/opt/airflow/data")
RAW_DIR = DATA_DIR / "raw"
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "damg-assignment-04-airflow")
S3_PREFIX = "raw"
DAILY_REFRESH_PREFIX = "daily_refresh"  # Separate prefix for delta runs
logger = logging.getLogger(__name__)

# Initialize S3 client
s3_client = boto3.client("s3")

# Pages to refresh daily (key pages for tracking changes)
REFRESH_PAGES = ["about", "careers", "blog"]

# Configuration
REFRESH_THRESHOLD_DAYS = 7  # Only refresh if not updated in 7 days
MAX_RETRIES = 2
TIMEOUT_PER_PAGE = 30  # seconds per page scrape


def load_changed_companies(**context) -> List[Dict]:
    """
    Scan the raw folder and identify companies that need daily refresh based on:
    1. Last refresh timestamp (7-day threshold)
    2. Whether company exists in raw folder
    3. Presence of metadata.json
    
    Returns list of companies ready for refresh with their metadata.
    """
    if not RAW_DIR.exists():
        logger.warning(f"Raw data directory not found: {RAW_DIR}. "
                      "Run full-load ingest (ai50_full_ingest_dag) first.")
        return []
    
    companies_to_refresh = []
    now = datetime.now()
    refresh_threshold = now - timedelta(days=REFRESH_THRESHOLD_DAYS)
    
    try:
        # Iterate through all company folders in raw/
        for company_dir in RAW_DIR.iterdir():
            if not company_dir.is_dir():
                continue
                
            # Look for metadata.json in company folder
            metadata_path = company_dir / "metadata.json"
            if not metadata_path.exists():
                logger.debug(f"No metadata.json found in {company_dir.name}, skipping")
                continue
            
            try:
                metadata = json.loads(metadata_path.read_text())
                company_id = metadata.get("company_id", company_dir.name)
                company_name = metadata.get("company_name", "Unknown")
                
                # Check if company needs refresh
                last_refresh_time = _get_last_refresh_time(company_dir)
                
                if last_refresh_time is None:
                    # First time refresh for this company
                    logger.info(f"[{company_id}] Scheduled for first refresh (no previous runs)")
                    companies_to_refresh.append({
                        **metadata,
                        "_refresh_reason": "first_time",
                        "_last_refresh": None
                    })
                elif last_refresh_time < refresh_threshold:
                    # Last refresh is older than threshold
                    days_since = (now - last_refresh_time).days
                    logger.info(f"[{company_id}] Scheduled for refresh (last: {days_since} days ago)")
                    companies_to_refresh.append({
                        **metadata,
                        "_refresh_reason": "threshold_exceeded",
                        "_last_refresh": last_refresh_time.isoformat()
                    })
                else:
                    days_until = (REFRESH_THRESHOLD_DAYS - (now - last_refresh_time).days)
                    logger.debug(f"[{company_id}] Skip refresh (next in {days_until} days)")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in metadata for {company_dir.name}: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing {company_dir.name}: {str(e)}")
        
        logger.info(f"Identified {len(companies_to_refresh)} companies for daily refresh")
        return companies_to_refresh
        
    except Exception as e:
        logger.error(f"Error scanning raw directory: {str(e)}")
        return []


def _get_last_refresh_time(company_dir: Path) -> datetime:
    """
    Get the timestamp of the most recent refresh run for a company.
    Looks for: daily_refresh/ subfolders with timestamp-named runs.
    Returns: datetime of last refresh or None if no previous refresh.
    """
    daily_refresh_dir = company_dir / DAILY_REFRESH_PREFIX
    
    if not daily_refresh_dir.exists():
        return None
    
    try:
        # Find all timestamped run folders (format: YYYY-MM-DD-HH-MM-SS)
        run_folders = [
            d for d in daily_refresh_dir.iterdir()
            if d.is_dir() and _is_valid_timestamp_folder(d.name)
        ]
        
        if not run_folders:
            return None
        
        # Return the most recent one
        latest_run = max(run_folders, key=lambda x: x.stat().st_mtime)
        return datetime.fromtimestamp(latest_run.stat().st_mtime)
        
    except Exception as e:
        logger.warning(f"Error reading last refresh time for {company_dir.name}: {str(e)}")
        return None


def _is_valid_timestamp_folder(folder_name: str) -> bool:
    """Validate if folder name follows timestamp pattern YYYY-MM-DD-HH-MM-SS."""
    try:
        parts = folder_name.split("-")
        if len(parts) != 6:
            return False
        # Validate year, month, day, hour, minute, second
        datetime.strptime(f"{parts[0]}{parts[1]}{parts[2]} {parts[3]}{parts[4]}{parts[5]}", 
                         "%Y%m%d %H%M%S")
        return True
    except (ValueError, IndexError):
        return False


def scrape_company_changes(company: Dict, **context) -> Dict:
    """
    Scrape key pages (About, Careers, Blog) and detect changes via content hashing.
    
    For each page:
    - Fetch current content
    - Compute content hash
    - Compare with previous hash (if exists)
    - Flag if changes detected
    
    Returns: Dict with per-page results and change summary.
    """
    company_id = company.get("company_id")
    company_name = company.get("company_name")
    website = company.get("website", "")
    refresh_reason = company.get("_refresh_reason", "manual")
    
    logger.info(f"[{company_id}] Starting daily refresh for {company_name} "
               f"({refresh_reason})")
    
    # Create result structure
    results = {
        "company_id": company_id,
        "company_name": company_name,
        "website": website,
        "run_timestamp": context["ts"],
        "execution_date": context["execution_date"].isoformat(),
        "pages": {},
        "changes_detected": False,
        "pages_changed": [],
        "pages_unchanged": [],
        "pages_failed": [],
        "summary": {
            "total_pages": len(REFRESH_PAGES),
            "successful": 0,
            "failed": 0,
            "changed": 0,
            "unchanged": 0,
        }
    }
    
    try:
        # Get company folder for hash comparison
        company_dir = RAW_DIR / company_id
        previous_hashes = _load_previous_hashes(company_dir)
        
        # Scrape each key page
        for page_type in REFRESH_PAGES:
            page_result = _scrape_page_with_delta_detection(
                company_id=company_id,
                website=website,
                page_type=page_type,
                previous_hash=previous_hashes.get(page_type),
                retry_count=MAX_RETRIES
            )
            
            results["pages"][page_type] = page_result
            
            if page_result["status"] == "success":
                results["summary"]["successful"] += 1
                
                if page_result.get("changed"):
                    results["changes_detected"] = True
                    results["pages_changed"].append(page_type)
                    results["summary"]["changed"] += 1
                    logger.info(f"[{company_id}] Changes detected in {page_type} page")
                else:
                    results["pages_unchanged"].append(page_type)
                    results["summary"]["unchanged"] += 1
                    logger.info(f"[{company_id}] No changes in {page_type} page")
            else:
                results["summary"]["failed"] += 1
                results["pages_failed"].append(page_type)
                logger.warning(f"[{company_id}] Failed to scrape {page_type}: "
                             f"{page_result.get('error', 'Unknown error')}")
        
        return results
        
    except Exception as e:
        logger.error(f"[{company_id}] Fatal error during refresh: {str(e)}")
        results["status"] = "failed"
        results["error"] = str(e)
        results["summary"]["failed"] = len(REFRESH_PAGES)
        return results


def _load_previous_hashes(company_dir: Path) -> Dict[str, str]:
    """
    Load previous content hashes from the most recent daily_refresh run.
    Returns: Dict[page_type] -> hash_value
    """
    hashes = {}
    daily_refresh_dir = company_dir / DAILY_REFRESH_PREFIX
    
    if not daily_refresh_dir.exists():
        return hashes
    
    try:
        # Find most recent run
        run_folders = [
            d for d in daily_refresh_dir.iterdir()
            if d.is_dir() and _is_valid_timestamp_folder(d.name)
        ]
        
        if not run_folders:
            return hashes
        
        latest_run = max(run_folders, key=lambda x: x.stat().st_mtime)
        hashes_file = latest_run / "content_hashes.json"
        
        if hashes_file.exists():
            hashes = json.loads(hashes_file.read_text())
            logger.debug(f"Loaded previous hashes from {latest_run.name}")
        
    except Exception as e:
        logger.warning(f"Could not load previous hashes: {str(e)}")
    
    return hashes


def _scrape_page_with_delta_detection(company_id: str, website: str, page_type: str,
                                     previous_hash: str = None, retry_count: int = 2) -> Dict:
    """
    Scrape a single page and detect changes via content hash.
    
    Args:
        company_id: Company identifier
        website: Company website URL
        page_type: Page to scrape (about, careers, blog)
        previous_hash: Previous content hash for comparison
        retry_count: Number of retry attempts
    
    Returns: Dict with page status, content, hash, and change detection
    """
    page_result = {
        "page_type": page_type,
        "status": "pending",
        "url": _build_page_url(website, page_type),
        "content_hash": None,
        "content_length": 0,
        "changed": False,
        "error": None,
    }
    
    for attempt in range(retry_count):
        try:
            logger.debug(f"[{company_id}] Scraping {page_type} (attempt {attempt + 1}/{retry_count})")
            
            # TODO: Replace with actual scraping logic
            # For now, simulate scraping
            content = _simulate_page_scrape(company_id, page_type)
            
            # Compute content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            page_result["status"] = "success"
            page_result["content_hash"] = content_hash
            page_result["content_length"] = len(content)
            
            # Detect change
            if previous_hash and previous_hash != content_hash:
                page_result["changed"] = True
                logger.info(f"[{company_id}] {page_type} content changed (hash mismatch)")
            elif previous_hash and previous_hash == content_hash:
                page_result["changed"] = False
            
            return page_result
            
        except Exception as e:
            logger.warning(f"[{company_id}] Error scraping {page_type} "
                          f"(attempt {attempt + 1}): {str(e)}")
            page_result["error"] = str(e)
            
            if attempt < retry_count - 1:
                logger.debug(f"Retrying in 5 seconds...")
                import time
                time.sleep(5)
    
    page_result["status"] = "failed"
    return page_result


def _build_page_url(website: str, page_type: str) -> str:
    """Build full URL for page type."""
    if not website:
        return ""
    
    # Ensure website has protocol
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    
    # Remove trailing slash
    website = website.rstrip("/")
    
    page_paths = {
        "about": "/about",
        "careers": "/careers",
        "blog": "/blog",
    }
    
    return website + page_paths.get(page_type, "")


def _simulate_page_scrape(company_id: str, page_type: str) -> str:
    """
    Simulate page scraping (placeholder).
    Replace with actual scraping logic using Selenium/BeautifulSoup.
    """
    # TODO: Implement actual web scraping
    # This is a placeholder that returns mock content
    return f"Mock content for {company_id} {page_type} page at {datetime.now().isoformat()}"


def store_refresh_results(**context) -> Dict:
    """
    Store daily refresh results to local filesystem and S3 in organized structure:
    
    Local Structure:
      raw/<company_id>/
        ├── metadata.json
        └── daily_refresh/
            └── YYYY-MM-DD-HH-MM-SS/  (timestamped run folder)
                ├── refresh_results.json (full run data)
                ├── content_hashes.json (for delta detection next run)
                ├── about.json
                ├── careers.json
                ├── blog.json
                └── run_log.json
    
    S3 Structure:
      damg-assignment-04-airflow/
        ├── daily_refresh/
        │   ├── YYYY-MM-DD-HH-MM-SS/
        │   │   ├── <company_id>/refresh_results.json
        │   │   └── summary.json
        │   └── index.json (listing of all runs)
    
    Args:
        context: Airflow context with execution_date and ti
    
    Returns:
        Dict with summary of stored results
    """
    execution_date = context["execution_date"]
    run_timestamp = execution_date.strftime("%Y-%m-%d-%H-%M-%S")
    task_instance = context["ti"]
    
    logger.info(f"Storing daily refresh results with timestamp: {run_timestamp}")
    
    # Pull refresh results from previous task
    refresh_results_list = task_instance.xcom_pull(task_ids="refresh_company_pages")
    
    if not refresh_results_list:
        logger.warning("No refresh results to store")
        return {
            "run_timestamp": run_timestamp,
            "companies_processed": 0,
            "succeeded": 0,
            "failed": 0,
            "changes_detected": [],
        }
    
    # Ensure it's a list
    if not isinstance(refresh_results_list, list):
        refresh_results_list = [refresh_results_list]
    
    summary = {
        "run_timestamp": run_timestamp,
        "execution_date": execution_date.isoformat(),
        "companies_processed": len(refresh_results_list),
        "succeeded": 0,
        "failed": 0,
        "changes_detected": [],
        "companies_with_changes": [],
        "storage_locations": {
            "local": [],
            "s3": [],
        },
        "errors": [],
    }
    
    for result in refresh_results_list:
        company_id = result.get("company_id")
        company_name = result.get("company_name")
        
        try:
            # Determine if this result succeeded
            result_status = result.get("status", "pending")
            success = result_status == "success" or result.get("summary", {}).get("successful", 0) > 0
            
            if success:
                summary["succeeded"] += 1
            else:
                summary["failed"] += 1
            
            # Check for changes
            if result.get("changes_detected"):
                summary["changes_detected"].append(company_id)
                summary["companies_with_changes"].append({
                    "company_id": company_id,
                    "company_name": company_name,
                    "changed_pages": result.get("pages_changed", []),
                })
                logger.info(f"[{company_id}] Changes detected: {result.get('pages_changed', [])}")
            
            # Store to local filesystem in timestamped subfolder
            local_path = _store_locally(company_id, run_timestamp, result)
            if local_path:
                summary["storage_locations"]["local"].append(str(local_path))
            
            # Store to S3 in timestamped subfolder
            s3_path = _store_to_s3(company_id, run_timestamp, result)
            if s3_path:
                summary["storage_locations"]["s3"].append(s3_path)
            
        except Exception as e:
            logger.error(f"[{company_id}] Error storing results: {str(e)}")
            summary["failed"] += 1
            summary["errors"].append({
                "company_id": company_id,
                "error": str(e),
            })
    
    # Store overall summary locally and in S3
    summary_path = _store_summary(run_timestamp, summary)
    
    logger.info(f"Daily refresh storage complete: "
               f"{summary['succeeded']} succeeded, {summary['failed']} failed, "
               f"{len(summary['changes_detected'])} with changes detected")
    
    return summary


def _store_locally(company_id: str, run_timestamp: str, result: Dict) -> Path:
    """
    Store refresh results locally in timestamped subfolder.
    Structure: raw/<company_id>/daily_refresh/<run_timestamp>/
    """
    try:
        company_dir = RAW_DIR / company_id
        daily_refresh_dir = company_dir / DAILY_REFRESH_PREFIX / run_timestamp
        daily_refresh_dir.mkdir(parents=True, exist_ok=True)
        
        # Store full result
        result_file = daily_refresh_dir / "refresh_results.json"
        result_file.write_text(json.dumps(result, indent=2))
        logger.info(f"[{company_id}] Stored locally: {result_file}")
        
        # Store per-page results
        for page_type, page_data in result.get("pages", {}).items():
            page_file = daily_refresh_dir / f"{page_type}.json"
            page_file.write_text(json.dumps(page_data, indent=2))
        
        # Store content hashes for next run's delta detection
        hashes = {
            page_type: page_data.get("content_hash")
            for page_type, page_data in result.get("pages", {}).items()
            if page_data.get("status") == "success"
        }
        if hashes:
            hashes_file = daily_refresh_dir / "content_hashes.json"
            hashes_file.write_text(json.dumps(hashes, indent=2))
        
        # Store run metadata/log
        run_log = {
            "run_timestamp": run_timestamp,
            "company_id": company_id,
            "status": "completed",
            "summary": result.get("summary", {}),
            "execution_date": result.get("execution_date"),
        }
        log_file = daily_refresh_dir / "run_log.json"
        log_file.write_text(json.dumps(run_log, indent=2))
        
        return daily_refresh_dir
        
    except Exception as e:
        logger.error(f"[{company_id}] Error storing locally: {str(e)}")
        return None


def _store_to_s3(company_id: str, run_timestamp: str, result: Dict) -> str:
    """
    Store refresh results to S3 in timestamped prefix.
    Structure: s3://bucket/daily_refresh/<run_timestamp>/<company_id>/
    """
    try:
        # Store full result
        result_key = f"{DAILY_REFRESH_PREFIX}/{run_timestamp}/{company_id}/refresh_results.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=result_key,
            Body=json.dumps(result, indent=2),
            ContentType="application/json",
            Metadata={
                "company_id": company_id,
                "run_timestamp": run_timestamp,
            }
        )
        logger.info(f"[{company_id}] Stored to S3: s3://{S3_BUCKET}/{result_key}")
        
        # Store per-page results
        for page_type, page_data in result.get("pages", {}).items():
            if page_data.get("status") == "success":
                page_key = f"{DAILY_REFRESH_PREFIX}/{run_timestamp}/{company_id}/{page_type}.json"
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=page_key,
                    Body=json.dumps(page_data, indent=2),
                    ContentType="application/json",
                )
        
        # Store hashes for next run
        hashes = {
            page_type: page_data.get("content_hash")
            for page_type, page_data in result.get("pages", {}).items()
            if page_data.get("status") == "success"
        }
        if hashes:
            hashes_key = f"{DAILY_REFRESH_PREFIX}/{run_timestamp}/{company_id}/content_hashes.json"
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=hashes_key,
                Body=json.dumps(hashes, indent=2),
                ContentType="application/json",
            )
        
        return f"s3://{S3_BUCKET}/{result_key}"
        
    except Exception as e:
        logger.error(f"[{company_id}] Error storing to S3: {str(e)}")
        return None


def _store_summary(run_timestamp: str, summary: Dict) -> Path:
    """
    Store overall daily refresh summary locally and in S3.
    """
    try:
        # Local summary
        summary_dir = RAW_DIR / DAILY_REFRESH_PREFIX
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_file = summary_dir / f"summary_{run_timestamp}.json"
        summary_file.write_text(json.dumps(summary, indent=2))
        logger.info(f"Stored summary: {summary_file}")
        
        # S3 summary
        summary_key = f"{DAILY_REFRESH_PREFIX}/{run_timestamp}/summary.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=summary_key,
            Body=json.dumps(summary, indent=2),
            ContentType="application/json",
        )
        logger.info(f"Stored summary to S3: s3://{S3_BUCKET}/{summary_key}")
        
        return summary_file
        
    except Exception as e:
        logger.error(f"Error storing summary: {str(e)}")
        return None


with DAG(
    dag_id="ai50_daily_refresh_dag",
    start_date=datetime(2025, 10, 31),
    schedule="0 3 * * *",  # Daily at 3 AM UTC
    catchup=False,
    tags=["ai50", "orbit", "daily", "delta"],
    description="Daily delta refresh: Scan raw folder, identify companies needing refresh (7-day threshold), "
                "scrape key pages (About, Careers, Blog), detect changes via content hash, store in "
                "timestamped subfolders for version control and audit trail.",
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=60),
    },
) as dag:

    # Task 1: Scan raw folder and identify companies needing refresh
    load_changed_task = PythonOperator(
        task_id="load_changed_companies",
        python_callable=load_changed_companies,
        provide_context=True,
        doc="Scan {RAW_DIR} and identify companies where last refresh > 7 days old",
    )

    # Task 2: Scrape key pages for identified companies with delta detection
    # Uses task_instance.xcom_push to pass list to next task
    def scrape_all_companies(**context):
        """Wrapper to process all companies from load_changed_companies."""
        task_instance = context["ti"]
        companies = task_instance.xcom_pull(task_ids="load_changed_companies")
        
        if not companies:
            logger.info("No companies to scrape")
            return []
        
        results = []
        for company in companies:
            result = scrape_company_changes(company, **context)
            results.append(result)
        
        return results
    
    refresh_pages_task = PythonOperator(
        task_id="refresh_company_pages",
        python_callable=scrape_all_companies,
        provide_context=True,
        doc="Scrape About, Careers, Blog pages. Detect changes via content hash comparison.",
    )

    # Task 3: Store results in timestamped subfolders (both local and S3)
    store_results_task = PythonOperator(
        task_id="store_refresh_results",
        python_callable=store_refresh_results,
        provide_context=True,
        doc="Store results to {RAW_DIR}/<company>/daily_refresh/<timestamp>/ and S3 "
            "with content hashes for next run's delta detection.",
    )

    # Define task dependencies
    # load_changed_companies provides list -> passed to refresh_company_pages -> store_refresh_results
    load_changed_task >> refresh_pages_task >> store_results_task
