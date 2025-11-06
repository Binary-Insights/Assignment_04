#!/usr/bin/env python3
"""Debug script to test LLM fallback subprocess call."""

import subprocess
import os
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded .env from {env_path}")
    else:
        print(f"✗ .env not found at {env_path}")
except ImportError:
    print("✗ dotenv not installed")

# Check if OPENAI_API_KEY is set
print(f"OPENAI_API_KEY set: {'OPENAI_API_KEY' in os.environ}")
if 'OPENAI_API_KEY' in os.environ:
    api_key = os.environ['OPENAI_API_KEY']
    print(f"  First 20 chars: {api_key[:20]}...")

project_root = Path(__file__).resolve().parent

cmd = [
    "python",
    "src/discover/llm_page_finder.py",
    "--website", "https://worldlabs.ai/",
    "--page-type", "careers",
    "--no-structured"  # Use fallback to avoid complex dependencies
]

print(f"\n[TEST] Running command: {' '.join(cmd)}")
print(f"[TEST] CWD: {project_root}")
print(f"[TEST] Starting subprocess...")

try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
        cwd=str(project_root)
    )
    
    print(f"\n[TEST] Return code: {result.returncode}")
    print(f"\n[TEST] STDOUT ({len(result.stdout)} bytes):")
    print(result.stdout[:1000])
    
    if result.stderr:
        print(f"\n[TEST] STDERR ({len(result.stderr)} bytes):")
        print(result.stderr[:1000])
    
except subprocess.TimeoutExpired:
    print("[TEST] ✗ TIMEOUT after 30 seconds")
except Exception as e:
    print(f"[TEST] ✗ ERROR: {e}")
