"""/api/chat (CANON §3, contract {reply, session_id})."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core import claude, claude_code, council, mediator, memory
from app.core import agent as orchestrator

router = APIRouter(prefix="/api")

# Chat channels (06_desktop.md §6.3): all persist history per session_id.
#   core        — direct dialogue with the core orchestrator
#   mediator    — Передатчик: consolidates owner msgs → task → concise essence
#   claude_code — headless Claude Code coding agent (read-only chat)
_AGENTS = {"core", "mediator", "claude_code", "guide", "council"}

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
    members: list | None = None    # council: per-model {provider, ok, ms}
    actions: list | None = None    # core: tools executed this turn (tool-use)


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


async def _get_summary(sid: str) -> str:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        try:
            cur = await db.execute("SELECT summary FROM sessions WHERE id=?", (sid,))
            row = await cur.fetchone()
            return (row[0] if row and row[0] else "")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
            await db.commit()
            return ""


async def _set_summary(sid: str, text: str) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        try:
            await db.execute("UPDATE sessions SET summary=? WHERE id=?", (text, sid))
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
            await db.execute("UPDATE sessions SET summary=? WHERE id=?", (text, sid))
        await db.commit()


async def _msg_count(sid: str) -> int:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (sid,))
        return (await cur.fetchone())[0]


async def _mem_context(sid: str, message: str) -> str:
    """Memory context for the model: rolling session summary + semantic recall (ChromaDB)."""
    parts = []
    summ = await _get_summary(sid)
    if summ:
        parts.append("Резюме прошлого этого диалога:\n" + summ)
    try:
        hits = await memory.recall(message, k=3)
        rel = "\n".join("- " + (h.get("content") or "") for h in hits if h.get("content"))
        if rel:
            parts.append("Возможно релевантное из долгой памяти:\n" + rel)
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


async def _maybe_summarize(sid: str) -> None:
    """Every ~10 messages, fold the recent thread into a rolling summary (long-term memory)."""
    n = await _msg_count(sid)
    if n < 8 or n % 10 != 0:
        return
    hist = await _history(sid, 24)
    old = await _get_summary(sid)
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in hist)
    prompt = (f"Старое резюме:\n{old or '(нет)'}\n\nНовые сообщения:\n{convo}\n\n"
              "Обнови КРАТКОЕ резюме диалога (что обсудили, решения, на чём остановились) — "
              "5–8 пунктов, по-русски.")
    try:
        summ, _, _ = await claude.chat_as("Ты ведёшь краткое резюме диалога для памяти ассистента.", prompt)
        await _set_summary(sid, summ.strip())
    except Exception:  # noqa: BLE001
        pass


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


async def _idea_system(idea_id: str) -> str:
    """Grounded agent for a specific intake item — knows its analysis (what/why/fit)."""
    base = ("Ты — агент по разбору этого элемента в Black Noir. Обсуждай ИМЕННО его: "
            "эффективность, нюансы, что он даст, как и куда встроится в систему, риски, "
            "стоит ли внедрять. Кратко, по-русски.")
    try:
        import json as _j
        async with aiosqlite.connect(settings.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            r = await (await db.execute("SELECT text FROM ideas WHERE id=?", (idea_id,))).fetchone()
            d = await (await db.execute("SELECT data FROM idea_detail WHERE idea_id=?", (idea_id,))).fetchone()
        ctx = []
        if r:
            ctx.append("Элемент: " + r["text"])
        if d:
            x = _j.loads(d["data"])
            for k, lbl in (("what", "что"), ("why", "зачем"), ("structure", "структура"), ("fit_cluster", "кластер"), ("fit_reason", "куда/как"), ("recommendation", "рекомендация")):
                if x.get(k):
                    ctx.append(f"{lbl}: {x[k]}")
        if ctx:
            base += "\n\nКОНТЕКСТ АНАЛИЗА:\n" + "\n".join(ctx)
    except Exception:
        pass
    return base


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn):
    agent = body.agent if body.agent in _AGENTS else "core"
    target = body.target or ""
    tgt_sys = _target_system(target)
    if target.startswith("idea:"):
        tgt_sys = await _idea_system(target.split(":", 1)[1])
    if target.startswith("ai:"):
        from app.core import core_ai
        a = core_ai.get_ai(target.split(":", 1)[1])
        tgt_sys = (f"Ты — {a.get('name', 'агент')} ({a.get('role', '')}) ядра Black Noir. {a.get('system', '')} "
                   "Отвечай кратко, по-русски, в рамках своей роли.") if a else "Ты — агент ядра Black Noir."
    # module/task/idea threads get their OWN agent + persistent per-target memory
    sid = body.session_id or (f"agent:{target}" if tgt_sys else str(uuid.uuid4()))
    await _ensure_session(sid)
    hist = await _history(sid)
    mem = await _mem_context(sid, body.message)    # rolling summary + semantic recall
    await _save(sid, "user", body.message)
    await memory.remember(body.message, source=f"chat:{target or agent}", role="user")

    _FACTORY_SYS = ("Сейчас ты — агент Фабрики модулей (C4). Когда владелец описывает нужный модуль, "
                    "ВЫЗОВИ инструмент request_module_build (name, cluster, purpose, tools). Подтверди, что "
                    "поставил сборку в очередь. На общие вопросы отвечай кратко.")
    out = ChatOut(reply="", session_id=sid, agent=("module" if tgt_sys else agent))
    if target == "module:factory":
        r = await orchestrator.run(body.message, hist, extra_system=_FACTORY_SYS)
        out.reply, out.actions = r["reply"], (r["actions"] or None)
    elif tgt_sys:
        out.reply, _, _ = await claude.chat_as(tgt_sys + (("\n\n" + mem) if mem else ""), body.message, hist)
    elif agent == "mediator":
        r = await mediator.relay(body.message, hist)
        out.reply, out.task, out.core_reply = r["reply"], r["task"], r["core_reply"]
    elif agent == "claude_code":
        r = await claude_code.ask(body.message, resume=body.cc_session)
        out.reply, out.cc_session = r["reply"], r["session"]
    elif agent == "council":
        r = await council.deliberate(body.message, hist)
        out.reply, out.members = r["reply"], r["members"]
    elif agent == "guide":
        out.reply, _, _ = await claude.chat_as(_GUIDE_SYS + (("\n\n" + mem) if mem else ""), body.message, hist)
    else:
        r = await orchestrator.run(body.message, hist, extra_system=mem)
        out.reply, out.actions = r["reply"], (r["actions"] or None)

    await _save(sid, "assistant", out.reply)
    await _maybe_summarize(sid)
    return out


@router.get("/chat/history")
async def chat_history(session_id: str, limit: int = 40):
    """Message history of a session (e.g. an AI agent's answer log)."""
    return {"session_id": session_id, "messages": await _history(session_id, limit)}


@router.get("/chat/summary")
async def chat_summary(session_id: str):
    """Where we left off — rolling summary of a chat session (shown on return)."""
    return {"session_id": session_id, "summary": await _get_summary(session_id)}
