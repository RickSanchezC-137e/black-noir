"""Ideas generator (C4) — proactive initiatives from memory + context.

Uses recalled long-term memory as context and Claude to propose concrete, relevant
initiatives for the owner. Stored in the `ideas` table; surfaced via /api/ideas and
the Telegram idea bot.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from app.config import settings
from app.core import claude, memory

_PROMPT = (
    "На основе контекста памяти ниже предложи {n} КОНКРЕТНЫХ проактивных инициативы "
    "для владельца (краткие, выполнимые, релевантные). Верни СТРОГО JSON-массив строк, "
    "без пояснений.\n\nКонтекст:\n{ctx}"
)


async def _store(ideas: list[str]) -> list[dict]:
    rows = []
    async with aiosqlite.connect(settings.sqlite_path) as db:
        for text in ideas:
            iid = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO ideas(id,text,status,created_at) VALUES(?,?,?,?)",
                (iid, text, "new", datetime.now(timezone.utc).isoformat()))
            rows.append({"id": iid, "text": text, "status": "new"})
        await db.commit()
    return rows


async def generate(n: int = 3, topic: str = "продуктивность и проекты владельца") -> list[dict]:
    hits = await memory.recall(topic, k=5)
    ctx = "\n".join(f"- {h.get('content','')}" for h in hits) or "(память пуста)"
    reply, _, _ = await claude.chat(_PROMPT.format(n=n, ctx=ctx))
    try:
        ideas = json.loads(reply[reply.index("["):reply.rindex("]") + 1])
        ideas = [str(x) for x in ideas][:n]
    except (ValueError, json.JSONDecodeError):
        ideas = [line.strip("-• ").strip() for line in reply.splitlines() if line.strip()][:n]
    return await _store(ideas)


async def list_ideas(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,text,status,created_at FROM ideas ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]
