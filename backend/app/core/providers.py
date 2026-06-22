"""Pluggable LLM providers — catalog-driven multi-model core (council).

Each provider: enabled = API key present; active = owner toggle (council_config).
A provider participates in the council only if enabled AND active. New providers
are added by supplying their key (set_key → secrets/.env). OpenAI-compatible
providers share one client; Anthropic and Gemini have their own.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time

import httpx

from app.config import settings
from app.core import claude

# id, name, kind, env var, base url (openai-compatible), model getter
CATALOG = [
    {"id": "opus", "name": "Claude Opus", "kind": "anthropic", "env": "ANTHROPIC_API_KEY",
     "key": lambda: settings.anthropic_api_key, "model": lambda: settings.claude_model},
    {"id": "openai", "name": "OpenAI GPT", "kind": "openai", "env": "OPENAI_API_KEY",
     "base": "https://api.openai.com/v1", "key": lambda: settings.openai_api_key, "model": lambda: settings.openai_model},
    {"id": "deepseek", "name": "DeepSeek", "kind": "openai", "env": "DEEPSEEK_API_KEY",
     "base": "https://api.deepseek.com", "key": lambda: settings.deepseek_api_key, "model": lambda: settings.deepseek_model},
    {"id": "gemini", "name": "Gemini", "kind": "gemini", "env": "GEMINI_API_KEY",
     "key": lambda: settings.gemini_api_key, "model": lambda: settings.gemini_model},
    {"id": "grok", "name": "xAI Grok", "kind": "openai", "env": "XAI_API_KEY",
     "base": "https://api.x.ai/v1", "key": lambda: settings.xai_api_key, "model": lambda: settings.xai_model},
    {"id": "mistral", "name": "Mistral", "kind": "openai", "env": "MISTRAL_API_KEY",
     "base": "https://api.mistral.ai/v1", "key": lambda: settings.mistral_api_key, "model": lambda: settings.mistral_model},
    {"id": "groq", "name": "Llama (Groq)", "kind": "openai", "env": "GROQ_API_KEY",
     "base": "https://api.groq.com/openai/v1", "key": lambda: settings.groq_api_key, "model": lambda: settings.groq_model},
]
_BY = {c["id"]: c for c in CATALOG}


def _active_map() -> dict:
    try:
        con = sqlite3.connect(str(settings.sqlite_path))
        con.execute("CREATE TABLE IF NOT EXISTS council_config(provider TEXT PRIMARY KEY, active INTEGER)")
        rows = con.execute("SELECT provider, active FROM council_config").fetchall(); con.close()
        return {p: bool(a) for p, a in rows}
    except sqlite3.Error:
        return {}


def set_active(pid: str, active: bool) -> dict:
    con = sqlite3.connect(str(settings.sqlite_path))
    con.execute("CREATE TABLE IF NOT EXISTS council_config(provider TEXT PRIMARY KEY, active INTEGER)")
    con.execute("INSERT INTO council_config(provider,active) VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET active=excluded.active",
                (pid, 1 if active else 0))
    con.commit(); con.close()
    return {"ok": True, "provider": pid, "active": active}


def roster() -> list[dict]:
    am = _active_map()
    out = []
    for c in CATALOG:
        out.append({"id": c["id"], "name": c["name"], "model": c["model"]() or "",
                    "enabled": bool(c["key"]()), "active": am.get(c["id"], True)})
    return out


async def _ask_oai(c: dict, system: str, message: str, history) -> str:
    key = c["key"]()
    if not key:
        raise RuntimeError("no key")
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in (history or [])]
    msgs.append({"role": "user", "content": message})
    async with httpx.AsyncClient(timeout=settings.council_timeout_s) as cl:
        r = await cl.post(c["base"].rstrip("/") + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": c["model"](), "messages": msgs, "max_tokens": settings.llm_max_tokens})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


async def _ask_gemini(c, system, message, history) -> str:
    key = c["key"]()
    if not key:
        raise RuntimeError("no key")
    contents = []
    for m in (history or []):
        contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{c['model']()}:generateContent?key={key}"
    async with httpx.AsyncClient(timeout=settings.council_timeout_s) as cl:
        r = await cl.post(url, json={"contents": contents, "systemInstruction": {"parts": [{"text": system}]},
                                     "generationConfig": {"maxOutputTokens": settings.llm_max_tokens}})
        r.raise_for_status()
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]).strip()


async def ask(pid: str, system: str, message: str, history=None) -> str:
    c = _BY[pid]
    if c["kind"] == "anthropic":
        txt, _, _ = await claude.chat_as(system, message, history); return txt
    if c["kind"] == "gemini":
        return await _ask_gemini(c, system, message, history)
    return await _ask_oai(c, system, message, history)


# back-compat: FNS[pid](system, message, history)
FNS = {c["id"]: (lambda s, m, h, _id=c["id"]: ask(_id, s, m, h)) for c in CATALOG}


# ---------------- real liveness (cached ping) ----------------
_LIVE: dict = {}
_LIVE_TS: float = 0.0


async def _ping(pid: str):
    c = _BY[pid]; key = c["key"]()
    if not key:
        raise RuntimeError("no key")
    if c["kind"] == "anthropic":
        await claude.client().messages.create(model=c["model"](), max_tokens=4,
                                              messages=[{"role": "user", "content": "ping"}]); return
    if c["kind"] == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{c['model']()}:generateContent?key={key}"
        async with httpx.AsyncClient(timeout=12) as cl:
            r = await cl.post(url, json={"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                                         "generationConfig": {"maxOutputTokens": 1}}); r.raise_for_status(); return
    async with httpx.AsyncClient(timeout=12) as cl:
        r = await cl.post(c["base"].rstrip("/") + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": c["model"](), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]})
        r.raise_for_status()


async def _one(pid):
    try:
        await asyncio.wait_for(_ping(pid), timeout=14); return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:140]}


async def _deepseek_balance() -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.get("https://api.deepseek.com/user/balance",
                             headers={"Authorization": f"Bearer {settings.deepseek_api_key}"})
            if r.status_code == 200:
                infos = r.json().get("balance_infos", [])
                if infos:
                    return f"{infos[0].get('total_balance')} {infos[0].get('currency')}"
    except Exception:  # noqa: BLE001
        pass
    return ""


async def live_status(ttl: float = 300.0) -> list[dict]:
    global _LIVE, _LIVE_TS
    now = time.monotonic()
    if not _LIVE or (now - _LIVE_TS) >= ttl:
        ids = [c["id"] for c in CATALOG if c["key"]()]
        res = await asyncio.gather(*[_one(i) for i in ids])
        _LIVE = {i: r for i, r in zip(ids, res)}; _LIVE_TS = now
    out = []
    for m in roster():
        st = _LIVE.get(m["id"]) if m["enabled"] else None
        m["ok"] = (st["ok"] if st else (None if m["enabled"] else False))
        m["error"] = (st.get("error") if st else ("нет ключа" if not m["enabled"] else None))
        m["balance"] = (await _deepseek_balance() if (m["id"] == "deepseek" and m["enabled"]) else None)
        out.append(m)
    return out
