"""Start FastAPI (uvicorn) and Streamlit as separate subprocesses.

This script:
- picks a free port for uvicorn
- waits for FastAPI /health to respond
- then starts Streamlit

Run with the same Python interpreter/venv:

    python run_services.py

"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from typing import List


def start_process(cmd: List[str]) -> subprocess.Popen:
    print("Starting:", " ".join(cmd))
    return subprocess.Popen(cmd)


def terminate(proc: subprocess.Popen, name: str) -> None:
    if proc and proc.poll() is None:
        print(f"Terminating {name} (pid={proc.pid})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            print(f"Killing {name} (pid={proc.pid})")
            proc.kill()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_health(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError):
            pass
        time.sleep(0.2)
    return False


def main() -> None:
    py = sys.executable

    port = find_free_port()
    uvicorn_cmd = [py, "-m", "uvicorn", "src.main:app", "--reload", "--port", str(port)]
    # Decide Streamlit port (prefer 8501, fallback to a free port)
    preferred_streamlit_port = 8501
    if is_port_free(preferred_streamlit_port):
        streamlit_port = preferred_streamlit_port
    else:
        streamlit_port = find_free_port()
        print(f"Port {preferred_streamlit_port} in use, selected free Streamlit port {streamlit_port}")

    streamlit_cmd = [
        py,
        "-m",
        "streamlit",
        "run",
        "src/streamlit_chat.py",
        "--server.port",
        str(streamlit_port),
        "--server.headless",
        "true",
    ]

    uvicorn_proc = start_process(uvicorn_cmd)

    if not wait_for_health(port, timeout=20.0):
        print(f"uvicorn did not become healthy on port {port}; exiting")
        terminate(uvicorn_proc, "uvicorn")
        return

    streamlit_proc = start_process(streamlit_cmd)

    # Wait for Streamlit to become available (root page) with a short timeout
    streamlit_url = f"http://127.0.0.1:{streamlit_port}/"
    streamlit_deadline = time.time() + 15.0
    streamlit_ready = False
    while time.time() < streamlit_deadline:
        try:
            with urllib.request.urlopen(streamlit_url, timeout=1) as resp:
                if resp.status == 200:
                    streamlit_ready = True
                    break
        except Exception:
            pass
        time.sleep(0.25)

    if not streamlit_ready:
        print(f"Streamlit did not start successfully on port {streamlit_port}. Check logs.")
        # terminate both and exit
        terminate(streamlit_proc, "streamlit")
        terminate(uvicorn_proc, "uvicorn")
        return
    else:
        print(f"Streamlit running at {streamlit_url}")

    try:
        while True:
            if uvicorn_proc.poll() is not None:
                print("uvicorn exited with", uvicorn_proc.returncode)
                break
            if streamlit_proc.poll() is not None:
                print("streamlit exited with", streamlit_proc.returncode)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Keyboard interrupt received — shutting down...")
    finally:
        terminate(streamlit_proc, "streamlit")
        terminate(uvicorn_proc, "uvicorn")


if __name__ == "__main__":
    main()
