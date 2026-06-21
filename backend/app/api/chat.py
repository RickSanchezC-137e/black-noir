"""/api/chat (CANON §3, contract {reply, session_id})."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core import claude, claude_code, mediator, memory

router = APIRouter(prefix="/api")

# Chat channels (06_desktop.md §6.3): all persist history per session_id.
#   core        — direct dialogue with the core orchestrator
#   mediator    — Передатчик: consolidates owner msgs → task → concise essence
#   claude_code — headless Claude Code coding agent (read-only chat)
_AGENTS = {"core", "mediator", "claude_code"}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    agent: str = "core"
    target: str | None = None     # module:/task:/idea: side-thread (routed to core)
    cc_session: str | None = None  # Claude Code CLI session id (for --resume memory)


class ChatOut(BaseModel):
    reply: str
    session_id: str
    agent: str = "core"
    task: str | None = None        # mediator: the task actually sent to the core
    core_reply: str | None = None  # mediator: the full (detailed) core answer
    cc_session: str | None = None  # claude_code: CLI session id to resume next turn


async def _history(sid: str, limit: int = 20) -> list[dict]:
    """Recent turns of this session → [{role, content}] for conversational memory."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT role,content FROM messages WHERE session_id=?"
            " ORDER BY created_at DESC LIMIT ?", (sid, limit))
        rows = [dict(r) for r in await cur.fetchall()][::-1]
    return [{"role": r["role"], "content": r["content"]} for r in rows
            if r["role"] in ("user", "assistant")]


async def _ensure_session(sid: str) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sessions(id,created_at) VALUES(?,?)",
            (sid, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def _save(sid: str, role: str, content: str, ti: int = 0, to: int = 0) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO messages(id,session_id,role,content,tokens_in,tokens_out,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sid, role, content, ti, to, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn):
    sid = body.session_id or str(uuid.uuid4())
    agent = body.agent if body.agent in _AGENTS else "core"
    await _ensure_session(sid)
    hist = await _history(sid)
    await _save(sid, "user", body.message)
    await memory.remember(body.message, source=f"chat:{agent}", role="user")

    out = ChatOut(reply="", session_id=sid, agent=agent)
    if agent == "mediator":
        r = await mediator.relay(body.message, hist)
        out.reply, out.task, out.core_reply = r["reply"], r["task"], r["core_reply"]
    elif agent == "claude_code":
        r = await claude_code.ask(body.message, resume=body.cc_session)
        out.reply, out.cc_session = r["reply"], r["session"]
    else:
        out.reply, _, _ = await claude.chat(body.message, hist)

    await _save(sid, "assistant", out.reply)
    return out
