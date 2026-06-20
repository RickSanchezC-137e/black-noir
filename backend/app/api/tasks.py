"""/api/tasks — snapshot of orchestrator tasks (CANON §3). Live updates via /ws/tasks."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/tasks")


@router.get("")
async def list_tasks(limit: int = 50):
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,kind,status,created_at,updated_at FROM tasks"
            " ORDER BY created_at DESC LIMIT ?", (limit,))
        return {"tasks": [dict(r) for r in await cur.fetchall()]}
