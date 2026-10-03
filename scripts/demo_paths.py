"""See every path of the graph without calling a real LLM.
A fake model replays scripted replies, so each run is predictable.
Needs the three MCP servers running."""
import asyncio
import subprocess
import sys

from langchain_core.language_models.fake_chat_models import FakeListChatModel

import agent

TOKEN = subprocess.check_output([sys.executable, "scripts/login.py", "riya"], text=True).strip()

SCENARIOS = [
    ("1. Grounded answer",
     "leave policy", TOKEN,
     ["Employees get 24 days of paid leave. [Employee Handbook > Leave policy]", "SUPPORTED"]),
    ("2. Guessed number -> retry -> safe",
     "What does Neha earn?", TOKEN,
     ["Neha earns about 26 lakh.", "I don't have that information.", "SUPPORTED"]),
    ("3. Unsupported twice -> refuse",
     "Is Dev on a PIP?", TOKEN,
     ["Dev is probably underperforming.", "UNSUPPORTED", "Dev might be on a plan.", "UNSUPPORTED"]),
    ("4. Bad token -> nothing retrieved -> refuse",
     "salaries", "garbage", ["unused"]),
]


async def main():
    for name, question, token, replies in SCENARIOS:
        agent.llm = FakeListChatModel(responses=replies)
        r = await agent.graph.ainvoke({"token": token, "question": question})
        print(f"\n{name}\n  Q: {question}\n  A: {r['answer']}\n  Path: {' -> '.join(r['trace'])}")
        if r.get("reason"):
            print(f"  Checker: {r['verdict']} ({r['reason']})")


asyncio.run(main())