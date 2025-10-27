# Docker Setup & Quick Start

This project is containerized and can run with Docker and Docker Compose.

## Prerequisites

- Docker Engine (https://docs.docker.com/get-docker/)
- Docker Compose (included in Docker Desktop)

## Quick Start with Docker Compose (Recommended)

1. Set your OpenAI API key (substitute your real key):
   ```bash
   export OPENAI_API_KEY="sk-..."
   # or on Windows PowerShell:
   $env:OPENAI_API_KEY = "sk-..."
   ```

2. Start both FastAPI and Streamlit:
   ```bash
   docker compose up
   ```
   This builds the image and starts the container.

3. Access the services:
   - FastAPI: http://localhost:8000/
   - Streamlit: http://localhost:8501/
   - Redirect to Streamlit from FastAPI: http://localhost:8000/streamlit

4. Stop services:
   ```bash
   docker compose down
   ```

## Build and Run Manually

Build the Docker image:
```bash
docker build -t assignment-04:latest .
```

Run the container:
```bash
docker run -it -p 8000:8000 -p 8501:8501 \
  -e OPENAI_API_KEY="sk-..." \
  -v $(pwd):/app \
  assignment-04:latest
```

(Use `${PWD}` on Linux/WSL; on Windows PowerShell use `${pwd}`)

## Environment Variables

Set these in your shell or `.env` file before running:

- `OPENAI_API_KEY` — Your OpenAI API key (required for Streamlit chatbot).

## Notes

- The `docker-compose.yml` mounts the current directory at `/app` for live code reload during development. Remove or comment out the `volumes` section for production.
- The container runs both FastAPI (port 8000) and Streamlit (port 8501) using `run_services.py`.
- The multi-stage Dockerfile keeps the final image lean (only runtime dependencies, no build tools).
- Logs from both services are visible in your terminal when running `docker compose up`.

## Production Considerations

- Use secrets management (Docker Secrets, HashiCorp Vault) instead of environment variables for sensitive data.
- Consider using a reverse proxy (NGINX, Traefik) in front of the container.
- Run with `--reload false` and `--server.runOnSave=false` for Streamlit in production.
- Set resource limits in `docker-compose.yml` (e.g., `mem_limit`, `cpus`).
