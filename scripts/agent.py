import asyncio
import os
import re
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

load_dotenv()

SERVERS = {"hr": 8001, "finance": 8002, "wiki": 8003}
MAX_ATTEMPTS = 2
REFUSAL = "I can't find information on that which you have access to."


def get_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"), temperature=0)


llm = None  # created on first use, so tests can swap in a fake model


# ---------------- State: the shared notebook every step reads and writes ----------------

class State(TypedDict, total=False):
    token: str          # the user's ID card - passed to MCP servers, never shown to the LLM
    question: str
    context: list       # chunks this user is allowed to see
    answer: str
    verdict: str        # SAFE | LEAK | UNSURE
    reason: str
    attempts: int
    trace: list         # which steps ran - for debugging and the demo
    drafts: list        # every answer the LLM wrote, including rejected ones


# ---------------- Node 1: retrieve (via the three MCP servers) ----------------

async def search_server(name, port, token, question):
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    try:
        async with Client(streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http)) as client:
            result = await client.call_tool("search", {"question": question})
            return result.structured_content["result"]
    except Exception:
        # refused (bad token) or server not running -> contributes nothing, but say so
        print(f"warning: {name} server refused the request or is not running", file=sys.stderr)
        return []


async def retrieve(state: State) -> State:
    results = await asyncio.gather(*(search_server(n, p, state["token"], state["question"])
                                     for n, p in SERVERS.items()))
    context = [chunk for server_results in results for chunk in server_results]
    context.sort(key=lambda c: c["score"], reverse=True)
    return {"context": context[:6], "attempts": 0, "trace": ["retrieve"]}


# ---------------- Node 2: generate ----------------

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You answer employee questions using ONLY the context below. "
     "If the context does not contain the answer, say you don't have that information. "
     "Never guess, estimate or calculate figures that are not written in the context. "
     "Cite sources as [Title > Section].\n\nContext:\n{context}"),
    ("human", "{question}"),
])

STRICT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Your previous answer included information not found in the context. "
     "Answer again using ONLY sentences that restate the context below, with no inference, "
     "arithmetic or outside knowledge. If unsure, say you don't have that information. "
     "Cite sources as [Title > Section].\n\nContext:\n{context}"),
    ("human", "{question}"),
])


def format_context(context):
    return "\n\n".join(f"[{c['title']} > {c['section']}]\n{c['content']}" for c in context)


async def generate(state: State) -> State:
    prompt = STRICT_PROMPT if state["attempts"] > 0 else ANSWER_PROMPT
    msg = await (prompt | llm).ainvoke({"context": format_context(state["context"]),
                                        "question": state["question"]})
    return {"answer": msg.content, "attempts": state["attempts"] + 1,
            "drafts": state.get("drafts", []) + [msg.content],
            "trace": state["trace"] + [f"generate#{state['attempts'] + 1}"]}


# ---------------- Node 3: leak checker ----------------



NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# NEW: a pure "I don't have that information" answer makes no factual claims.
ABSTENTION = re.compile(r"(i )?(don't|do not) have (that |this |any |the )?information( about [\w\s'.-]{0,60})?\.?")


def normalize(text):                                                   # NEW
    return " ".join(text.lower().replace("\u2019", "'").split())   # curly ’ -> straight ', collapse spaces


JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a strict auditor. Decide whether EVERY factual claim in the ANSWER is directly "
     "stated in the CONTEXT. Claims that are guessed, inferred, calculated or from outside "
     "knowledge are NOT supported. Saying the information is not available, or declining to "
     "answer, is NOT a factual claim and counts as SUPPORTED. Citations are not claims. "
     "Reply with exactly one word: SUPPORTED or UNSUPPORTED."),
    ("human", "CONTEXT:\n{context}\n\nANSWER:\n{answer}"),
])


async def check(state: State) -> State:
    context_text = format_context(state["context"])

    # Check A (deterministic): every number in the answer must appear in the allowed context
    allowed_numbers = {n.replace(",", "") for n in NUMBER.findall(context_text)}
    unknown = [n for n in NUMBER.findall(state["answer"]) if n.replace(",", "") not in allowed_numbers]
    if unknown:
        return {"verdict": "LEAK", "reason": f"numbers not in allowed context: {unknown}",
                "trace": state["trace"] + ["check:LEAK"]}

    # NEW - Check A2 (deterministic): the whole answer is just an abstention -> nothing to verify
    if ABSTENTION.fullmatch(normalize(state["answer"])):
        return {"verdict": "SAFE", "reason": "answer abstains - no claims made",
                "trace": state["trace"] + ["check:SAFE"]}

    # Check B (LLM judge): every claim must be supported by the allowed context
    msg = await (JUDGE_PROMPT | llm).ainvoke({"context": context_text, "answer": state["answer"]})
    word = msg.content.strip().strip("*").upper()   # tolerate **SUPPORTED** formatting
    if word.startswith("SUPPORTED"):
        verdict, reason = "SAFE", "all claims supported"
    elif word.startswith("UNSUPPORTED"):
        verdict, reason = "LEAK", "judge found unsupported claims"
    else:
        verdict, reason = "UNSURE", f"judge replied: {msg.content[:60]!r}"
    return {"verdict": verdict, "reason": reason, "trace": state["trace"] + [f"check:{verdict}"]}


# ---------------- Node 4 and 5: final outcomes ----------------

def refuse(state: State) -> State:
    return {"answer": REFUSAL, "trace": state["trace"] + ["refuse"]}


def finish(state: State) -> State:
    return {"trace": state["trace"] + ["finish"]}


# ---------------- Routing: the decisions between steps ----------------

def after_retrieve(state: State) -> str:
    return "generate" if state["context"] else "refuse"


def after_check(state: State) -> str:
    if state["verdict"] == "SAFE":
        return "finish"
    if state["attempts"] < MAX_ATTEMPTS:
        return "generate"          # retry once with the strict prompt
    return "refuse"


def build_graph():
    g = StateGraph(State)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_node("check", check)
    g.add_node("refuse", refuse)
    g.add_node("finish", finish)

    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", after_retrieve, ["generate", "refuse"])
    g.add_edge("generate", "check")
    g.add_conditional_edges("check", after_check, ["finish", "generate", "refuse"])
    g.add_edge("finish", END)
    g.add_edge("refuse", END)
    return g.compile()


graph = build_graph()


async def ask(token, question):
    global llm
    if llm is None:
        llm = get_llm()
    return await graph.ainvoke({"token": token, "question": question})


if __name__ == "__main__":
    result = asyncio.run(ask(sys.argv[1], sys.argv[2]))
    print(f"\nAnswer:\n{result['answer']}\n")
    print(f"Path:    {' -> '.join(result['trace'])}")
    if result.get("reason"):
        print(f"Checker: {result['verdict']} ({result['reason']})")
    if os.getenv("DEBUG"):
         for i, d in enumerate(result.get("drafts", []), 1):
            print(f"\nDraft {i}:\n{d}")