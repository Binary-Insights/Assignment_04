# Fallback Strategy Implementation - Phase 9

## Overview

Successfully implemented **fallback strategy enforcement** in `scripts/rag/structured_extraction.py`. The extraction pipeline now supports three runtime-controlled strategies for handling Qdrant vector search failures.

## What Was Implemented

### 1. Helper Functions Added

#### `should_use_fallback()` (NEW)
Determines if fallback to raw text should be used based on the current strategy and context availability.

**Behavior:**
- If context_docs available → return False (no fallback needed)
- If `FALLBACK_STRATEGY == 'qdrant_only'` → log error and return False (will trigger exception in caller)
- If `FALLBACK_STRATEGY == 'raw_only'` → log warning and return True (use raw text)
- If `FALLBACK_STRATEGY == 'qdrant_first'` → log warning and return True (fallback to raw text)

#### `log_extraction_sources()` (ENHANCED)
Updated to provide better source tracking information.

### 2. Fallback Strategy Enum

**Three Strategies Available:**

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `qdrant_only` | Fail if Qdrant unavailable | Strict mode - requires vector search to succeed |
| `raw_only` | Always use raw text, skip Qdrant | Debugging/baseline - pure LLM without semantic search |
| `qdrant_first` | Try Qdrant, fallback to raw | Production (default) - best effort approach |

### 3. Updated Extraction Functions

All 6 extraction functions now implement the strategy enforcement pattern:

#### Pattern Applied:
```python
if FALLBACK_STRATEGY == 'raw_only':
    logger.info(f"⚙️  Strategy 'raw_only' selected - skipping Qdrant search for [TYPE]")
    context_text = json.dumps(pages_text, indent=2)[:3000]
else:
    # Try Qdrant search
    for query in search_queries:
        docs = search_qdrant_for_context(...)
        context_docs.extend(docs)
    
    if context_docs:
        logger.info("📊 Using Qdrant context for [TYPE] extraction")
        context_text = build_context(context_docs)
    elif FALLBACK_STRATEGY == 'qdrant_only':
        logger.error("❌ Strategy 'qdrant_only': No Qdrant results for [TYPE] - ABORTING")
        raise ValueError("No Qdrant context available and 'qdrant_only' strategy selected")
    else:  # qdrant_first
        logger.warning("⚠️  Fallback: Qdrant returned no results for [TYPE], using raw text instead")
        context_text = json.dumps(pages_text, indent=2)[:3000]
```

**Functions Updated:**
1. ✅ `extract_company_info()` - Company info extraction
2. ✅ `extract_events()` - Events/funding rounds extraction
3. ✅ `extract_snapshots()` - Business snapshots extraction
4. ✅ `extract_products()` - Product information extraction
5. ✅ `extract_leadership()` - Leadership team extraction
6. ✅ `extract_visibility()` - Public metrics/visibility extraction

### 4. CLI Argument

Added `--fallback-strategy` argument to main():

```bash
python scripts/rag/structured_extraction.py \
  --company-slug world_labs \
  --fallback-strategy [qdrant_only|raw_only|qdrant_first]
```

**Default:** `qdrant_first` (tries Qdrant, falls back to raw text)

### 5. Logging Icons (Maintained)

Enhanced logging with emoji indicators for clarity:

| Icon | Meaning | Usage |
|------|---------|-------|
| 🔍 | Qdrant search query | When searching for context |
| 🎯 | Ranked search results | When showing top results with similarity |
| ✅ | Successful operation | When Qdrant search succeeds |
| ❌ | Error/failure | When operations fail |
| 📊 | Using Qdrant context | When extraction proceeds with vector results |
| ⚠️ | Fallback scenario | When falling back to raw text |
| ⚙️ | Strategy configuration | When skipping searches due to strategy |

## Execution Examples

### Example 1: Qdrant-First Mode (Default, Production)
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs
```

**Log Output:**
```
Fallback strategy: qdrant_first
...
🔍 Searching Qdrant: "company overview mission vision"
🎯 Ranked results: [5 results with scores 0.923, 0.891, ...]
📊 Using Qdrant context for company info extraction
✓ Successfully extracted company: World Labs
```

### Example 2: Qdrant-Only Mode (Strict, Testing)
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy qdrant_only
```

**Log Output:**
```
Fallback strategy: qdrant_only
...
🔍 Searching Qdrant: "company overview mission vision"
❌ No results found
❌ Strategy 'qdrant_only': No Qdrant results for company info - ABORTING
Error: No Qdrant context available and 'qdrant_only' strategy selected
```

### Example 3: Raw-Only Mode (Baseline, Debugging)
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy raw_only
```

**Log Output:**
```
Fallback strategy: raw_only
...
⚙️  Strategy 'raw_only' selected - skipping Qdrant search for company info
✓ Successfully extracted company: World Labs
```

## Use Cases for Each Strategy

### `qdrant_first` (DEFAULT - Recommended for Production)
**When to use:**
- Production deployments
- When vector search might be intermittently unavailable
- Want best of both worlds: semantic search when possible, graceful degradation

**Behavior:**
- ✅ Attempts Qdrant semantic search
- ✅ Falls back to raw text if Qdrant unavailable
- ✅ Always completes extraction

### `qdrant_only` (Strict Mode - Testing/Validation)
**When to use:**
- Validating vector database quality
- Ensuring Qdrant is always available in your environment
- Testing semantic search quality without fallback
- Debugging Qdrant connectivity issues

**Behavior:**
- ✅ Attempts Qdrant semantic search
- ❌ **FAILS** if no results (doesn't fall back)
- ❌ Does not complete extraction if Qdrant unavailable

### `raw_only` (Baseline - Debugging/Comparison)
**When to use:**
- Baseline comparison (without semantic search)
- Debugging LLM performance
- Rapid iteration when Qdrant isn't relevant
- Testing pure LLM capabilities

**Behavior:**
- ⚙️ Skips Qdrant entirely
- ✅ Uses raw text directly
- ✅ Always completes extraction

## Global Configuration

The fallback strategy is stored in a global variable:

```python
# In structured_extraction.py around line 51
FALLBACK_STRATEGY = 'qdrant_first'  # Can be: 'qdrant_only', 'raw_only', 'qdrant_first'
```

**Updated at runtime by:**
```python
global FALLBACK_STRATEGY
FALLBACK_STRATEGY = args.fallback_strategy
```

Each extraction function accesses this global to determine behavior:
```python
global FALLBACK_STRATEGY

