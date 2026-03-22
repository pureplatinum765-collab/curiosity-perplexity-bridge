"""
Curiosity -> Perplexity Bridge Service
Exposes Curiosity Desktop App's local search as a remote HTTP connector
that Perplexity can call.
"""

import os
import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(title="Curiosity-Perplexity Bridge")

# --- Config ---
CURIOSITY_BASE = os.getenv("CURIOSITY_BASE_URL", "http://localhost:19191")
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", "change-me-to-a-secret")
CURIOSITY_TOKEN = os.getenv("CURIOSITY_API_TOKEN", "")


# --- Auth ---
async def verify_api_key(authorization: str = Header(...)):
    if authorization.replace("Bearer ", "") != BRIDGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Models ---
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query to send to Curiosity")
    max_results: int = Field(10, ge=1, le=50)
    source_filter: Optional[str] = Field(
        None, description="Filter by source app: slack, gmail, drive, notion, etc."
    )


class SearchResult(BaseModel):
    title: str
    snippet: str
    source: str
    url: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str


# --- Curiosity local API interaction ---
async def query_curiosity(query: str, max_results: int, source_filter: str | None):
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

    raise HTTPException(
        status_code=502,
        detail=(
            f"Could not reach Curiosity at {CURIOSITY_BASE}. "
            "Make sure the Curiosity Desktop App is running and check "
            "the port in Curiosity Settings > Advanced > API."
        ),
    )


def _parse_curiosity_response(data: dict, query: str) -> SearchResponse:
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
                SearchResult(
                    title=item.get("title") or item.get("name") or item.get("subject", "Untitled"),
                    snippet=item.get("snippet") or item.get("preview") or item.get("body", "")[:300],
                    source=item.get("source") or item.get("app") or item.get("type", "unknown"),
                    url=item.get("url") or item.get("link"),
                    score=item.get("score") or item.get("relevance"),
                )
            )

    return SearchResponse(results=results, total=len(results), query=query)


# --- Routes ---
@app.post("/search", response_model=SearchResponse, dependencies=[Depends(verify_api_key)])
async def search(req: SearchRequest):
    """Main search endpoint - Perplexity calls this."""
    return await query_curiosity(req.query, req.max_results, req.source_filter)


@app.get("/health")
async def health():
    return {"status": "ok", "curiosity_base": CURIOSITY_BASE}


@app.get("/schema")
async def schema():
    return {
        "name": "Curiosity Search",
        "description": "Search across all your connected apps via Curiosity AI",
        "endpoints": [
            {
                "path": "/search",
                "method": "POST",
                "description": "Search Curiosity unified index",
                "input": {
                    "query": {"type": "string", "required": True},
                    "max_results": {"type": "integer", "default": 10},
                    "source_filter": {"type": "string", "required": False},
                },
                "output": {
                    "results": [
                        {
                            "title": "string",
                            "snippet": "string",
                            "source": "string",
                            "url": "string",
                            "score": "number",
                        }
                    ],
                    "total": "integer",
                    "query": "string",
                },
            }
        ],
    }
