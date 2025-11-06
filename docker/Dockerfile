FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src /app/src
COPY data /app/data

# Set environment variables
ENV PYTHONPATH=/app
ENV QDRANT_URL=http://qdrant:6333
ENV QDRANT_API_KEY=
ENV QDRANT_COLLECTION_NAME=rag_chunks

# Default command - will be overridden by docker-compose
CMD ["python", "-c", "import time; time.sleep(infinity)"]
