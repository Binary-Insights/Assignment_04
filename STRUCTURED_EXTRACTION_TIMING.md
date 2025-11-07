# Structured Extraction Timing Analysis

## Results

**Tested on:** world_labs company  
**Actual Runtime:** 39.9 minutes (2,393.9 seconds)

## Timeline Breakdown

```
Total: 39.9 minutes

Phase 1: Setup & Loading (0-1 min)
├─ Load metadata & pages: 12 sec
├─ Initialize OpenAI client: 12 sec
└─ Connect to Qdrant: 1 sec

Phase 2: Indexing to Qdrant (1-22 min)
├─ Process 6 page types
├─ Create 91 chunks
├─ Index to Qdrant: ~20 min
└─ Completed: 2025-11-06 23:18:21

Phase 3: LLM Extraction (22-40 min)
├─ Company info: ~3 sec (LLM call)
├─ Events: ~4 sec (LLM call)
├─ Snapshots: ~3 sec (LLM call)
├─ Products: ~2 sec (LLM call)
├─ Leadership: ~2 sec (LLM call)
└─ Visibility: ~1 sec (LLM call)

Phase 4: Save Results (<1 sec)
└─ Write JSON files
```

## What's Taking Time?

### Fast (~1-3 sec each):
- ✅ LLM API calls (instructor + OpenAI)
- ✅ Validation & schema enforcement
- ✅ File I/O

### Slow (~20 min):
- 🐢 Indexing chunks to Qdrant
  - 91 chunks × embedding generation
  - Network I/O to Qdrant server
  - Vector storage operations

## Scaling Calculations

| Scenario | Time | Notes |
|----------|------|-------|
| Single company | 40 min | Measured (world_labs) |
| 5 companies | ~200 min (3.3 hrs) | Sequential |
| 10 companies | ~400 min (6.7 hrs) | Sequential |
| 50 companies | ~2000 min (33 hrs) | Sequential |

## Optimization Strategies

### ✅ Current Setup (No code changes needed)
```bash
# Run 5 companies overnight
python run_all_structured.py --limit 5

# Or run 50 in batches:
python run_all_structured.py --start-index 0 --limit 10   # Run 1
python run_all_structured.py --start-index 10 --limit 10  # Run 2 (next day)
python run_all_structured.py --start-index 20 --limit 10  # Run 3
# ... etc
```

### 🚀 Fast Solution (Airflow - Parallel Execution)
```bash
# In Airflow DAG: run_all_structured_parallel_dag.py
# Uses Python multiprocessing to run 5-10 companies in parallel
# Reduces 33 hours → 4-7 hours
```

### ⚡ Advanced Solution (Code optimization)
1. **Cache LLM responses** - Store results, reuse for similar queries
2. **Batch LLM calls** - Send multiple extraction requests together
3. **Use faster embeddings** - Switch from text-embedding-3-small to text-embedding-3-large
4. **Local embeddings** - Use HuggingFace instead of OpenAI (no API calls)

## Current Timeout Settings

✅ **Updated:** 60 minutes per company (3600 seconds)
- Includes 50% safety buffer over actual 40-minute runtime
- Should handle occasional API latency spikes

## Recommended Approach for Lab 9

For comparing RAG vs Structured on 5 companies (as per requirements):

```bash
# Option 1: Run 5 companies (takes ~200 minutes = 3.3 hours)
python run_all_structured.py --limit 5 --verbose

# Option 2: Run 5 specific companies
python run_all_structured.py --limit 5 --verbose

# Option 3: Use existing data if already processed
# Check which files exist in data/structured/
ls -la data/structured/*.json | wc -l
```

## For Full 50-Company Processing

Recommend using Airflow DAG with parallel execution:
```bash
# Creates parallel tasks for batches of 10 companies
# Reduces total time from 33 hours → ~4 hours
```

---

**Last Updated:** 2025-11-06  
**Benchmark:** world_labs (40 min)
