# Phase 9 Visual Implementation Guide

## 🎯 Three Strategies at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                   FALLBACK STRATEGY ENFORCEMENT                 │
└─────────────────────────────────────────────────────────────────┘

STRATEGY 1: qdrant_first (DEFAULT - ⭐ RECOMMENDED)
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   START                                                        │
│     │                                                         │
│     ├─→ TRY: Qdrant Semantic Search 🔍                       │
│     │                                                         │
│     ├─→ SUCCESS? 📊                                          │
│     │   ├─ YES → Use Qdrant Context                          │
│     │   │        Extract with targeted results               │
│     │   │        ✓ Complete successfully                     │
│     │   │                                                   │
│     │   └─ NO → ⚠️ Fallback to Raw Text                    │
│     │          Extract with full text context              │
│     │          ✓ Complete successfully                    │
│     │                                                     │
│     └─→ RESULT: ✅ Always Succeeds                        │
│                                                           │
│   USE WHEN: Production deployments (best effort)         │
│   LATENCY: Variable (Qdrant + fallback time if needed)   │
│   QUALITY: High (semantic when possible)                 │
│                                                           │
└────────────────────────────────────────────────────────────────┘

STRATEGY 2: qdrant_only (STRICT - ⭐ FOR VALIDATION)
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   START                                                        │
│     │                                                         │
│     ├─→ TRY: Qdrant Semantic Search 🔍                       │
│     │                                                         │
│     ├─→ SUCCESS? 📊                                          │
│     │   ├─ YES → Use Qdrant Context                          │
│     │   │        Extract with targeted results               │
│     │   │        ✓ Complete successfully                     │
│     │   │                                                   │
│     │   └─ NO → ❌ ABORT                                   │
│     │          Fail with error message                     │
│     │          ✗ Extraction aborted                       │
│     │                                                     │
│     └─→ RESULT: ✅ or ❌ (no middle ground)              │
│                                                           │
│   USE WHEN: Validation & testing (strict requirements)   │
│   LATENCY: Fast (but fails fast if no results)          │
│   QUALITY: High (semantic search only)                   │
│                                                           │
└────────────────────────────────────────────────────────────────┘

STRATEGY 3: raw_only (BASELINE - ⭐ FOR DEBUGGING)
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   START                                                        │
│     │                                                         │
│     ├─→ SKIP: Qdrant Entirely ⚙️                             │
│     │   (No Qdrant dependency)                              │
│     │                                                         │
│     ├─→ USE: Raw Text Context                               │
│     │   Load full text from pages_text dict                 │
│     │                                                         │
│     └─→ RESULT: ✅ Always Succeeds                         │
│                                                              │
│   USE WHEN: Debugging, comparison, rapid iteration       │
│   LATENCY: Fast (no Qdrant overhead)                       │
│   QUALITY: Medium (full text, less targeted)              │
│                                                            │
└────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Execution Flow Comparison

