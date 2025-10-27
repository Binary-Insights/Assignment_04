import os
from openai import OpenAI
import streamlit as st
from dotenv import load_dotenv

# Load .env if present (optional)
load_dotenv()

# Try Streamlit secrets first, then environment
OPENAI_API_KEY = None
try:
    OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
except Exception:
    OPENAI_API_KEY = None

if not OPENAI_API_KEY:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    st.error("OpenAI API key not found. Set OPENAI_API_KEY as an env var or in Streamlit secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)


st.set_page_config(page_title="Simple ChatBot", page_icon="🤖")
st.title("Simple Streamlit ChatBot (OpenAI)")

# Sidebar settings must be declared before interactive widgets (forms)
st.sidebar.header("Settings")
# Model/temperature controls (used when sending messages)
model = st.sidebar.selectbox("Model", ["gpt-4o"], index=0)
temp = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7)

st.sidebar.markdown("---")
st.sidebar.markdown("Set your OpenAI API key via `OPENAI_API_KEY` environment variable or Streamlit secrets.")


if "messages" not in st.session_state:
    # Start with a system prompt to guide assistant
    st.session_state.messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]


def send_message(user_text: str, model: str, temperature: float):
    if not user_text:
        return
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.spinner("Thinking..."):
        try:
            # Use OpenAI v1 client
            resp = client.chat.completions.create(
                model=model,
                messages=st.session_state.messages,
                temperature=temperature,
                max_tokens=512,
            )
            # resp.choices[0].message.content contains the assistant reply
            assistant_message = resp.choices[0].message.content.strip()
        except Exception as e:
            assistant_message = f"[Error] {e}"
    st.session_state.messages.append({"role": "assistant", "content": assistant_message})


with st.form(key="chat_form", clear_on_submit=True):
    user_input = st.text_input("You:")
    submit = st.form_submit_button("Send")
    if submit:
        # read model/temperature from sidebar controls
        send_message(user_input, model, temp)


for msg in st.session_state.messages:
    if msg["role"] == "system":
        continue
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    elif msg["role"] == "assistant":
        st.markdown(f"**Assistant:** {msg['content']}")

