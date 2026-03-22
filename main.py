import os
import httpx
import json
import argparse
import uvicorn
from typing import Optional
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, RedirectResponse
from starlette.routing import Route, Mount
from mcp.server.fastmcp import FastMCP

# --- Config ---
CURIOSITY_BASE = os.getenv("CURIOSITY_BASE_URL", "http://localhost:19191")
CURIOSITY_TOKEN = os.getenv("CURIOSITY_API_TOKEN", "")

# --- MCP Server ---
mcp = FastMCP("Curiosity Search", stateless_http=True)


def _parse_response(data: dict, query: str) -> dict:
    results = []
    items = (
        data.get("results")
        or data.get("items")
        or data.get("hits")
        or data.get("data", [])
    )
    if isinstance(items, list):
        for item in items:
            results.append({
                "title": item.get("title") or item.get("name") or item.get("subject", "Untitled"),
                "snippet": (item.get("snippet") or item.get("preview") or item.get("body", ""))[:300],
                "source": item.get("source") or item.get("app") or item.get("type", "unknown"),
                "url": item.get("url") or item.get("link"),
                "score": item.get("score") or item.get("relevance"),
            })
    return {"results": results, "total": len(results), "query": query}


async def _query_curiosity(query: str, max_results: int, source_filter: Optional[str]) -> dict:
    headers = {}
    if CURIOSITY_TOKEN:
        headers["Authorization"] = f"Bearer {CURIOSITY_TOKEN}"
    params = {"q": query, "limit": max_results}
    if source_filter:
        params["source"] = source_filter
    endpoints = [
        f"{CURIOSITY_BASE}/api/search",
        f"{CURIOSITY_BASE}/api/v1/search",
        f"{CURIOSITY_BASE}/search",
        f"{CURIOSITY_BASE}/api/query",
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        for endpoint in endpoints:
            try:
                resp = await client.get(endpoint, params=params, headers=headers)
                if resp.status_code == 200:
                    return _parse_response(resp.json(), query)
                resp = await client.post(endpoint, json={"query": query, "limit": max_results}, headers=headers)
                if resp.status_code == 200:
                    return _parse_response(resp.json(), query)
            except Exception:
                continue
    return {
        "results": [],
        "total": 0,
        "query": query,
        "error": f"Could not reach Curiosity at {CURIOSITY_BASE}. Make sure Curiosity Desktop is running.",
    }


@mcp.tool()
async def search_curiosity(
    query: str,
    max_results: int = 10,
    source_filter: Optional[str] = None,
) -> str:
    """Search across all your connected apps via Curiosity AI desktop app.
    Args:
        query: The search query to send to Curiosity
        max_results: Maximum number of results to return (1-50, default 10)
        source_filter: Optional filter by source app: slack, gmail, drive, notion, etc.
    """
    result = await _query_curiosity(query, max_results, source_filter)
    return json.dumps(result, indent=2)


@mcp.tool()
async def check_curiosity_status() -> str:
    """Check if the Curiosity Desktop App is running and reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{CURIOSITY_BASE}/api/search", params={"q": "test", "limit": 1})
            return json.dumps({"status": "connected", "http_status": resp.status_code})
    except Exception as e:
        return json.dumps({"status": "unreachable", "error": str(e)})


# --- OAuth metadata endpoint ---
async def oauth_metadata(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


# --- OAuth stub: dynamic client registration ---
async def oauth_register(request: Request) -> JSONResponse:
    body = await request.json()
    client_id = os.urandom(16).hex()
    return JSONResponse({
        "client_id": client_id,
        "client_secret": "",
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, status_code=201)


# --- OAuth stub: authorization endpoint ---
async def oauth_authorize(request: Request) -> Response:
    params = dict(request.query_params)
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code = os.urandom(16).hex()
    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={code}&state={state}"
    return RedirectResponse(url=location, status_code=302)


# --- OAuth stub: token endpoint ---
async def oauth_token(request: Request) -> JSONResponse:
    return JSONResponse({
        "access_token": "curiosity-no-auth",
        "token_type": "bearer",
        "expires_in": 86400,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Starting Curiosity MCP server on http://127.0.0.1:{args.port}")
    print("Transport: Streamable HTTP | MCP endpoint: /mcp")
    print("Press Ctrl+C to stop.")
    mcp_app = mcp.streamable_http_app()
    app = Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", oauth_metadata),
        Route("/oauth/register", oauth_register, methods=["POST"]),
        Route("/oauth/authorize", oauth_authorize),
        Route("/oauth/token", oauth_token, methods=["POST"]),
        Mount("/", app=mcp_app),
    ])
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        forwarded_allow_ips="*",
        proxy_headers=True,
    )
