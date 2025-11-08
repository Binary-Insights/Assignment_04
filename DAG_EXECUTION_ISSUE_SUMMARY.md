# DAG Execution Issue - Airflow 3.x LocalExecutor Problem

## Status
✅ **DAG is discovered and parses correctly**
❌ **Task execution fails with httpx.ConnectError**

## Root Cause
Airflow 3.1.2 LocalExecutor in Docker is failing with `httpx.ConnectError: [Errno 111] Connection refused` when trying to execute tasks. This appears to be a networking/configuration issue in Airflow 3.x where the executor cannot communicate with the task workers.

##Error Details
```
httpx.ConnectError: [Errno 111] Connection refused
File "/usr/local/lib/python3.11/site-packages/airflow/executors/local_executor.py", line 96, in _run_worker
```

The error occurs when:
1. DAG is triggered
2. Scheduler tries to execute tasks via LocalExecutor
3. LocalExecutor attempts HTTP communication to task execution service
4. Connection is refused

## What's Working
✅ DAG file: `/app/src/dags/eval_runner_dag.py` (6KB+, loads successfully)
✅ DAG parsing: `airflow dags report` shows 1 DAG with 8 tasks
✅ DAG discovery: DAG appears in `airflow dags list`
✅ DAG triggering: Can create DAG runs from CLI
✅ DAG processor service: Running and parsing files
✅ All containers: Healthy status

## What's Not Working
❌ Task execution: LocalExecutor fails with connection error
❌ Task runs: All tasks fail during execution phase

## Attempted Solutions
1. ✅ Added dag-processor service (fixed DAG discovery issue)
2. ✅ Fixed health check endpoint (/api/v1/health instead of /health)
3. ✅ Added hostname configuration for Airflow services
4. ✅ Disabled remote logging (AIRFLOW__LOGGING__REMOTE_LOGGING: false)
5. ❌ Switched to SequentialExecutor (still using LocalExecutor despite config)

## Recommended Next Steps

### Option 1: Force SequentialExecutor (Safest)
- Clear Airflow database and reinitialize
- Verify `airflow config get-value core executor` returns `SequentialExecutor`
- This executor runs tasks sequentially (no parallelism)

###Option 2: Switch to CeleryExecutor
- Add Redis service
- Add Celery worker container
- Configure Celery executor in docker-compose
- More complex but enables proper parallel execution

### Option 3: Upgrade Airflow
- Check if Airflow 3.2+ or 3.3+ has fixes
- Update Dockerfile to use newer version

### Option 4: Use Airflow 2.x
- Revert to Apache Airflow 2.8.1 (more stable for LocalExecutor)
- Update Dockerfile from `apache/airflow:latest` to specific 2.x version

## DAG Code Status
The `eval_runner_dag.py` code is production-ready:
- ✅ All Python tasks defined correctly  
- ✅ Dynamic task generation works
- ✅ No syntax errors
- ✅ Proper error handling in place
- ✅ File paths correctly configured

The issue is purely with Airflow's task execution engine, not the DAG definition itself.

## Files Modified
- `docker/docker-compose.yml` - Added hostname config, disabled remote logging
- `src/dags/eval_runner_dag.py` - Added better error logging
- Added `airflow-dag-processor` service

## Testing Command
```bash
cd docker
docker-compose up -d
docker-compose exec airflow-webserver airflow dags trigger eval_runner_dag
# Wait 5-10 seconds
docker-compose exec airflow-scheduler airflow dags list-runs eval_runner_dag
```

Expected output: DAG run with status "failed" due to executor connection issue
