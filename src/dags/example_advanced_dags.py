"""
Example: Advanced Airflow DAG Integration with FastAPI and Data Pipeline

This module shows how to create Airflow DAGs that:
1. Trigger FastAPI endpoints
2. Process data through your pipeline
3. Store results in the shared data volume
4. Handle errors gracefully
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.http_operator import SimpleHttpOperator
from airflow.models import Variable
from airflow.exceptions import AirflowException
import requests
import json
import logging

logger = logging.getLogger(__name__)

# Default arguments for all DAGs
default_args = {
    'owner': 'data-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 10, 31),
    'email_on_failure': False,
}

# ============================================================================
# Example 1: Basic DAG with FastAPI Integration
# ============================================================================

def fetch_company_data(**context):
    """Fetch company data from FastAPI backend"""
    try:
        response = requests.get('http://fastapi:8000/companies', timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Store in XCom for next tasks
        context['task_instance'].xcom_push(key='companies', value=data)
        logger.info(f"Fetched {len(data)} companies")
        return {'status': 'success', 'count': len(data)}
    except Exception as e:
        logger.error(f"Error fetching companies: {str(e)}")
        raise AirflowException(f"Failed to fetch companies: {str(e)}")


def process_company_data(**context):
    """Process company data"""
    companies = context['task_instance'].xcom_pull(
        task_ids='fetch_companies',
        key='companies'
    )
    
    logger.info(f"Processing {len(companies)} companies")
    
    # Add your processing logic here
    processed_data = {
        'timestamp': datetime.now().isoformat(),
        'total_companies': len(companies),
        'processed': True,
        'companies': companies
    }
    
    # Save to shared volume
    output_file = '/app/data/processed_results.json'
    with open(output_file, 'w') as f:
        json.dump(processed_data, f, indent=2)
    
    logger.info(f"Processed data saved to {output_file}")
    return {'status': 'success', 'file': output_file}


def validate_results(**context):
    """Validate processed results"""
    try:
        with open('/app/data/processed_results.json', 'r') as f:
            data = json.load(f)
        
        if data.get('processed'):
            logger.info("✅ Validation passed")
            return {'status': 'valid', 'records': data.get('total_companies', 0)}
        else:
            raise AirflowException("Validation failed: data not processed")
    except FileNotFoundError:
        raise AirflowException("Results file not found")


with DAG(
    dag_id='fastapi_data_pipeline',
    default_args=default_args,
    description='Integrate FastAPI with Airflow for data processing',
    schedule_interval='0 2 * * *',  # Daily at 2 AM
    catchup=False,
    tags=['fastapi', 'data-pipeline'],
) as dag_fastapi:
    
    fetch_task = PythonOperator(
        task_id='fetch_companies',
        python_callable=fetch_company_data,
        provide_context=True,
    )
    
    process_task = PythonOperator(
        task_id='process_data',
        python_callable=process_company_data,
        provide_context=True,
    )
    
    validate_task = PythonOperator(
        task_id='validate_results',
        python_callable=validate_results,
        provide_context=True,
    )
    
    # Set task dependencies
    fetch_task >> process_task >> validate_task


# ============================================================================
# Example 2: Parallel Processing with Error Handling
# ============================================================================

def process_company(company_id: str, **context):
    """Process individual company"""
    try:
        response = requests.post(
            f'http://fastapi:8000/process/{company_id}',
            json={'refresh': True},
            timeout=60
        )
        response.raise_for_status()
        return {'company_id': company_id, 'status': 'processed'}
    except Exception as e:
        logger.error(f"Error processing company {company_id}: {str(e)}")
        raise


def prepare_company_list(**context):
    """Prepare list of companies to process"""
    companies = [
        'world-labs',
        'anthropic',
        'abridge',
        'openai',
        'mistral'
    ]
    context['task_instance'].xcom_push(key='company_list', value=companies)
    return len(companies)


with DAG(
    dag_id='parallel_company_processing',
    default_args=default_args,
    description='Process multiple companies in parallel',
    schedule_interval='0 3 * * *',  # Daily at 3 AM
    catchup=False,
    tags=['parallel', 'companies'],
) as dag_parallel:
    
    prepare_task = PythonOperator(
        task_id='prepare_companies',
        python_callable=prepare_company_list,
    )
    
    # Create dynamic parallel tasks
    process_tasks = []
    company_ids = ['world-labs', 'anthropic', 'abridge']  # In production, fetch dynamically
    
    for company_id in company_ids:
        task = PythonOperator(
            task_id=f'process_{company_id}',
            python_callable=process_company,
            op_kwargs={'company_id': company_id},
            provide_context=True,
        )
        process_tasks.append(task)
    
    prepare_task >> process_tasks


# ============================================================================
# Example 3: Data Quality Checks and Notifications
# ============================================================================

def check_data_quality(**context):
    """Check data quality metrics"""
    try:
        response = requests.get('http://fastapi:8000/evals', timeout=30)
        response.raise_for_status()
        evals = response.json()
        
        # Check quality metrics
        issues = []
        for company_eval in evals:
            if company_eval.get('score', 0) < 7:
                issues.append({
                    'company': company_eval['company'],
                    'score': company_eval['score'],
                    'severity': 'warning'
                })
        
        if issues:
            logger.warning(f"Found {len(issues)} quality issues: {issues}")
            context['task_instance'].xcom_push(key='quality_issues', value=issues)
        
        return {
            'status': 'complete',
            'total_evaluated': len(evals),
            'issues': len(issues)
        }
    except Exception as e:
        logger.error(f"Error checking data quality: {str(e)}")
        raise


def notify_on_issues(**context):
    """Send notification if quality issues found"""
    issues = context['task_instance'].xcom_pull(
        task_ids='check_quality',
        key='quality_issues'
    ) or []
    
    if issues:
        message = f"⚠️ Data Quality Alert: {len(issues)} issues found\n"
        for issue in issues:
            message += f"  - {issue['company']}: Score {issue['score']}/14\n"
        
        logger.warning(message)
        # In production, send via email/Slack
    else:
        logger.info("✅ All data quality checks passed")
    
    return {'notified': True, 'issues': len(issues)}


with DAG(
    dag_id='data_quality_checks',
    default_args=default_args,
    description='Run data quality checks on evaluation results',
    schedule_interval='0 4 * * *',  # Daily at 4 AM
    catchup=False,
    tags=['quality', 'monitoring'],
) as dag_quality:
    
    quality_task = PythonOperator(
        task_id='check_quality',
        python_callable=check_data_quality,
        provide_context=True,
    )
    
    notify_task = PythonOperator(
        task_id='notify_issues',
        python_callable=notify_on_issues,
        provide_context=True,
    )
    
    quality_task >> notify_task


# ============================================================================
# Example 4: Scheduled Refresh with Logging
# ============================================================================

with DAG(
    dag_id='scheduled_refresh_with_logging',
    default_args=default_args,
    description='Refresh data and log results',
    schedule_interval='0 1 * * *',  # Daily at 1 AM
    catchup=False,
    tags=['refresh', 'scheduled'],
) as dag_refresh:
    
    start_task = BashOperator(
        task_id='start_refresh',
        bash_command='echo "Starting scheduled refresh..." && date',
    )
    
    refresh_changed = PythonOperator(
        task_id='refresh_changed_companies',
        python_callable=lambda **context: logger.info("Refreshing changed companies..."),
    )
    
    refresh_all = PythonOperator(
        task_id='refresh_all_companies',
        python_callable=lambda **context: logger.info("Refreshing all companies..."),
    )
    
    end_task = BashOperator(
        task_id='refresh_complete',
        bash_command='echo "Refresh complete!" && date',
    )
    
    start_task >> [refresh_changed, refresh_all] >> end_task


# ============================================================================
# Helper Functions for DAG Testing
# ============================================================================

def get_dag_status(dag_id: str):
    """Get current DAG status"""
    from airflow.models import DagRun
    
    latest_run = DagRun.find(dag_id=dag_id)
    if latest_run:
        return {
            'dag_id': dag_id,
            'state': latest_run[0].state,
            'execution_date': latest_run[0].execution_date,
            'start_date': latest_run[0].start_date,
            'end_date': latest_run[0].end_date,
        }
    return None


def get_task_logs(dag_id: str, run_id: str, task_id: str):
    """Get logs for a specific task"""
    from airflow.models import TaskInstance
    
    task = TaskInstance.get(
        dag_id=dag_id,
        run_id=run_id,
        task_id=task_id,
    )
    if task:
        return {
            'task_id': task.task_id,
            'state': task.state,
            'try_number': task.try_number,
            'start_date': task.start_date,
            'end_date': task.end_date,
        }
    return None


if __name__ == '__main__':
    # For testing
    logger.info("DAG definitions loaded successfully")
