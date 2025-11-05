FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY data /app/data

# Qdrant is provided as a separate service in docker-compose; applications
# will talk to it at the hostname `qdrant` on port 6333. Provide a sensible
# default URL to the app environment so it can connect when running in compose.
ENV QDRANT_URL=http://qdrant:6333
ENV QDRANT_API_KEY=
ENV QDRANT_COLLECTION_NAME=rag_chunks

CMD ["tail", "-f", "/dev/null"]
