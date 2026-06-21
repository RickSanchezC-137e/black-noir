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


def roster() -> list[dict]:
    """Council members + whether each is enabled (has a key)."""
    return [
        {"id": "opus", "name": "Claude Opus", "model": settings.claude_model, "enabled": bool(settings.anthropic_api_key)},
        {"id": "deepseek", "name": "DeepSeek", "model": settings.deepseek_model, "enabled": bool(settings.deepseek_api_key)},
        {"id": "gemini", "name": "Gemini", "model": settings.gemini_model, "enabled": bool(settings.gemini_api_key)},
    ]


FNS = {"opus": ask_opus, "deepseek": ask_deepseek, "gemini": ask_gemini}
