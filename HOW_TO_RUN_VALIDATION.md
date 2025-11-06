# How to Run validate_extraction_sources.py

## Quick Start

### Prerequisites
Before running the validation script, ensure:

```bash
# 1. Qdrant is running
docker ps | grep qdrant

# 2. Structured extraction has been completed
ls -la data/structured/

# 3. Raw data exists
ls -la data/raw/

# 4. Environment variables are set
echo $OPENAI_API_KEY
```

---

## Basic Usage

### Option 1: Run with Defaults
```bash
python scripts/rag/validate_extraction_sources.py
```

**What it does:**
- Scans `data/structured/` for all `.json` files
- Validates each extraction against Qdrant sources
- Compares with raw source files
- Generates validation report

**Output:**
```
QDRANT VALIDATION: world-labs
✓ Collection exists: company_world_labs
  Total points: 45

📊 Sources in Qdrant:
✓ data/raw/world_labs/about/text.txt
    Chunks: 12
    Content matches: 3/3
✓ data/raw/world_labs/blog/text.txt
    Chunks: 18
    Content matches: 3/3

✓ All Qdrant sources verified against raw files

[... more output ...]

VALIDATION SUMMARY
Qdrant Sources: ✓ PASS
Provenance Chain: ✓ PASS
```

---

## Prerequisites - Step by Step

### Step 1: Ensure Qdrant is Running

```bash
# Check if Docker container is running
docker ps | grep qdrant

# If not running, start it
docker-compose -f docker/docker-compose.yml up -d
```

**Expected output:**
```
CONTAINER ID   IMAGE              PORTS
abc123def456   qdrant/qdrant      0.0.0.0:6333->6333/tcp
```

### Step 2: Verify Qdrant Connectivity

```bash
# Test Qdrant health
curl -s http://localhost:6333/health | jq .

# List collections
curl -s http://localhost:6333/collections | jq '.collections[].name'
```

**Expected:**
```json
{
  "status": "ok"
}
company_world_labs
company_anthropic
...
```

### Step 3: Run Structured Extraction First

Before validating, you need structured data:

```bash
# Extract data for a company
python scripts/rag/structured_extraction.py --company-slug world_labs

# This creates: data/structured/world-labs.json
ls -la data/structured/
```

### Step 4: Set Environment Variables

```bash
# Linux/Mac
export QDRANT_URL="http://localhost:6333"
export OPENAI_API_KEY="sk-..."

# Windows PowerShell
$env:QDRANT_URL = "http://localhost:6333"
$env:OPENAI_API_KEY = "sk-..."

# Or create .env file
cat > .env << EOF
QDRANT_URL=http://localhost:6333
OPENAI_API_KEY=sk-...
EOF
```

---

## Full Validation Workflow

### Complete Step-by-Step Process

```bash
# 1. Start Qdrant
docker-compose -f docker/docker-compose.yml up -d
sleep 5

# 2. Extract structured data (if not already done)
python scripts/rag/structured_extraction.py --company-slug world_labs
python scripts/rag/structured_extraction.py --company-slug anthropic

# 3. Run validation
python scripts/rag/validate_extraction_sources.py

# 4. Review the output
```

---

## What the Validation Script Checks

### 1. Qdrant Collection Validation
- ✅ Collection exists for the company
- ✅ All source files are indexed in Qdrant
- ✅ Chunk counts are correct
- ✅ Content from raw files matches Qdrant chunks

**Log output:**
```
QDRANT VALIDATION: world-labs
✓ Collection exists: company_world_labs
  Total points: 45
✓ data/raw/world_labs/about/text.txt
    Chunks: 12
    Content matches: 3/3
```

### 2. Extraction Provenance Validation
- ✅ Company record has provenance data
- ✅ Events have source attribution
- ✅ Snapshots have source attribution
- ✅ Products have source attribution
- ✅ Leadership have source attribution
- ✅ Visibility have source attribution

**Log output:**
```
✓ Company Record (provenance: 5 sources)
  Source: https://worldlabs.ai/about
  Date: 2024-11-05

✓ Events (3 total)
  Event: Series A Funding
    Sources: 2
      - https://worldlabs.ai/blog
```

### 3. Raw vs Qdrant Comparison
- ✅ Raw files exist on disk
- ✅ Qdrant chunks traceable to raw files
- ✅ Content consistency verified

