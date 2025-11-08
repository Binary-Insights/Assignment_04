"""
Airflow DAG for running LLM pipeline evaluations.

Evaluates all companies in ground_truth.json with both 'structured' and 'rag' pipelines.
Uses Python tasks to execute evaluation commands for each company/pipeline combination.

Schedule: Manual trigger (no automatic schedule)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import subprocess
import sys

logger = logging.getLogger(__name__)

# Get project root
# DAG is at /app/src/dags/eval_runner_dag.py, so go up 3 levels to /app
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Evaluation configuration
GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "eval" / "ground_truth.json"
EVAL_SCRIPT = PROJECT_ROOT / "src" / "evals" / "eval_runner.py"
PIPELINES = ["structured", "rag"]


def load_companies_from_ground_truth(**context):
    """
    Load company slugs from ground_truth.json.
    Returns list of company slugs for downstream tasks.
    """
    try:
        if not GROUND_TRUTH_FILE.exists():
            logger.error(f"Ground truth file not found: {GROUND_TRUTH_FILE}")
            return []
        
        with open(GROUND_TRUTH_FILE, "r") as f:
            ground_truth = json.load(f)
        
        companies = list(ground_truth.keys())
        logger.info(f"✓ Loaded {len(companies)} companies from ground truth")
        logger.info(f"  Companies: {', '.join(companies)}")
        
        # Store in XCom for downstream tasks
        context["task_instance"].xcom_push(
            key="companies",
            value=companies
        )
        
        return companies
    
    except Exception as e:
        logger.error(f"Error loading ground truth: {e}")
        raise


def evaluate_company_pipeline(company_slug: str, pipeline: str, **context):
    """
    Run evaluation for a specific company/pipeline combination.
    
    Args:
        company_slug: Company slug (e.g., "world-labs")
        pipeline: Pipeline type ("structured" or "rag")
    """
    try:
        logger.info(f"Starting evaluation: {company_slug} / {pipeline}")
        
        # Build command
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / EVAL_SCRIPT),
            "--company", company_slug,
            "--pipeline", pipeline,
            "--force"
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        # Execute evaluation
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        logger.info(f"STDOUT:\n{result.stdout}")
        
        if result.returncode != 0:
            logger.error(f"STDERR:\n{result.stderr}")
            raise RuntimeError(
                f"Evaluation failed for {company_slug}/{pipeline}: {result.stderr}"
            )
        
        logger.info(f"✓ Evaluation complete: {company_slug} / {pipeline}")
        
        return {
            "company": company_slug,
            "pipeline": pipeline,
            "status": "success"
        }
    
    except subprocess.TimeoutExpired:
        logger.error(f"Evaluation timeout for {company_slug}/{pipeline}")
        raise
    except Exception as e:
        logger.error(f"Error evaluating {company_slug}/{pipeline}: {e}")
        raise


def generate_comparison_report(**context):
    """
    Generate comparison report after all evaluations complete.
    """
    try:
        logger.info("Generating comparison report...")
        
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / EVAL_SCRIPT),
            "--batch",
            "--report"
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        logger.info(f"Report output:\n{result.stdout}")
        
        if result.returncode != 0:
            logger.error(f"Report generation failed: {result.stderr}")
            raise RuntimeError(f"Report generation failed: {result.stderr}")
        
        logger.info("✓ Comparison report generated")
        
        return {"status": "success", "message": "Report generated"}
    
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise


# Define DAG
with DAG(
    dag_id="eval_runner_dag",
    description="Run LLM pipeline evaluations for all companies",
    start_date=datetime(2025, 11, 7),
    schedule=None,  # Manual trigger only
    catchup=False,
    tags=["evaluation", "ml_pipeline", "quality_assurance"],
    max_active_runs=1,  # Only allow one active run
    default_view="graph",
) as dag:
    
    # Task 1: Load companies from ground truth
    load_companies = PythonOperator(
        task_id="load_companies",
        python_callable=load_companies_from_ground_truth,
        provide_context=True,
    )
    
    # Task 2: Dynamic task generation for each company/pipeline combination
    # We'll create these tasks dynamically
    evaluation_tasks = []
    
    # Load ground truth for dynamic task generation
    try:
        with open(GROUND_TRUTH_FILE, "r") as f:
            ground_truth = json.load(f)
        companies = list(ground_truth.keys())
    except Exception as e:
        logger.error(f"Failed to load ground truth for DAG creation: {e}")
        companies = []
    
    # Create evaluation tasks for each company and pipeline
    for company_slug in companies:
        for pipeline in PIPELINES:
            task_id = f"evaluate_{company_slug}_{pipeline}"
            
            task = PythonOperator(
                task_id=task_id,
                python_callable=evaluate_company_pipeline,
                op_kwargs={
                    "company_slug": company_slug,
                    "pipeline": pipeline,
                },
                provide_context=True,
                retries=2,  # Retry up to 2 times on failure
                retry_delay=60,  # Wait 60 seconds between retries
            )
            
            evaluation_tasks.append(task)
    
    # Task 3: Generate comparison report
    generate_report = PythonOperator(
        task_id="generate_comparison_report",
        python_callable=generate_comparison_report,
        provide_context=True,
        trigger_rule="all_done",  # Run even if some evaluations failed
    )
    
    # Define task dependencies
    load_companies >> evaluation_tasks >> generate_report

