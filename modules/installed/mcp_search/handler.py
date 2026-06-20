"""mcp_search — real web search via Tavily (no stub).

Reads TAVILY_API_KEY from env (resolved by core from secrets/.env). Network egress
class is external_send → Governor gates it (CONFIRM by default per policy).
"""
from __future__ import annotations

import os

import httpx

TAVILY_URL = "https://api.tavily.com/search"


async def call(tool: str, args: dict) -> dict:
    if tool != "search.web":
        raise ValueError(f"unknown tool {tool}")
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        raise ValueError("TAVILY_API_KEY not configured")
    payload = {
        "api_key": key,
        "query": args["query"],
        "max_results": args.get("max_results", 5),
        "search_depth": args.get("depth", "basic"),
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(TAVILY_URL, json=payload)
        r.raise_for_status()
        data = r.json()
    results = [{"title": x.get("title"), "url": x.get("url"),
                "content": (x.get("content") or "")[:500]} for x in data.get("results", [])]
    return {"query": args["query"], "answer": data.get("answer"), "results": results}


async def health() -> dict:
    return {"ok": bool(os.environ.get("TAVILY_API_KEY")), "provider": "tavily"}