**Log output:**
```
RAW FILES vs QDRANT COMPARISON: world_labs
📄 Raw file: data/raw/world_labs/about/text.txt
   Size: 3450 chars
   Preview: World Labs is an AI...

📊 Qdrant Collection: company_world_labs
   Total chunks: 45

✓ Point 1: Found in about/text.txt
✓ Point 2: Found in blog/text.txt
Verified: 10/10 chunks
```

---

## Interpreting the Output

### Success ✅
```
VALIDATION SUMMARY
Qdrant Sources: ✓ PASS
Provenance Chain: ✓ PASS
```

**Means:**
- All extraction data is traceable to raw sources
- Qdrant indexed all pages correctly
- Provenance chain is intact

### Failures ❌
```
✗ Point 12: Source file missing: data/raw/world_labs/product/text.txt
⚠️  Event 'Series B Funding' has NO provenance!
```

**Means:**
- Source file may have been deleted
- Extraction happened but provenance wasn't recorded
- Need to re-extract or check raw data

---

## Troubleshooting

### Error: "Collection not found"
```
Error validating Qdrant: QdrantException: Not found
```

**Solution:**
```bash
# 1. Ensure Qdrant is running
docker ps | grep qdrant

# 2. Re-create collection by extracting
python scripts/rag/structured_extraction.py --company-slug world_labs

# 3. Try validation again
python scripts/rag/validate_extraction_sources.py
```

### Error: "Structured file not found"
```
Structured file not found: data/structured/world-labs.json
```

**Solution:**
```bash
# 1. Create structured file
python scripts/rag/structured_extraction.py --company-slug world_labs

# 2. Verify it was created
ls -la data/structured/

# 3. Try validation again
python scripts/rag/validate_extraction_sources.py
```

### Error: "No structured files found"
```
No structured files found
```

**Solution:**
```bash
# 1. Extract data for at least one company
python scripts/rag/structured_extraction.py --company-slug world_labs

# 2. Verify directory exists
mkdir -p data/structured

# 3. Try validation again
python scripts/rag/validate_extraction_sources.py
```

### Error: "Qdrant connection refused"
```
Error connecting to Qdrant: Connection refused
```

**Solution:**
```bash
# 1. Check if Qdrant is running
docker ps | grep qdrant

# 2. Start Qdrant if not running
docker-compose -f docker/docker-compose.yml up -d

# 3. Wait for it to be ready
sleep 5

# 4. Try validation again
python scripts/rag/validate_extraction_sources.py
```

---

## Advanced Usage

### Run with Verbose Logging

```bash
# Set Python logging to DEBUG
PYTHONLOGGING=DEBUG python scripts/rag/validate_extraction_sources.py
```

### Validate Specific Company

The script validates ALL extracted files. To validate just one:

```bash
# Option 1: Delete other structured files temporarily
mv data/structured/anthropic.json data/structured/anthropic.json.bak
python scripts/rag/validate_extraction_sources.py
mv data/structured/anthropic.json.bak data/structured/anthropic.json

# Option 2: Modify script to validate only one company
# (See "Customization" section below)
```

---

## Customization

### Modify Script to Validate Specific Company

Edit the `main()` function in `validate_extraction_sources.py`:

```python
def main():
    logger = setup_logging()
    
    # Find structured files to validate
    structured_dir = Path("data/structured")
    if not structured_dir.exists():
        logger.error(f"Structured directory not found: {structured_dir}")
        return
    
    # CUSTOMIZE: Only validate specific company
    structured_files = [Path("data/structured/world-labs.json")]  # ← CHANGE THIS
    
    # ... rest of function unchanged
```

Then run:
```bash
python scripts/rag/validate_extraction_sources.py
```

### Modify Qdrant URL

If your Qdrant is running on a different host:

```bash
# Set environment variable
export QDRANT_URL="http://your-server:6333"

# Or modify .env file
echo "QDRANT_URL=http://your-server:6333" >> .env

# Then run
python scripts/rag/validate_extraction_sources.py
```

---

## Integration with CI/CD

### Run Validation After Extraction

```bash
#!/bin/bash

# Extract
python scripts/rag/structured_extraction.py --company-slug world_labs

# Validate
python scripts/rag/validate_extraction_sources.py

# Check exit code
if [ $? -eq 0 ]; then
    echo "✓ Validation passed"
    exit 0
else
    echo "✗ Validation failed"
    exit 1
fi
```

### Batch Validation

