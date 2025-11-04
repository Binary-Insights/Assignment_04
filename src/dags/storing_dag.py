from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import os
import subprocess
import logging
import json

def get_valid_ai50_companies():
    """
    Dynamically discover valid AI50 company folders from data/raw.
    Validates companies against the seed data list.
    """
    logger = logging.getLogger(__name__)
    base_dir = '/opt/airflow/workspace'
    raw_data_path = os.path.join(base_dir, 'data', 'raw')
    seed_file_path = os.path.join(base_dir, 'data', 'forbes_ai50_seed.json')
    
    valid_companies = []
    
    # Load AI50 companies from seed data for validation
    try:
        with open(seed_file_path, 'r') as f:
            seed_data = json.load(f)
            # Assuming seed data has company identifiers (names or tickers)
            valid_company_ids = {item.get('name') or item.get('ticker') for item in seed_data}
    except Exception as e:
        logger.error(f"Failed to load forbes_ai50_seed.json: {e}")
        return []
    
    # Check if raw data directory exists
    if not os.path.exists(raw_data_path):
        logger.warning(f"Raw data directory not found: {raw_data_path}")
        return []
    
    # Discover folders in data/raw/
    for folder_name in os.listdir(raw_data_path):
        folder_path = os.path.join(raw_data_path, folder_name)
        if not os.path.isdir(folder_path):
            continue
        
        # Validate company exists in AI50 list
        if folder_name not in valid_company_ids:
            logger.warning(f"Folder {folder_name} is not a valid AI50 company, skipping")
            continue
        
        # Check if parsed directory exists (prerequisite for storing)
        parsed_dir_path = os.path.join(base_dir, 'data', 'parsed', folder_name)
        if not os.path.exists(parsed_dir_path):
            logger.warning(f"Missing parsed directory for {folder_name}: {parsed_dir_path}")
            continue
        
        # Check if there are any files to upload
        try:
            has_content = False
            for root, dirs, files in os.walk(parsed_dir_path):
                if files:
                    has_content = True
                    break
            
            if not has_content:
                logger.warning(f"No parsed content found for {folder_name} in {parsed_dir_path}")
                continue
        except Exception as e:
            logger.warning(f"Error checking parsed content for {folder_name}: {e}")
            continue
        
        valid_companies.append(folder_name)
        logger.info(f"Valid AI50 company found for storing: {folder_name}")
    
    logger.info(f"Total valid AI50 companies found for storing: {len(valid_companies)}")
    return valid_companies

def run_store_ai50_data(company_name):
    """
    Upload parsed data for a given AI50 company to S3.
    """
    logger = logging.getLogger(__name__)
    base_dir = '/opt/airflow/workspace'
    script_path = os.path.join(base_dir, 'scripts', 'store', 's3_uploader.py')
    local_folder = os.path.join(base_dir, 'data', 'parsed', company_name)
    bucket = os.environ.get('S3_BUCKET_NAME', 'damg-assignment-04-airflow')
    prefix = f'parsed/{company_name}'
    
    # Pre-flight checks
    if not os.path.exists(local_folder):
        raise Exception(f"Missing prerequisite: Parsed data directory not found at {local_folder}")
    
    if not os.path.exists(script_path):
        logger.warning(f"Script not found: {script_path}. Skipping S3 upload.")
        return f"Store skipped (script not found): {company_name}"
    
    # Check if there's actually content to upload
    has_content = False
    try:
        for root, dirs, files in os.walk(local_folder):
            if files:
                has_content = True
                break
        
        if not has_content:
            raise Exception(f"No files found to upload in {local_folder}")
    except Exception as e:
        raise Exception(f"Error checking content in {local_folder}: {e}")
    
    try:
        os.chdir(base_dir)
        logger.info(f"Uploading parsed data for {company_name} to S3")
        logger.info(f"Local folder: {local_folder}")
        logger.info(f"S3 destination: s3://{bucket}/{prefix}")
        
        result = subprocess.run([
            'python', script_path,
            '--local_folder', local_folder,
            '--bucket', bucket,
            '--prefix', prefix
        ], capture_output=True, text=True, timeout=900)
        
        logger.info(f"S3 upload output for {company_name}: {result.stdout}")
        
        if result.returncode != 0:
            logger.error(f"S3 upload error for {company_name}: {result.stderr}")
            raise Exception(f"Store failed for {company_name}: {result.stderr}")
        
        return f"Store Success: {company_name}"
        
    except subprocess.TimeoutExpired:
        logger.error(f"S3 upload timeout for {company_name}")
        raise Exception(f"Store timeout for {company_name}")
    except Exception as e:
        logger.error(f"Store error for {company_name}: {str(e)}")
        raise

default_args = {
    'owner': 'data-engineering-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 11, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'store_ai50_data_dag',
    default_args=default_args,
    description='Store parsed AI50 company data in S3 - dynamically discovers valid companies',
    schedule_interval=None,
    catchup=False,
    tags=['ai50', 'store', 's3'],
)

# Dynamically discover valid AI50 companies
AI50_COMPANIES = get_valid_ai50_companies()

store_tasks = []
for company in AI50_COMPANIES:
    store_task = PythonOperator(
        task_id=f'store_ai50_{company.lower().replace(" ", "_")}',
        python_callable=run_store_ai50_data,
        op_args=[company],
        dag=dag,
    )
    store_tasks.append(store_task)

# Log the discovered companies for debugging
logging.getLogger(__name__).info(f"DAG will process {len(AI50_COMPANIES)} AI50 companies: {AI50_COMPANIES}")
