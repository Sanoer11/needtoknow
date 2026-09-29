import sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from auth import AuthError, verify_token          # noqa: E402
from secure_search import DB_URL, hybrid_search   # noqa: E402

DEPARTMENT = sys.argv[1]            # hr | finance | wiki
PORT = int(sys.argv[2])             # 8001 | 8002 | 8003


class JWTVerifier:
    """Runs on EVERY request, before any tool. Bad or missing token -> 401, tool never runs."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = verify_token(token)
        except AuthError:
            return None
        return AccessToken(token=token, client_id="needtoknow", subject=user, scopes=[])


mcp = MCPServer(
    f"needtoknow-{DEPARTMENT}",
    token_verifier=JWTVerifier(),
    auth=AuthSettings(
        issuer_url="http://127.0.0.1:9000",
        resource_server_url=f"http://127.0.0.1:{PORT}/mcp",
        required_scopes=[],
        validate_token_resource=False,   # our JWTVerifier checks the token itself
    ),
)


@mcp.tool()
def search(question: str) -> list[dict]:
    """Search this department's documents. Returns only sections the caller may read."""
    user = get_access_token().subject          # from the verified token, NOT from the LLM or the caller's arguments
    with psycopg.connect(DB_URL) as conn:
        register_vector(conn)
        rows = hybrid_search(conn, user, question, k=5, department=DEPARTMENT)
    return [{"title": t, "section": s, "score": round(score, 4)} for _, t, s, score in rows]


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=PORT)