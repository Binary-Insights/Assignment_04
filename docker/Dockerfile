FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Airflow with compatible extras and Celery support
RUN pip install --no-cache-dir \
    apache-airflow \
    apache-airflow-providers-postgres \
    apache-airflow-providers-http

# Copy application code
COPY src /app/src
COPY data /app/data

# Create Airflow directories and set permissions
RUN mkdir -p /app/airflow_home && \
    mkdir -p /app/logs && \
    mkdir -p /app/plugins && \
    mkdir -p /app/dags && \
    mkdir -p /app/data && \
    chown -R 50000:50000 /app/airflow_home && \
    chown -R 50000:50000 /app/logs && \
    chown -R 50000:50000 /app/plugins && \
    chown -R 50000:50000 /app/dags && \
    chown -R 50000:50000 /app/data && \
    chmod -R 755 /app/airflow_home && \
    chmod -R 755 /app/logs && \
    chmod -R 755 /app/plugins

# Create airflow user
RUN useradd -m -u 50000 -g 0 airflow || true

# Switch to airflow user
USER 50000:0

# Set environment variables
ENV PYTHONPATH=/app
ENV AIRFLOW_HOME=/app/airflow_home
ENV AIRFLOW__CORE__LOAD_EXAMPLES=false
ENV AIRFLOW__CORE__UNIT_TEST_MODE=false
ENV AIRFLOW__CORE__DAGS_FOLDER=/app/src/dags
ENV AIRFLOW__CORE__LOGS_FOLDER=/app/logs
ENV AIRFLOW__CORE__PLUGINS_FOLDER=/app/plugins
ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor

# Default command - will be overridden by docker-compose
CMD ["python", "-c", "import time; time.sleep(1000000)"]
