Simple Streamlit ChatBot using OpenAI

This repository includes a minimal Streamlit chat app that uses the OpenAI ChatCompletion API.

Files added:
- `streamlit_chat.py` — Streamlit app (run with `streamlit run streamlit_chat.py`).
- `requirements.txt` — dependencies to install in a virtual environment.

Setup (Windows PowerShell):

```powershell
# create venv with python 3.11 explicitly (if needed)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Set your OpenAI API key in an environment variable:

```powershell
setx OPENAI_API_KEY "sk-..."  # persistent for new shells; or use $env:OPENAI_API_KEY in current session
$env:OPENAI_API_KEY = "sk-..." # for current PowerShell session only
```

Run the Streamlit app:

```powershell
streamlit run streamlit_chat.py
```

Notes:
- The app expects `OPENAI_API_KEY` either in environment variables or in Streamlit secrets.
- On Windows, `uvloop` is not supported — this doesn't affect Streamlit-based usage.
# Updated