```
SCENARIO 1: Qdrant is Available & Has Results
═════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────┐
│                     qdrant_first                         │
├─────────────────────────────────────────────────────────┤
│ 🔍 Search Qdrant                                        │
│ 🎯 Found 3 results (similarity: 0.92, 0.88, 0.85)     │
│ 📊 Using Qdrant context for extraction                 │
│ ✅ Extraction succeeded with targeted data              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    qdrant_only                          │
├─────────────────────────────────────────────────────────┤
│ 🔍 Search Qdrant                                        │
│ 🎯 Found 3 results (similarity: 0.92, 0.88, 0.85)     │
│ 📊 Using Qdrant context for extraction                 │
│ ✅ Extraction succeeded with targeted data              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                     raw_only                            │
├─────────────────────────────────────────────────────────┤
│ ⚙️  Strategy 'raw_only' - skipping Qdrant search        │
│ 📝 Loading raw text context                             │
│ ✅ Extraction succeeded with full text                  │
└─────────────────────────────────────────────────────────┘


SCENARIO 2: Qdrant Unavailable or No Results
═════════════════════════════════════════════

┌─────────────────────────────────────────────────────────┐
│                     qdrant_first                         │
├─────────────────────────────────────────────────────────┤
│ 🔍 Search Qdrant                                        │
│ ❌ No results found (timeout or unavailable)           │
│ ⚠️  Fallback: Using raw text instead                    │
│ ✅ Extraction succeeded with fallback                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    qdrant_only                          │
├─────────────────────────────────────────────────────────┤
│ 🔍 Search Qdrant                                        │
│ ❌ No results found (timeout or unavailable)           │
│ ❌ Strategy 'qdrant_only': ABORTING                     │
│ ✗ Extraction FAILED - no fallback allowed               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                     raw_only                            │
├─────────────────────────────────────────────────────────┤
│ ⚙️  Strategy 'raw_only' - skipping Qdrant search        │
│ 📝 Loading raw text context                             │
│ ✅ Extraction succeeded with full text                  │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Decision Matrix

```
┌──────────────────────────────────────────────────────────────────┐
│  Choose Your Strategy Based on Your Needs                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Need Semantic Search Quality?                                  │
│  ├─ YES → Use qdrant_first (default) or qdrant_only            │
│  └─ NO  → Use raw_only for pure LLM testing                    │
│                                                                  │
│  Can Tolerate Fallback?                                         │
│  ├─ YES → Use qdrant_first (production)                        │
│  ├─ NO  → Use qdrant_only (strict)                             │
│  └─ SKIP QDRANT → Use raw_only (baseline)                      │
│                                                                  │
│  Need to Validate Qdrant?                                      │
│  ├─ YES → Use qdrant_only (will fail if not working)          │
│  └─ NO  → Use qdrant_first (auto-handles failures)            │
│                                                                  │
│  Production or Testing?                                         │
│  ├─ PRODUCTION → Use qdrant_first (recommended)               │
│  ├─ VALIDATION → Use qdrant_only (strict)                     │
│  └─ DEBUGGING  → Use raw_only (baseline)                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Code Implementation Pattern

```python
# All 6 extraction functions follow this pattern:

def extract_[TYPE](...) -> [Result]:
    """Extract [TYPE] with fallback strategy enforcement."""
    
    global FALLBACK_STRATEGY
    
    # 1. DETERMINE STRATEGY
    if FALLBACK_STRATEGY == 'raw_only':
        # Strategy: Skip Qdrant entirely
        logger.info(f"⚙️  Strategy 'raw_only' - skipping Qdrant")
        context_text = raw_text_data
    
    else:
        # Strategy: Try Qdrant first
        
        # 2. ATTEMPT QDRANT SEARCH
        context_docs = []
        for query in search_queries:
            docs = search_qdrant_for_context(...)
            context_docs.extend(docs)
        
        # 3. EVALUATE RESULTS
        if context_docs:
            # Success case
            logger.info("📊 Using Qdrant context")
            context_text = build_context(context_docs)
        
        elif FALLBACK_STRATEGY == 'qdrant_only':
            # Strict failure case
            logger.error("❌ Strategy 'qdrant_only' - ABORTING")
            raise ValueError("No Qdrant context available")
        
        else:  # qdrant_first
            # Graceful fallback case
            logger.warning("⚠️  Fallback to raw text")
            context_text = raw_text_data
    
    # 4. CONTINUE EXTRACTION
    result = llm.extract(context_text)
    return result
```

---

## 📈 Performance & Quality Comparison

```
┌────────────────────────────────────────────────────────────────┐
│                      QDRANT AVAILABLE                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Strategy         Speed      Quality   Qdrant   Fallback      │
│ ─────────────    ──────     ────────  ───────  ────────      │
│ qdrant_first     🟢 Fast    🟢 High   ✓ Used   ✗ Unused     │
│ qdrant_only      🟢 Fast    🟢 High   ✓ Used   ✗ Unused     │
│ raw_only         🟡 Slow    🟠 Med    ✗ Skip   ✓ Always     │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                   QDRANT UNAVAILABLE                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Strategy         Speed      Quality   Qdrant   Fallback      │
│ ─────────────    ──────     ────────  ───────  ────────      │
│ qdrant_first     🟡 Slow    🟠 Med    ✗ Fail   ✓ Active     │
│ qdrant_only      🔴 FAIL    ✗ NONE    ✗ Fail   ✗ None      │
│ raw_only         🟢 Fast    🟠 Med    ✗ Skip   ✓ Always     │
│                                                                │
└────────────────────────────────────────────────────────────────┘

Legend:
🟢 Good  |  🟡 OK  |  🟠 Medium  |  🔴 Bad/Fail
```

