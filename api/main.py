"""NeedToKnow API - the single front door for every client (the web UI, curl, a future Slack bot).
Run from the project root:  uvicorn api.main:app --port 8000 --reload
Needs Docker (Postgres) and the three MCP servers running."""
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import agent                                              # noqa: E402
from auth import AuthError, issue_token, verify_token     # noqa: E402

COMPANY = json.loads((ROOT / "data" / "company.json").read_text())
DEMO_USERS = {u["id"]: u for u in COMPANY["users"]}
WEB_PAGE = ROOT / "app" / "web" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent.llm = agent.get_llm()          # create the LLM client ONCE at startup, not per request
    yield


app = FastAPI(title="NeedToKnow", lifespan=lifespan)
bearer = HTTPBearer()                    # reads "Authorization: Bearer <token>"


# ---------- request / response shapes (FastAPI validates these automatically) ----------

class LoginRequest(BaseModel):
    user_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Source(BaseModel):
    title: str
    section: str


class AskResponse(BaseModel):
    user: str
    answer: str
    verdict: str | None = None
    reason: str | None = None
    path: list[str]
    sources: list[Source]
    rejected_drafts: list[str]


# ---------- auth: runs before every protected endpoint ----------

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        return verify_token(creds.credentials)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ---------- endpoints ----------

@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(WEB_PAGE)


@app.get("/users")
async def users():
    # DEMO ONLY: lets the UI show who can be picked. Display info - access is still decided by the database.
    return [{"id": u["id"], "name": u["name"], "role": u["role"], "groups": u["groups"]}
            for u in DEMO_USERS.values()]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/login")
async def login(req: LoginRequest):
    user_id = req.user_id.strip().lower()          # "Riya " -> "riya"
    # DEMO ONLY: picks a user without a password. Replace with SSO/password in a real deployment.
    if user_id not in DEMO_USERS:
        raise HTTPException(status_code=404, detail="unknown user")
    return {"token": issue_token(user_id)}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: str = Depends(current_user),
              creds: HTTPAuthorizationCredentials = Depends(bearer)):
    result = await agent.graph.ainvoke({"token": creds.credentials, "question": req.question})
    drafts = result.get("drafts", [])
    return AskResponse(
        user=user,
        answer=result["answer"],
        verdict=result.get("verdict"),
        reason=result.get("reason"),
        path=result["trace"],
        sources=[Source(title=c["title"], section=c["section"]) for c in result.get("context", [])],
        rejected_drafts=drafts[:-1] if len(drafts) > 1 else [],
    )