if FALLBACK_STRATEGY == 'raw_only':
    # Skip Qdrant
elif FALLBACK_STRATEGY == 'qdrant_only':
    # Fail if no results
else:  # 'qdrant_first'
    # Try Qdrant, fallback to raw
```

## Testing the Implementation

### Test 1: Verify Qdrant-First Mode
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy qdrant_first
# Expected: Should see 📊 icons if Qdrant works, ⚠️ if it falls back
```

### Test 2: Verify Qdrant-Only Mode
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy qdrant_only
# Expected: Should see 📊 icons if Qdrant works, ❌ error if it doesn't
```

### Test 3: Verify Raw-Only Mode
```bash
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy raw_only
# Expected: Should see ⚙️ icons, skip all Qdrant searches, use raw text directly
```

### Test 4: Batch Processing with Strategy
```bash
# Process multiple companies with strict strategy
for company in $(ls data/raw/); do
  python scripts/rag/structured_extraction.py --company-slug $company --fallback-strategy qdrant_first
done
```

## Files Modified

| File | Changes |
|------|---------|
| `scripts/rag/structured_extraction.py` | Added strategy enforcement to 6 extraction functions + CLI argument |

**Lines Changed:**
- Line ~51: Global `FALLBACK_STRATEGY` variable
- Lines ~278-321: `search_qdrant_for_context()` - added icons
- Lines ~461-502: `extract_company_info()` - added strategy enforcement
- Lines ~540-583: `extract_events()` - added strategy enforcement
- Lines ~640-685: `extract_snapshots()` - added strategy enforcement
- Lines ~735-778: `extract_products()` - added strategy enforcement
- Lines ~828-871: `extract_leadership()` - added strategy enforcement
- Lines ~923-966: `extract_visibility()` - added strategy enforcement
- Lines ~1160-1167: CLI argument parsing for `--fallback-strategy`

## Error Handling

### When `qdrant_only` fails:
```
ValueError: No Qdrant context available and 'qdrant_only' strategy selected
```
- Script exits with error
- Extraction is **NOT** completed
- Useful for detecting Qdrant unavailability

### When `qdrant_first` has no Qdrant results:
```
⚠️  Fallback: Qdrant returned no results for [TYPE], using raw text instead
```
- Script continues gracefully
- Falls back to raw text
- Extraction completes successfully

### When `raw_only` is selected:
```
⚙️  Strategy 'raw_only' selected - skipping Qdrant search for [TYPE]
```
- Qdrant search is skipped entirely
- Raw text used directly
- Fast extraction without vector database

## Performance Implications

| Strategy | Qdrant Calls | LLM Tokens | Latency | Quality |
|----------|--------------|-----------|---------|---------|
| `qdrant_only` | High | Lower (targeted context) | Fast | High (semantic) |
| `raw_only` | None | Higher (full text) | Medium | Medium (full context) |
| `qdrant_first` | High | Lower/Higher | Variable | High (best effort) |

## Next Steps (Optional Enhancements)

1. **Metrics Collection**: Track which strategy is used most frequently
2. **Adaptive Strategy**: Automatically switch strategy based on Qdrant availability
3. **Caching**: Cache Qdrant results to avoid repeated searches
4. **Async Execution**: Make Qdrant search non-blocking for faster fallback

## Troubleshooting

### All Extractions Failing with `qdrant_only`
**Issue:** Strategy set to `qdrant_only` but Qdrant isn't returning results

**Solution:**
1. Verify Qdrant is running: `ps aux | grep qdrant`
2. Check collection exists: `http://localhost:6333/collections`
3. Switch to `qdrant_first` for graceful degradation
4. Check VALIDATION_GUIDE.md for debugging steps

### Extractions Slower with `qdrant_first`
**Issue:** Takes longer due to Qdrant search attempts before fallback

**Solution:**
- Use `raw_only` for speed if semantic search isn't critical
- Optimize Qdrant queries (reduce number of search queries)
- Monitor Qdrant performance metrics

### Missing Information with `raw_only`
**Issue:** Less targeted context means lower quality extractions

**Solution:**
- Only use `raw_only` for testing/comparison
- Use `qdrant_first` (default) for production
- Ensure Qdrant is properly indexed with all company pages

## Summary

✅ **All extraction functions now enforce fallback strategy**
✅ **CLI argument allows runtime strategy selection**
✅ **Comprehensive logging with emoji indicators**
✅ **Three strategies cover all use cases: strict, baseline, and production**
✅ **Graceful error handling for each strategy**

---

**Implementation Date:** Phase 9
**Modified File:** `scripts/rag/structured_extraction.py`
**Total Functions Enhanced:** 6 extraction functions + 1 helper function
**CLI Arguments Added:** 1 (`--fallback-strategy`)
**Status:** ✅ Ready for Testing