---

## 🎯 Real-World Examples

### Example 1: Production Setup (qdrant_first)

```bash
$ python scripts/rag/structured_extraction.py \
    --company-slug world_labs

Fallback strategy: qdrant_first
...
🔍 Searching Qdrant: "company overview mission vision"
🎯 Found 3 results with scores: 0.923, 0.891, 0.876
📊 Using Qdrant context for company extraction
✓ Successfully extracted company: World Labs
✓ Saved to: data/structured/world-labs.json
```

### Example 2: Validation Mode (qdrant_only)

```bash
$ python scripts/rag/structured_extraction.py \
    --company-slug world_labs \
    --fallback-strategy qdrant_only

Fallback strategy: qdrant_only
...
🔍 Searching Qdrant: "company overview mission vision"
❌ Qdrant connection failed
❌ Strategy 'qdrant_only': No Qdrant results - ABORTING

Error: No Qdrant context available and 'qdrant_only' strategy selected
→ This tells us Qdrant is not working!
```

### Example 3: Baseline Mode (raw_only)

```bash
$ python scripts/rag/structured_extraction.py \
    --company-slug world_labs \
    --fallback-strategy raw_only

Fallback strategy: raw_only
...
⚙️  Strategy 'raw_only' - skipping Qdrant for company
📝 Loading raw text context (3000 chars)
✓ Successfully extracted company: World Labs
✓ Saved to: data/structured/world-labs.json
→ No Qdrant overhead, pure LLM extraction
```

---

## 🔗 Integration Points

```
┌──────────────────────────────────────────────────────────┐
│                   main() function                         │
│                                                          │
│  1. Parse arguments                                      │
│     └─ Get: --fallback-strategy (or use default)        │
│                                                          │
│  2. Set global FALLBACK_STRATEGY                         │
│     └─ This controls all 6 extraction functions         │
│                                                          │
│  3. Call extraction functions                            │
│     ├─ extract_company_info()     ← Uses global         │
│     ├─ extract_events()            ← Uses global        │
│     ├─ extract_snapshots()         ← Uses global        │
│     ├─ extract_products()          ← Uses global        │
│     ├─ extract_leadership()        ← Uses global        │
│     └─ extract_visibility()        ← Uses global        │
│                                                          │
│  4. Each function checks FALLBACK_STRATEGY               │
│     ├─ 'raw_only'   → Skip Qdrant                       │
│     ├─ 'qdrant_only'→ Fail if no results               │
│     └─ 'qdrant_first'→ Fallback to raw                 │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## ✨ Summary

**Three Strategies, One Parameter**

| Command | Strategy | Best For | Behavior |
|---------|----------|----------|----------|
| `--fallback-strategy qdrant_first` | Production | ⭐ Default | Try Qdrant, fallback to raw |
| `--fallback-strategy qdrant_only` | Validation | Strict | Fail if no Qdrant results |
| `--fallback-strategy raw_only` | Debugging | Baseline | Skip Qdrant, use raw text |

**Logging Indicators**
- 🔍 = Qdrant search initiated
- 🎯 = Results ranked by similarity
- 📊 = Using Qdrant context
- ⚠️ = Falling back to raw text
- ⚙️ = Strategy-driven action
- ❌ = Error/failure
- ✅ = Success

**All 6 Functions Updated**
- Each enforces the selected strategy
- Each logs appropriately
- Each handles errors for that strategy

---

**Visual Guide v1.0** | **Status: ✅ Complete**
