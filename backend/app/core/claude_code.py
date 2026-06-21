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
