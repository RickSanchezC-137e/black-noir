"""Claude Code chat channel — talk to the headless coding agent (CANON §2/§5).

Runs `claude -p` non-interactively in the repo. Default permission mode → write
tools that need approval are auto-denied in headless mode, so a chat turn is
effectively read-only (it can read/reason about the codebase, not mutate the live
tree — mutation is the Builder's sandboxed job). Memory is persistent across turns
via the CLI session id (--resume).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings

REPO = Path("/home/jarvis/noir")


def _bin() -> str | None:
    """Resolve the Claude Code CLI even when systemd PATH lacks npm-global."""
    cand = settings.claude_code_bin
    if os.path.isabs(cand) and os.path.exists(cand):
        return cand
    found = shutil.which(cand)
    if found:
        return found
    fallback = os.path.expanduser("~/.npm-global/bin/claude")
    return fallback if os.path.exists(fallback) else None


def _run(message: str, resume: str | None, timeout: int) -> dict:
    binary = _bin()
    if not binary:
        return {"reply": "[Claude Code CLI не найден на сервере]", "session": resume}
    cmd = [binary, "-p", message, "--output-format", "json"]
    if resume:
        cmd += ["--resume", resume]
    try:
        r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"reply": "[Claude Code: превышено время ожидания]", "session": resume}
    except (FileNotFoundError, OSError) as e:
        return {"reply": f"[Claude Code: не удалось запустить ({e})]", "session": resume}
    try:
        data = json.loads(r.stdout)
        return {"reply": (data.get("result") or "").strip() or "[пустой ответ]",
                "session": data.get("session_id") or resume}
    except (ValueError, json.JSONDecodeError):
        out = (r.stdout + r.stderr).strip()
        return {"reply": out[-2000:] or "[нет ответа от Claude Code]", "session": resume}


async def ask(message: str, resume: str | None = None, timeout: int = 240) -> dict:
    """Returns {reply, session}. Run in a thread so the event loop isn't blocked."""
    return await asyncio.to_thread(_run, message, resume, timeout)


def _brief(inp: dict | None) -> str:
    """One-line summary of a tool_use input for the live activity log."""
    if not isinstance(inp, dict):
        return ""
    for k in ("file_path", "path", "pattern", "command", "query", "url", "prompt"):
        v = inp.get(k)
        if v:
            return str(v)[:90]
    return ", ".join(str(k) for k in list(inp)[:3])[:90]


async def stream(message: str, resume: str | None = None, per_line_timeout: int = 300):
    """Async-generate Claude Code's live events (stream-json NDJSON) as compact dicts:
    {t:init,cc_session,model} · {t:text,text} · {t:tool,name,input} · {t:tool_done}
    · {t:done,text,cc_session} · {t:error,text}. Lets the UI show CC working in real time."""
    binary = _bin()
    if not binary:
        yield {"t": "error", "text": "[Claude Code CLI не найден на сервере]"}
        return
    cmd = [binary, "-p", message, "--output-format", "stream-json", "--verbose"]
    if resume:
        cmd += ["--resume", resume]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(REPO), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    final = ""
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=per_line_timeout)
            except asyncio.TimeoutError:
                yield {"t": "error", "text": "[Claude Code: превышено время ожидания]"}
                return
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            typ = ev.get("type")
            if typ == "system" and ev.get("subtype") == "init":
                yield {"t": "init", "cc_session": ev.get("session_id"), "model": ev.get("model")}
            elif typ == "assistant":
                for b in (ev.get("message", {}).get("content") or []):
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        yield {"t": "text", "text": b["text"].strip()}
                    elif b.get("type") == "tool_use":
                        yield {"t": "tool", "name": b.get("name"), "input": _brief(b.get("input"))}
            elif typ == "user":
                for b in (ev.get("message", {}).get("content") or []):
                    if b.get("type") == "tool_result":
                        yield {"t": "tool_done"}
            elif typ == "result":
                final = (ev.get("result") or "").strip()
                yield {"t": "done", "text": final or "[пустой ответ]", "cc_session": ev.get("session_id") or resume}
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001
            pass