```bash
#!/bin/bash

for company in world_labs anthropic openai; do
    echo "Processing $company..."
    
    # Extract
    python scripts/rag/structured_extraction.py --company-slug $company
    
    # Validate (only this company's file)
    # Can add custom validation logic here
    
    if [ -f "data/structured/$company.json" ]; then
        echo "✓ $company: Success"
    else
        echo "✗ $company: Failed"
    fi
done
```

---

## What Happens During Validation

### Phase 1: Qdrant Collection Check
1. Connect to Qdrant at `http://localhost:6333`
2. Verify collection exists (e.g., `company_world_labs`)
3. Count total chunks indexed
4. Verify all source files are represented

### Phase 2: Chunk Content Verification
1. For each chunk in Qdrant
2. Get the source file path from metadata
3. Load that source file from disk
4. Verify the chunk content exists in the source file

### Phase 3: Provenance Chain Analysis
1. Load structured JSON from `data/structured/`
2. Analyze each extracted field
3. Verify provenance metadata is present
4. Check source URLs and timestamps

### Phase 4: Comparison Report
1. Compare raw file sizes vs Qdrant chunks
2. Verify chunk-to-source mappings
3. Generate summary report

---

## Expected Output Example

```
=======================================================================
QDRANT VALIDATION: world-labs
=======================================================================
✓ Collection exists: company_world_labs
  Total points: 45

📊 Sources in Qdrant:
──────────────────────────────────────────────────────────────────────
✓ data/raw/world_labs/about/text.txt
    Chunks: 12
    Content matches: 3/3
✓ data/raw/world_labs/blog/text.txt
    Chunks: 18
    Content matches: 3/3
✓ data/raw/world_labs/careers/text.txt
    Chunks: 15
    Content matches: 3/3
──────────────────────────────────────────────────────────────────────
✓ All Qdrant sources verified against raw files

=======================================================================
EXTRACTION PROVENANCE VALIDATION
=======================================================================

📋 Provenance Analysis for world-labs:
──────────────────────────────────────────────────────────────────────
✓ Company Record (provenance: 5 sources)
    Source: https://worldlabs.ai/about
    Date: 2024-11-05
    Snippet: World Labs is building...

✓ Events (3 total)
  Event: Series A Funding
    Sources: 2
      - https://worldlabs.ai/blog
✓ Snapshots (5 total)
✓ Products (2 total)
✓ Leadership (8 total)
──────────────────────────────────────────────────────────────────────

=======================================================================
RAW FILES vs QDRANT COMPARISON: world_labs
=======================================================================
📄 Raw file: data/raw/world_labs/about/text.txt
   Size: 3450 chars
   Preview: World Labs is an AI research company...

📊 Qdrant Collection: company_world_labs
   Total chunks: 45

──────────────────────────────────────────────────────────────────────
Verification: Chunks traceable to raw files?
──────────────────────────────────────────────────────────────────────
✓ Point 1: Found in about/text.txt
✓ Point 2: Found in about/text.txt
✓ Point 3: Found in blog/text.txt
✓ Point 4: Found in careers/text.txt
✓ Point 5: Found in about/text.txt
✓ Point 6: Found in blog/text.txt
✓ Point 7: Found in blog/text.txt
✓ Point 8: Found in careers/text.txt
✓ Point 9: Found in blog/text.txt
✓ Point 10: Found in about/text.txt

Verified: 10/10 chunks

=======================================================================
VALIDATION SUMMARY
=======================================================================
Qdrant Sources: ✓ PASS
Provenance Chain: ✓ PASS
=======================================================================
```

---

## Next Steps After Validation

✅ **If Validation Passes:**
- Data extraction is working correctly
- Qdrant is properly indexed
- Provenance chain is intact
- Ready to deploy or analyze results

❌ **If Validation Fails:**
1. Review the error messages
2. Check raw data files exist
3. Re-run extraction
4. Verify Qdrant is running
5. Check logs for details

---

## Quick Reference Commands

```bash
# All in one: Start, Extract, Validate
docker-compose -f docker/docker-compose.yml up -d && \
sleep 5 && \
python scripts/rag/structured_extraction.py --company-slug world_labs && \
python scripts/rag/validate_extraction_sources.py

# Just run validation
python scripts/rag/validate_extraction_sources.py

# Run with specific company only (extract first)
python scripts/rag/structured_extraction.py --company-slug world_labs && \
python scripts/rag/validate_extraction_sources.py

# Check Qdrant is ready
curl -s http://localhost:6333/health | jq .

# List all collections
curl -s http://localhost:6333/collections | jq '.collections'
```

---

**Guide v1.0** | **Status: ✅ Ready to Use**
