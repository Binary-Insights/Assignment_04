from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI()

BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "src"

if not STATIC_DIR.exists():
    raise RuntimeError(f"Static directory not found: {STATIC_DIR}")

# Mount the entire `src` directory at /static so assets can be reached if needed.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Return the `index.html` file from the `src` directory."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return FileResponse(str(index_path))
    return FileResponse(str(index_path))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # Run with: uvicorn main:app --reload --port 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
