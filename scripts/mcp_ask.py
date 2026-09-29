import asyncio
import sys

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

SERVERS = {"hr": 8001, "finance": 8002, "wiki": 8003}


async def ask_server(name, port, token, question):
    # The token travels in the HTTP Authorization header - never as a tool argument
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    try:
        async with Client(streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http)) as client:
            result = await client.call_tool("search", {"question": question})
            return name, result.structured_content["result"]
    except Exception:
        return name, "REFUSED - server rejected the token (401)"


async def main(token, question):
    results = await asyncio.gather(*(ask_server(n, p, token, question) for n, p in SERVERS.items()))
    for name, rows in results:
        print(f"\n[{name} server]")
        if isinstance(rows, str):
            print(f"  {rows}")
        elif not rows:
            print("  (nothing you're allowed to see)")
        else:
            for r in rows:
                print(f"  {r['score']:.4f}  {r['title']} > {r['section']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))