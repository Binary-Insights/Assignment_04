#!/usr/bin/env bash
# Quick start script for RAG Search API

set -e

echo "🚀 RAG Search API - Quick Start"
echo "================================"
echo ""

# Check dependencies
echo "✓ Checking dependencies..."
python -c "import fastapi; print('  ✓ FastAPI installed')" 2>/dev/null || { echo "  ✗ FastAPI not found"; echo "    Run: pip install fastapi"; exit 1; }
python -c "import uvicorn; print('  ✓ Uvicorn installed')" 2>/dev/null || { echo "  ✗ Uvicorn not found"; echo "    Run: pip install uvicorn"; exit 1; }
python -c "import qdrant_client; print('  ✓ Qdrant client installed')" 2>/dev/null || { echo "  ✗ Qdrant client not found"; echo "    Run: pip install qdrant-client"; exit 1; }
python -c "import pydantic; print('  ✓ Pydantic installed')" 2>/dev/null || { echo "  ✗ Pydantic not found"; echo "    Run: pip install pydantic"; exit 1; }

echo ""
echo "✓ All dependencies installed"
echo ""

# Check Qdrant
echo "✓ Checking Qdrant connection..."
if curl -s http://localhost:6333/health > /dev/null 2>&1; then
    echo "  ✓ Qdrant is running at http://localhost:6333"
else
    echo "  ⚠ Qdrant not found at http://localhost:6333"
    echo "    Starting Qdrant in Docker..."
    docker run -d -p 6333:6333 qdrant/qdrant:v1.12.0 2>/dev/null || true
    sleep 2
fi

echo ""
echo "✓ Starting RAG Search API..."
echo ""

# Start API
cd "$(dirname "$0")/../.."
python scripts/backend/rag_search_api.py
