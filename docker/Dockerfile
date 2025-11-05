# ===============================================
#   Dockerfile for Forbes AI50 Dashboard + Airflow
#   with Qdrant Vector Database Integration
#   FastAPI + Streamlit + Airflow Orchestration
# ===============================================
FROM apache/airflow:2.10.4-python3.11

# Switch to root to install system dependencies
USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PYTHONPATH="/opt/airflow/workspace"

# Install system dependencies including Chrome and Selenium support
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    gnupg \
    unzip \
    ca-certificates \
    # Chrome dependencies
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome Browser
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Switch to airflow user
USER airflow
ENV PATH="/root/.cargo/bin:$PATH"

# ----------------------------
# Airflow core + Amazon provider
# ----------------------------
ARG AIRFLOW_VERSION=2.10.4
ARG PYTHON_VERSION=3.11
ARG CONSTRAINTS_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.11.txt"

RUN python -m pip install --upgrade pip setuptools wheel \
 && uv pip install -c ${CONSTRAINTS_URL} \
    apache-airflow==2.10.4 \
    apache-airflow-providers-amazon

# ----------------------------
# AWS SDKs and utilities
# ----------------------------
RUN uv pip install \
    "boto3>=1.40.58" \
    "awscli>=1.32,<2"

# ----------------------------
# Web scraping and data processing
# ----------------------------
RUN uv pip install \
    "requests==2.32.3" \
    "beautifulsoup4==4.12.2" \
    "html2text==2024.2.26" \
    "lxml==5.3.0" \
    "selenium>=4.38.0"

# ----------------------------
# Web frameworks (FastAPI + Streamlit)
# ----------------------------
RUN uv pip install \
    "fastapi>=0.119.1" \
    "uvicorn>=0.38.0" \
    "streamlit>=1.50.0"

# ----------------------------
# Data validation and utilities
# ----------------------------
RUN uv pip install \
    "pydantic>=2.6.0" \
    "python-dotenv>=1.1.1"

# ----------------------------
# LLM and AI/ML stack
# ----------------------------
RUN uv pip install \
    "langchain>=1.0.2" \
    "langchain-openai>=1.0.1" \
    "langchain-anthropic>=0.3.0" \
    "instructor>=1.11.3"

# ----------------------------
# Vector database (Qdrant)
# ----------------------------
RUN uv pip install \
    "qdrant-client>=2.7.0"

# ----------------------------
# Workspace structure
# ----------------------------
ENV PYTHONPATH="/opt/airflow/workspace" \
    QDRANT_URL=http://qdrant:6333 \
    QDRANT_API_KEY="" \
    QDRANT_COLLECTION_NAME=rag_chunks

# Copy all workspace files (DAGs, src/, scripts/, data/, etc.)
COPY . /opt/airflow/workspace

# Setup chromedriver for Selenium (if needed)
RUN mkdir -p /opt/airflow/workspace/chromedriver && \
    chmod +x /opt/airflow/workspace/chromedriver/linux64/chromedriver 2>/dev/null || true && \
    ln -s /opt/airflow/workspace/chromedriver/linux64/chromedriver /usr/local/bin/chromedriver 2>/dev/null || true

# Expose ports
# 8080: Airflow Webserver
# 8000: FastAPI Backend
# 8501: Streamlit Frontend
# 6333: Qdrant Vector DB
EXPOSE 8080 8000 8501 6333

# Set working directory
WORKDIR /opt/airflow/workspace
