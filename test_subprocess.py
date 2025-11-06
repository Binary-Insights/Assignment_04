#!/usr/bin/env python3
"""Test subprocess issue with llm_page_finder"""
import subprocess
import sys
from pathlib import Path
import time

project_root = Path(__file__).resolve().parent

# Test 1: Run llm_page_finder directly
print("=" * 60)
print("TEST 1: Running llm_page_finder.py DIRECTLY")
print("=" * 60)
start = time.time()
result = subprocess.run(
    [sys.executable, "-u", "src/discover/llm_page_finder.py", 
     "--website", "https://worldlabs.ai/",
     "--page-type", "product",
     "--no-structured"],
    cwd=str(project_root),
    timeout=15
)
elapsed = time.time() - start
print(f"\nReturn code: {result.returncode}")
print(f"Time: {elapsed:.1f} seconds")

print("\n" + "=" * 60)
print("TEST 2: Running via subprocess.run with capture_output")
print("=" * 60)
start = time.time()
try:
    result = subprocess.run(
        [sys.executable, "-u", "src/discover/llm_page_finder.py",
         "--website", "https://worldlabs.ai/",
         "--page-type", "careers",
         "--no-structured"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15
    )
    elapsed = time.time() - start
    print(f"Return code: {result.returncode}")
    print(f"Time: {elapsed:.1f} seconds")
    print(f"Stdout length: {len(result.stdout)} chars")
    print(f"Stderr length: {len(result.stderr)} chars")
    if result.stdout:
        print(f"\nStdout (last 300 chars):\n{result.stdout[-300:]}")
except subprocess.TimeoutExpired as e:
    elapsed = time.time() - start
    print(f"TIMEOUT after {elapsed:.1f} seconds!")
except Exception as e:
    print(f"ERROR: {e}")
