from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import os
import subprocess
import logging
import sys

def run_process_discovered_pages():
    """
    Process discovered AI50 company pages.
    Extracts content and data from discovered pages using web scraping.
    
    Script expects:
    - data/company_pages_discovered.json (input)
    - Selenium WebDriver setup in container
    - Working directory: /opt/airflow
    """
    logger = logging.getLogger(__name__)
    
    # Set working directory to /opt/airflow (where data/ and workspace/ are mounted)
    work_dir = '/opt/airflow'
    script_path = os.path.join(work_dir, 'workspace', 'scripts', 'discover', 'process_discovered_pages.py')
    
    try:
        logger.info("="*70)
        logger.info("Starting process_discovered_pages")
        logger.info("="*70)
        logger.info(f"Working directory: {work_dir}")
        logger.info(f"Script path: {script_path}")
        logger.info(f"Current working dir: {os.getcwd()}")
        
        # Verify script exists
        if not os.path.exists(script_path):
            error_msg = f"❌ Script not found at {script_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Verify input file exists
        input_file = os.path.join(work_dir, 'data', 'company_pages_discovered.json')
        if not os.path.exists(input_file):
            error_msg = f"❌ Input file not found at {input_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        logger.info(f"✓ Script found: {script_path}")
        logger.info(f"✓ Input file found: {input_file}")
        
        # Run the script from work_dir so relative paths work
        logger.info(f"Executing: python {script_path}")
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=3600,  # 60 minutes (increased from 30 for 50 companies × 4 pages)
            cwd=work_dir,  # Set working directory
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}  # Enable unbuffered output
        )
        
        # Always log both stdout and stderr
        if result.stdout:
            logger.info(f"STDOUT:\n{result.stdout}")
        
        if result.stderr:
            logger.warning(f"STDERR:\n{result.stderr}")
        
        # Check for errors
        if result.returncode != 0:
            error_msg = (
                f"❌ Script failed with return code {result.returncode}\n"
                f"STDERR: {result.stderr if result.stderr else 'No error message'}"
            )
            logger.error(error_msg)
            raise Exception(error_msg)
        
        logger.info("="*70)
        logger.info("✓ process_discovered_pages completed successfully")
        logger.info("="*70)
        return "Success"
        
    except subprocess.TimeoutExpired as e:
        error_msg = f"❌ Script timeout (3600s exceeded)\n{str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)
    
    except FileNotFoundError as e:
        error_msg = f"❌ File not found: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
    
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise


default_args = {
    'owner': 'data-engineering-team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=60),  # Increased from 30 to 60 minutes
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
        execution_timeout=timedelta(minutes=60),  # Increased from 30 to 60 minutes
    )

    process_pages_task

