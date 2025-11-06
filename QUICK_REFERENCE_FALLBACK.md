# Quick Reference Card - Fallback Strategy

## TL;DR - Fallback Strategy Control

### Three Ways to Run Extraction

```bash
# DEFAULT: Try Qdrant, fallback to raw if unavailable
python scripts/rag/structured_extraction.py --company-slug world_labs

# STRICT: Fail if Qdrant unavailable
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy qdrant_only

# BASELINE: Skip Qdrant entirely, use raw text only
python scripts/rag/structured_extraction.py --company-slug world_labs --fallback-strategy raw_only
```

---

## What Each Strategy Does

### ✅ `qdrant_first` (DEFAULT)
- **Try:** Qdrant semantic search
- **Fallback:** Use raw text if Qdrant fails
- **Result:** Always completes extraction
- **Best for:** Production 🚀

### ❌ `qdrant_only` (STRICT)
- **Try:** Qdrant semantic search
- **Fallback:** NONE - fails with error
- **Result:** Fails if Qdrant unavailable
- **Best for:** Validation 🔍

### ⚙️ `raw_only` (BASELINE)
- **Try:** Nothing - skip Qdrant entirely
- **Use:** Raw text only
- **Result:** Always completes extraction
- **Best for:** Debugging 🐛

---

## Log Indicators

| Icon | Means | Example |
|------|-------|---------|
| 🔍 | Searching Qdrant | Finding relevant chunks |
| 🎯 | Ranked results | Top matches sorted by similarity |
| ✅ | Success | Operation completed |
| ❌ | Error | Operation failed |
| 📊 | Using Qdrant | Extraction with semantic results |
| ⚠️ | Fallback | Using raw text instead |
| ⚙️ | Strategy choice | Skipping Qdrant due to strategy |

---

## When to Use Each

| Use Case | Strategy | Reason |
|----------|----------|--------|
| Production | `qdrant_first` | Best-effort, graceful degradation |
| Debugging | `raw_only` | Fast, no vector DB needed |
| Validation | `qdrant_only` | Strict, catches Qdrant issues |
| Comparison | `raw_only` vs `qdrant_first` | Quality difference (semantic vs full text) |
| Testing | Any strategy | Test different scenarios |

---

## Expected Output Examples

### Success with qdrant_first
```
✅ Fallback strategy: qdrant_first
📊 Using Qdrant context for company extraction
✓ Successfully extracted company: World Labs
✓ Saved structured data to: data/structured/world-labs.json
```

### Fallback with qdrant_first
```
✅ Fallback strategy: qdrant_first
⚠️  Fallback: Qdrant returned no results for company info, using raw text instead
✓ Successfully extracted company: Test Corp
✓ Saved structured data to: data/structured/test-corp.json
```

### Success with raw_only
```
✅ Fallback strategy: raw_only
⚙️  Strategy 'raw_only' selected - skipping Qdrant search for company info
✓ Successfully extracted company: World Labs
✓ Saved structured data to: data/structured/world-labs.json
```

### Failure with qdrant_only
```
✅ Fallback strategy: qdrant_only
❌ Strategy 'qdrant_only': No Qdrant results for company info - ABORTING
Error: No Qdrant context available and 'qdrant_only' strategy selected
```

---

## Batch Processing

```bash
# Process multiple companies with same strategy
for company in world_labs anthropic openai; do
  python scripts/rag/structured_extraction.py \
    --company-slug $company \
    --fallback-strategy qdrant_first
done

# Or with error handling
for company in $(ls data/raw/); do
  python scripts/rag/structured_extraction.py \
    --company-slug "$company" \
    --fallback-strategy qdrant_first || echo "Failed: $company"
done
```

---

## Troubleshooting

### qdrant_only fails - what to do?
```bash
# Check if Qdrant is running
docker ps | grep qdrant

# Try qdrant_first instead (auto-fallback)
python scripts/rag/structured_extraction.py --company-slug X --fallback-strategy qdrant_first

# Or use raw_only to bypass Qdrant
python scripts/rag/structured_extraction.py --company-slug X --fallback-strategy raw_only
```

### raw_only is slow - what to do?
```bash
# Normal - raw_only uses full text context
# Use qdrant_first for better performance
python scripts/rag/structured_extraction.py --company-slug X --fallback-strategy qdrant_first
```

### Different results between strategies - expected?
```bash
# YES - normal behavior
# qdrant_first: semantic search (more targeted)
# raw_only: full text (complete context)
# Compare outputs - qdrant_first should be higher quality
```

---

## Performance Tiers

| Speed | Strategy | Notes |
|-------|----------|-------|
| 🚀 Fastest | `raw_only` | No Qdrant overhead, more LLM tokens |
| 🔄 Variable | `qdrant_first` | Depends on Qdrant availability |
| ⚠️ May fail | `qdrant_only` | Fast if Qdrant works, instant fail if not |

---

## One-Liners

```bash
# Default (recommended)
python scripts/rag/structured_extraction.py --company-slug COMPANY

# Strict validation
python scripts/rag/structured_extraction.py --company-slug COMPANY --fallback-strategy qdrant_only

# Baseline test
python scripts/rag/structured_extraction.py --company-slug COMPANY --fallback-strategy raw_only

# With verbose logging
python scripts/rag/structured_extraction.py --company-slug COMPANY --verbose

# All at once
python scripts/rag/structured_extraction.py --company-slug COMPANY --fallback-strategy qdrant_first --verbose
```

---

## Output Location

All strategies save to: `data/structured/{company-id}.json`

**Note:** Same output location for all strategies, different quality based on strategy used.

---

## Further Reading

- **Full Implementation Details:** `FALLBACK_STRATEGY_IMPLEMENTATION.md`
- **Testing Guide:** `TESTING_GUIDE_FALLBACK.md`
- **Validation Documentation:** `VALIDATION_GUIDE.md`
- **Phase 9 Summary:** `PHASE_9_COMPLETION_SUMMARY.md`

---

**Quick Reference v1.0**
**Status:** ✅ Ready to Use
