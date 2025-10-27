from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import uvicorn
import subprocess
import sys
from typing import Optional

app = FastAPI()

BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR 

if not STATIC_DIR.exists():
    raise RuntimeError(f"Static directory not found: {STATIC_DIR}")

# Mount the entire `src` directory at /static so assets can be reached if needed.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# We'll optionally launch the Streamlit app as a subprocess when FastAPI starts.
# The Streamlit app is expected at `src/streamlit_chat.py`.
_streamlit_proc: Optional[subprocess.Popen] = None


@app.on_event("startup")
async def start_streamlit_subprocess():
    """Start Streamlit in a background subprocess (if the app file exists).

    This uses the same Python interpreter (sys.executable) so Streamlit is launched
    from the same virtualenv where FastAPI runs. It runs headless on port 8501.
    """
    global _streamlit_proc
    streamlit_app = STATIC_DIR / "streamlit_chat.py"
    if streamlit_app.exists():
        try:
            cmd = [sys.executable, "-m", "streamlit", "run", str(streamlit_app), "--server.port", "8501", "--server.headless", "true"]
            # Start Streamlit detached; keep handle so we can terminate on shutdown
            _streamlit_proc = subprocess.Popen(cmd)
        except Exception:
            _streamlit_proc = None


@app.on_event("shutdown")
def stop_streamlit_subprocess():
    """Terminate the Streamlit subprocess if we started one."""
    global _streamlit_proc
    if _streamlit_proc and _streamlit_proc.poll() is None:
        try:
            _streamlit_proc.terminate()
            _streamlit_proc.wait(timeout=5)
        except Exception:
            try:
                _streamlit_proc.kill()
            except Exception:
                pass


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Return the `index.html` file from the `src` directory."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return FileResponse(str(index_path))
    return FileResponse(str(index_path))



@app.get("/streamlit")
async def redirect_to_streamlit():
    """Redirect users to the Streamlit UI (assumes Streamlit runs on localhost:8501)."""
    return RedirectResponse(url="http://127.0.0.1:8501/")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # Run with: uvicorn main:app --reload --port 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
