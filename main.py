"""
Curiosity -> Perplexity Bridge Service
Exposes Curiosity Desktop App's local search as an MCP server
that Perplexity can connect to as a Custom Remote Connector.
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional

# --- Config ---
CURIOSITY_BASE = os.getenv("CURIOSITY_BASE_URL", "http://localhost:19191")
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", "change-me-to-a-secret")
CURIOSITY_TOKEN = os.getenv("CURIOSITY_API_TOKEN", "")

# --- MCP Server ---
mcp = FastMCP(
    "Curiosity Search",
    description="Search across all your connected apps via Curiosity AI desktop app",
)


def _parse_curiosity_response(data: dict, query: str) -> dict:
    results = []
    items = (
        data.get("results")
        or data.get("items")
        or data.get("hits")
        or data.get("data", [])
    )
    if isinstance(items, list):
        for item in items:
            results.append(
                {
                    "title": item.get("title") or item.get("name") or item.get("subject", "Untitled"),
                    "snippet": item.get("snippet") or item.get("preview") or item.get("body", "")[:300],
                    "source": item.get("source") or item.get("app") or item.get("type", "unknown"),
                    "url": item.get("url") or item.get("link"),
                    "score": item.get("score") or item.get("relevance"),
                }
            )
    return {"results": results, "total": len(results), "query": query}


async def query_curiosity(query: str, max_results: int, source_filter: str | None) -> dict:
    headers = {}
    if CURIOSITY_TOKEN:
        headers["Authorization"] = f"Bearer {CURIOSITY_TOKEN}"

    params = {"q": query, "limit": max_results}
    if source_filter:
        params["source"] = source_filter

    endpoints_to_try = [
        f"{CURIOSITY_BASE}/api/search",
        f"{CURIOSITY_BASE}/api/v1/search",
        f"{CURIOSITY_BASE}/search",
        f"{CURIOSITY_BASE}/api/query",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for endpoint in endpoints_to_try:
            try:
                resp = await client.get(endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    return _parse_curiosity_response(resp.json(), query)
                resp = await client.post(
                    endpoint,
                    json={"query": query, "limit": max_results},
                    headers=headers,
                )
                if resp.status_code == 200:
                    return _parse_curiosity_response(resp.json(), query)
            except httpx.ConnectError:
                continue
            except Exception:
                continue

    return {
        "results": [],
        "total": 0,
        "query": query,
        "error": f"Could not reach Curiosity at {CURIOSITY_BASE}. Make sure the Curiosity Desktop App is running.",
    }


@mcp.tool()
async def search_curiosity(
    query: str,
    max_results: int = 10,
    source_filter: Optional[str] = None,
) -> str:
    """Search across all your connected apps (Slack, Gmail, Drive, Notion, etc.) via Curiosity AI desktop app.

    Args:
        query: The search query to send to Curiosity
        max_results: Maximum number of results to return (1-50, default 10)
        source_filter: Optional filter by source app: slack, gmail, drive, notion, etc.
    """
    import json
    result = await query_curiosity(query, max_results, source_filter)
    return json.dumps(result, indent=2)


@mcp.tool()
async def check_curiosity_status() -> str:
    """Check if the Curiosity Desktop App is running and reachable."""
    import json
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{CURIOSITY_BASE}/api/search", params={"q": "test", "limit": 1})
            return json.dumps({"status": "connected", "curiosity_base": CURIOSITY_BASE, "http_status": resp.status_code})
    except Exception as e:
        return json.dumps({"status": "unreachable", "curiosity_base": CURIOSITY_BASE, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="sse")
