"""/api/tasks — snapshot of orchestrator tasks (CANON §3). Live updates via /ws/tasks."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/tasks")


class CreateIn(BaseModel):
    kind: str = "manual"
    payload: str = ""


@router.get("")
async def list_tasks(limit: int = 50):
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,kind,status,created_at,updated_at FROM tasks"
            " ORDER BY created_at DESC LIMIT ?", (limit,))
        return {"tasks": [dict(r) for r in await cur.fetchall()]}


@router.post("")
async def create_task(body: CreateIn):
    """Create a queued task (manual / from UI). Real row in the tasks table."""
    import uuid
    tid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO tasks(id,kind,status,payload,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?)", (tid, body.kind, "pending", body.payload, now, now))
        await db.commit()
    return {"id": tid, "kind": body.kind, "status": "queued"}


@router.get("/{task_id}")
async def task_detail(task_id: str):
    """Single task + its audit log lines (HUD task inspector ИНФО/ЛОГ, §6.2)."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,kind,status,payload,result,error,created_at,updated_at"
            " FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        task = dict(row)
        cur = await db.execute(
            "SELECT module,tool,decision,action_class,reason,ok,created_at"
            " FROM agent_log WHERE reason LIKE ? OR tool LIKE ?"
            " ORDER BY id DESC LIMIT 50", (f"%{task_id[:8]}%", f"%{task_id[:8]}%"))
        log = [dict(r) for r in await cur.fetchall()]
    return {"task": task, "log": log}


async def _set_status(task_id: str, status: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cur = await db.execute(
            "UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, now, task_id))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "task not found")
    return {"ok": True, "id": task_id, "status": status}


@router.post("/{task_id}/cancel")
async def cancel(task_id: str):
    return await _set_status(task_id, "error")


@router.post("/{task_id}/retry")
async def retry(task_id: str):
    return await _set_status(task_id, "pending")
