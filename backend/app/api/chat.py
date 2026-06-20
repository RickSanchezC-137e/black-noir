"""/api/chat (CANON §3, contract {reply, session_id})."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core import claude, memory

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None


class ChatOut(BaseModel):
    reply: str
    session_id: str


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
    await _ensure_session(sid)
    await _save(sid, "user", body.message)
    await memory.remember(body.message, source="chat", role="user")

    reply, ti, to = await claude.chat(body.message)

    await _save(sid, "assistant", reply, ti, to)
    return ChatOut(reply=reply, session_id=sid)
