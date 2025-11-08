FROM apache/airflow:2.10.4-python3.11

WORKDIR /app

# Install additional system dependencies if needed
USER root
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*
USER airflow

# Install additional Python requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src /app/src
COPY data /app/data

# Set environment variables
ENV PYTHONPATH=/app
ENV AIRFLOW__CORE__LOAD_EXAMPLES=false
ENV AIRFLOW__CORE__UNIT_TEST_MODE=false
ENV AIRFLOW__CORE__DAGS_FOLDER=/app/src/dags
ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor

# Default command - will be overridden by docker-compose
CMD ["airflow", "version"]
