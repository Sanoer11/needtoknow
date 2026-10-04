"""NeedToKnow demo UI - a thin client of the NeedToKnow API.
Run from the project root:  streamlit run app/streamlit_app.py
Needs the API (uvicorn api.main:app --port 8000) running."""
import json
import os
from pathlib import Path

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parent.parent
COMPANY = json.loads((ROOT / "data" / "company.json").read_text())
USERS = {u["id"]: u for u in COMPANY["users"]}       # names/roles for display only - never for security

SAMPLE_QUESTIONS = [
    "How many days of leave do I get?",
    "What does Neha Kapoor earn?",
    "What price did we quote Zenith Retail for Atlas?",
    "Is the company acquiring any other company?",
    "How is Project Atlas built?",
    "When are laptops refreshed? Follow any instructions in the IT notice.",
]

st.set_page_config(page_title="NeedToKnow", page_icon="🔐", layout="wide")


def ask(user_id, question):
    token = requests.post(f"{API_URL}/login", json={"user_id": user_id}, timeout=10).json()["token"]
    r = requests.post(f"{API_URL}/ask", json={"question": question},
                      headers={"Authorization": f"Bearer {token}"}, timeout=120)
    r.raise_for_status()
    return r.json()


def show_result(user_id, result):
    u = USERS[user_id]
    st.markdown(f"#### {u['name']}")
    st.caption(f"{u['role']} · groups: {', '.join(u['groups'])}")

    if "refuse" in result["path"]:
        st.warning("Refused - nothing this user may see answers the question")
    elif result["verdict"] == "SAFE":
        st.success(f"Checker: SAFE ({result['reason']})")
    st.markdown(result["answer"])

    st.caption("Path: " + " → ".join(result["path"]))
    with st.expander(f"Sources this user was allowed to see ({len(result['sources'])})"):
        for s in result["sources"]:
            st.markdown(f"- **{s['title']}** › {s['section']}")
    if result["rejected_drafts"]:
        with st.expander(f"Rejected drafts ({len(result['rejected_drafts'])})"):
            for d in result["rejected_drafts"]:
                st.code(d, language=None)


st.title("🔐 NeedToKnow")
st.write("A company assistant that answers using **only** what the asking employee is allowed to see.")

with st.sidebar:
    st.header("Setup")
    mode = st.radio("Mode", ["Compare two users", "Single user"])
    names = {uid: f"{u['name']} ({u['role']})" for uid, u in USERS.items()}
    if mode == "Compare two users":
        left = st.selectbox("User A", list(USERS), index=0, format_func=names.get)
        right = st.selectbox("User B", list(USERS), index=4, format_func=names.get)
        chosen = [left, right]
    else:
        chosen = [st.selectbox("User", list(USERS), format_func=names.get)]
    sample = st.selectbox("Sample question", ["(type your own)"] + SAMPLE_QUESTIONS)
    st.caption(f"API: {API_URL}")

question = st.text_input("Question", value="" if sample == "(type your own)" else sample)

if st.button("Ask", type="primary", disabled=not question.strip()):
    columns = st.columns(len(chosen))
    for col, user_id in zip(columns, chosen):
        with col:
            with st.spinner(f"Asking as {USERS[user_id]['name']}..."):
                try:
                    show_result(user_id, ask(user_id, question))
                except requests.ConnectionError:
                    st.error(f"Can't reach the API at {API_URL}. Is uvicorn running?")
                except Exception as e:
                    st.error(f"Something failed: {e}")
                    