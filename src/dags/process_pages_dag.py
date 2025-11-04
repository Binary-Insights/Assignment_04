from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import os
import subprocess
import logging

def run_process_discovered_pages():
    """
    Process discovered AI50 company pages.
    Extracts content and data from discovered pages using web scraping.
    """
    logger = logging.getLogger(__name__)
    base_dir = '/opt/airflow/workspace'
    script_path = os.path.join(base_dir, 'scripts', 'discover', 'process_discovered_pages.py')
    
    try:
        os.chdir(base_dir)
        result = subprocess.run(['python', script_path], capture_output=True, text=True, timeout=600)
        logger.info(result.stdout)
        
        if result.returncode != 0:
            logger.error(result.stderr)
            raise Exception(f"Process discovered pages failed: {result.stderr}")
        
        return "Process Discovered Pages Success"
    except Exception as e:
        logger.error(str(e))
        raise

default_args = {
    'owner': 'data-engineering-team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=30),
}

with DAG(
    dag_id='process_pages_dag',
    default_args=default_args,
    description='Process discovered AI50 company pages and extract content',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2025, 11, 1),
    catchup=False,
    tags=['ai50', 'process', 'pages'],
) as dag:

    process_pages_task = PythonOperator(
        task_id='process_ai50_pages',
        python_callable=run_process_discovered_pages,
        execution_timeout=timedelta(minutes=30),
    )

    process_pages_task
