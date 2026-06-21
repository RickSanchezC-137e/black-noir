"""Pluggable LLM providers for the multi-model core (council).

One async interface per provider: ask(system, message, history) -> text.
A missing API key makes that provider unavailable (skipped by the council).
DeepSeek uses an OpenAI-compatible endpoint; Gemini uses the Google REST API.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.core import claude


async def ask_opus(system: str, message: str, history: list[dict] | None = None) -> str:
    text, _, _ = await claude.chat_as(system, message, history)
    return text


async def ask_deepseek(system: str, message: str, history: list[dict] | None = None) -> str:
    if not settings.deepseek_api_key:
        raise RuntimeError("no deepseek key")
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in (history or [])]
    msgs.append({"role": "user", "content": message})
    async with httpx.AsyncClient(timeout=settings.council_timeout_s) as c:
        r = await c.post("https://api.deepseek.com/chat/completions",
                         headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                         json={"model": settings.deepseek_model, "messages": msgs,
                               "max_tokens": settings.llm_max_tokens})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


async def ask_gemini(system: str, message: str, history: list[dict] | None = None) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("no gemini key")
    contents = []
    for m in (history or []):
        contents.append({"role": "user" if m["role"] == "user" else "model",
                         "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    body = {"contents": contents,
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"maxOutputTokens": settings.llm_max_tokens}}
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}")
    async with httpx.AsyncClient(timeout=settings.council_timeout_s) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()
        cand = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in cand).strip()


async def ask_openai(system: str, message: str, history: list[dict] | None = None) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("no openai key")
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in (history or [])]
    msgs.append({"role": "user", "content": message})
    async with httpx.AsyncClient(timeout=settings.council_timeout_s) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions",
                         headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                         json={"model": settings.openai_model, "messages": msgs,
                               "max_tokens": settings.llm_max_tokens})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


def roster() -> list[dict]:
    """Council members + whether each is enabled (has a key)."""
    return [
        {"id": "opus", "name": "Claude Opus", "model": settings.claude_model, "enabled": bool(settings.anthropic_api_key)},
        {"id": "deepseek", "name": "DeepSeek", "model": settings.deepseek_model, "enabled": bool(settings.deepseek_api_key)},
        {"id": "gemini", "name": "Gemini", "model": settings.gemini_model, "enabled": bool(settings.gemini_api_key)},
        {"id": "openai", "name": "OpenAI GPT", "model": settings.openai_model, "enabled": bool(settings.openai_api_key)},
    ]


FNS = {"opus": ask_opus, "deepseek": ask_deepseek, "gemini": ask_gemini, "openai": ask_openai}


# ---------------- real liveness (actual ping, cached) — not just "has a key" ----------------
import asyncio as _asyncio
import time as _time

_LIVE: dict = {}
_LIVE_TS: float = 0.0


async def _ping_opus():
    await claude.client().messages.create(model=settings.claude_model, max_tokens=4,
                                           messages=[{"role": "user", "content": "ping"}])


async def _ping_openai():
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions",
                         headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                         json={"model": settings.openai_model, "max_tokens": 1,
                               "messages": [{"role": "user", "content": "ping"}]})
        r.raise_for_status()


async def _ping_deepseek():
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post("https://api.deepseek.com/chat/completions",
                         headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                         json={"model": settings.deepseek_model, "max_tokens": 1,
                               "messages": [{"role": "user", "content": "ping"}]})
        r.raise_for_status()


async def _ping_gemini():
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}")
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post(url, json={"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                                    "generationConfig": {"maxOutputTokens": 1}})
        r.raise_for_status()


_PINGS = {"opus": _ping_opus, "deepseek": _ping_deepseek, "gemini": _ping_gemini, "openai": _ping_openai}


async def _one_ping(pid):
    try:
        await _asyncio.wait_for(_PINGS[pid](), timeout=14)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:140]}


async def live_status(ttl: float = 300.0) -> list[dict]:
    """Roster with REAL availability (cached ping). enabled=has key; ok=actually answers now."""
    global _LIVE, _LIVE_TS
    now = _time.monotonic()
    if not _LIVE or (now - _LIVE_TS) >= ttl:
        ids = [m["id"] for m in roster() if m["enabled"]]
        res = await _asyncio.gather(*[_one_ping(i) for i in ids])
        _LIVE = {i: r for i, r in zip(ids, res)}; _LIVE_TS = now
    out = []
    for m in roster():
        st = _LIVE.get(m["id"]) if m["enabled"] else None
        out.append({**m, "ok": (st["ok"] if st else (None if m["enabled"] else False)),
                    "error": (st.get("error") if st else ("нет ключа" if not m["enabled"] else None))})
    return out
