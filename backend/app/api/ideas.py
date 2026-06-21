"""/api/ideas (C4) — generate + list proactive initiatives. Telegram channel status."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core import ideas as ideas_svc
from app.core import telegram

router = APIRouter(prefix="/api/ideas")


class GenIn(BaseModel):
    n: int = 3
    topic: str = "продуктивность и проекты владельца"


class IntakeIn(BaseModel):
    # GitHub-репо / ссылка / файл / видео / ручной ввод (06_desktop.md §6.5)
    source: str = "link"   # repo|link|file|video|text|telegram
    value: str


class RejectIn(BaseModel):
    reason: str = ""


class AdoptIn(BaseModel):
    repo: str                       # owner/name or full GitHub URL
    capability: str = ""
    cluster: str = "C6"


@router.get("")
async def list_ideas(limit: int = 60):
    """Ideas + per-item readiness progress (left join idea_detail)."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("CREATE TABLE IF NOT EXISTS idea_detail(idea_id TEXT PRIMARY KEY, progress INTEGER, data TEXT, updated_at TEXT)")
        cur = await db.execute(
            "SELECT i.id,i.text,i.status,i.score,i.created_at, COALESCE(d.progress,0) progress,"
            " (d.idea_id IS NOT NULL) analyzed FROM ideas i LEFT JOIN idea_detail d ON d.idea_id=i.id"
            " ORDER BY i.created_at DESC LIMIT ?", (limit,))
        return {"ideas": [dict(r) for r in await cur.fetchall()]}


@router.post("/generate")
async def generate(body: GenIn):
    return {"ideas": await ideas_svc.generate(n=body.n, topic=body.topic)}


@router.post("/intake")
async def intake(body: IntakeIn):
    """Ingest → study → sort (good/bad/review) → route worthy items to self-improvement."""
    val = body.value.strip()
    if not val:
        raise HTTPException(422, "empty value")
    from app.core import intake as intake_svc
    return await intake_svc.triage(body.source, val)


async def _set_status(idea_id: str, status: str) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cur = await db.execute("UPDATE ideas SET status=? WHERE id=?", (status, idea_id))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "idea not found")


@router.post("/{idea_id}/accept")
async def accept(idea_id: str):
    """Accept an idea → create a task (queued) and mark the idea accepted (§6.5)."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id,text FROM ideas WHERE id=?", (idea_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "idea not found")
        tid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO tasks(id,kind,status,payload,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (tid, "idea", "pending", row["text"], now, now))
        await db.execute("UPDATE ideas SET status='accepted' WHERE id=?", (idea_id,))
        await db.commit()
    return {"task_id": tid, "status": "accepted"}


@router.post("/{idea_id}/reject")
async def reject(idea_id: str, body: RejectIn | None = None):
    await _set_status(idea_id, "rejected")
    return {"ok": True}


@router.post("/adopt")
async def adopt_repo(body: AdoptIn):
    """Analyze a GitHub repo (clone+license+security+eval) and adopt if worthy."""
    from app.core import adoption
    repo = body.repo.strip().replace("https://github.com/", "").replace(".git", "").strip("/")
    rep = await adoption.adopt(repo, capability=body.capability, cluster=body.cluster)
    # flag overlap with an existing module of the same cluster (compare-vs-ours)
    try:
        from app.core.modules_runtime import manager
        rep["overlaps"] = [m["name"] for m in manager.list() if m.get("cluster") == body.cluster]
    except Exception:  # noqa: BLE001
        rep["overlaps"] = []
    return rep


class WrapIn(BaseModel):
    repo: str
    capability: str = ""
    cluster: str = "C6"


class PromoteIn(BaseModel):
    token: str


@router.post("/adopt/build")
async def adopt_build(body: WrapIn):
    """Builder writes an MCP wrapper for the repo (eval-gated, owner promotes)."""
    from app.core import adoption
    return await adoption.build_wrapper(body.repo, capability=body.capability, cluster=body.cluster)


@router.post("/adopt/promote")
async def adopt_promote(body: PromoteIn):
    """Owner-confirmed: apply the built wrapper to the live core."""
    from app.core import adoption
    return await adoption.promote_wrapper(body.token)


@router.get("/bot")
async def bot_status():
    """Live Telegram bot identity (getMe) — proves the escalation channel is wired."""
    me = await telegram.get_me()
    return {"telegram": me.get("result") if me.get("ok") else me}


@router.get("/{idea_id}")
async def idea_detail(idea_id: str):
    from app.core import intake as intake_svc
    return await intake_svc.get_detail(idea_id)


@router.post("/{idea_id}/analyze")
async def idea_analyze(idea_id: str):
    """Deep-dive: what/why/structure/where-to-integrate/license/security + readiness."""
    from app.core import intake as intake_svc
    return await intake_svc.analyze_detail(idea_id)
