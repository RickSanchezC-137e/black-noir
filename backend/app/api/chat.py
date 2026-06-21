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
_AGENTS = {"core", "mediator", "claude_code", "guide"}

# Volt-Bro — onboard system guide (companion). Concise answers about how the
# system is built + quick questions. Knowledge of the canonical architecture.
_GUIDE_SYS = (
    "Ты — Волт-Бро, бортовой помощник по системе Black Noir. Отвечай ОЧЕНЬ кратко, "
    "дружелюбно, по-русски (1–4 предложения). Объясняешь устройство системы и "
    "отвечаешь на быстрые вопросы.\n"
    "Архитектура: ядро на FastAPI, мозг — Claude-оркестратор; всё эффектное проходит "
    "через Governor (ALLOW/CONFIRM/DENY/KILL + неизменяемый аудит). 6 кластеров: "
    "C1 Взаимодействие (чат/голос/Telegram/Передатчик), C2 Память (ChromaDB+SQLite, "
    "Профиль владельца), C3 Восприятие (зрение/OCR/видео/слух), C4 Самоулучшение "
    "(Scout/Builder/Eval/Самоанализ), C5 Безопасность (Governor/аудит/kill-switch), "
    "C6 Инструменты (Web/Tavily/Shell/Git/Filesystem/glances). Десктоп — тонкий клиент "
    "на живых /api/*. Если чего-то не знаешь — честно скажи."
)


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


def _module_agent_system(mid: str) -> str:
    """Scoped persona for a module's own agent — answers AS the module, not the core."""
    try:
        from app.core.modules_runtime import manager
        m = next((x for x in manager.list() if x.get("name") == mid), None)
    except Exception:  # noqa: BLE001
        m = None
    if m:
        return (
            f"Ты — агент модуля «{m.get('display_name') or mid}» (кластер {m.get('cluster')}) "
            f"системы Black Noir. Твоя зона ответственности — функции этого модуля и его "
            f"инструменты: {', '.join(m.get('tools') or []) or '—'}. Отвечай кратко, по-русски, "
            f"ТОЛЬКО в рамках своей зоны. Если вопрос вне неё — скажи, что это к ядру или "
            f"другому модулю, и к какому."
        )
    return (f"Ты — агент модуля «{mid}» системы Black Noir. Отвечай кратко, по-русски, "
            f"в рамках зоны ответственности этого модуля.")


def _target_system(target: str) -> str | None:
    """System prompt for a module/task/idea side-thread agent (None → core)."""
    if target.startswith("module:"):
        return _module_agent_system(target.split(":", 1)[1])
    if target.startswith("task:"):
        return (f"Ты — агент задачи {target.split(':', 1)[1][:8]} в Black Noir. Отвечай кратко, "
                "по-русски, строго по этой задаче: статус, шаги, результат, помощь по ней.")
    if target.startswith("idea:"):
        return ("Ты — агент идеи в контуре самоулучшения Black Noir (C4). Отвечай кратко, "
                "по-русски: суть идеи, польза, риски, как проверить/принять.")
    return None


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn):
    agent = body.agent if body.agent in _AGENTS else "core"
    target = body.target or ""
    tgt_sys = _target_system(target)
    # module/task/idea threads get their OWN agent + persistent per-target memory
    sid = body.session_id or (f"agent:{target}" if tgt_sys else str(uuid.uuid4()))
    await _ensure_session(sid)
    hist = await _history(sid)
    await _save(sid, "user", body.message)
    await memory.remember(body.message, source=f"chat:{target or agent}", role="user")

    out = ChatOut(reply="", session_id=sid, agent=("module" if tgt_sys else agent))
    if tgt_sys:
        out.reply, _, _ = await claude.chat_as(tgt_sys, body.message, hist)
    elif agent == "mediator":
        r = await mediator.relay(body.message, hist)
        out.reply, out.task, out.core_reply = r["reply"], r["task"], r["core_reply"]
    elif agent == "claude_code":
        r = await claude_code.ask(body.message, resume=body.cc_session)
        out.reply, out.cc_session = r["reply"], r["session"]
    elif agent == "guide":
        out.reply, _, _ = await claude.chat_as(_GUIDE_SYS, body.message, hist)
    else:
        out.reply, _, _ = await claude.chat(body.message, hist)

    await _save(sid, "assistant", out.reply)
    return out
