"""/api/memory — remember/recall + module memory slice (CANON §3/§10)."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings
from app.core import memory

router = APIRouter(prefix="/api/memory")


class RememberIn(BaseModel):
    text: str
    source: str = "chat"
    role: str = "user"


@router.get("")
async def memory_slice(module: str = Query(None)):
    """Memory slice for a module's private namespace (HUD Profile panel, §6.7).
    For owner_profile returns facts/hypotheses + health metrics, schedule and goals
    (10_owner_profile.md §11: домены, метрики, гипотезы, здоровье, расписание)."""
    if module == "owner_profile":
        async with aiosqlite.connect(settings.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id,domain,key,value,confidence,source,observed_at"
                " FROM m_owner_profile__profile_fact WHERE superseded_by IS NULL"
                " ORDER BY observed_at DESC LIMIT 100")
            items = [{"id": r["id"], "type": r["domain"], "key": r["key"], "value": r["value"],
                      "confidence": r["confidence"], "source": r["source"], "ts": r["observed_at"]}
                     for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT id,statement,status,verdict FROM m_owner_profile__profile_hypothesis")
            hyps = [{"id": r["id"], "statement": r["statement"], "status": r["status"],
                     "verdict": r["verdict"]} for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT id,metric,value,unit,observed_at,source"
                " FROM m_owner_profile__health_metric ORDER BY observed_at DESC LIMIT 60")
            health = [{"id": r["id"], "metric": r["metric"], "value": r["value"],
                       "unit": r["unit"], "ts": r["observed_at"], "source": r["source"]}
                      for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT id,title,start,end,recurrence,source,status"
                " FROM m_owner_profile__schedule_item ORDER BY start LIMIT 40")
            schedule = [{"id": r["id"], "title": r["title"], "start": r["start"],
                         "end": r["end"], "recurrence": r["recurrence"],
                         "status": r["status"], "source": r["source"]}
                        for r in await cur.fetchall()]
            cur = await db.execute(
                "SELECT id,title,horizon,progress,status,updated_at"
                " FROM m_owner_profile__goal ORDER BY updated_at DESC LIMIT 40")
            goals = [{"id": r["id"], "title": r["title"], "horizon": r["horizon"],
                      "progress": r["progress"], "status": r["status"], "ts": r["updated_at"]}
                     for r in await cur.fetchall()]
        return {"module": module, "items": items, "hypotheses": hyps,
                "health": health, "schedule": schedule, "goals": goals}
    return {"module": module, "items": [], "hypotheses": [],
            "health": [], "schedule": [], "goals": []}


@router.post("/remember")
async def remember(body: RememberIn):
    cid = await memory.remember(body.text, source=body.source, role=body.role)
    return {"ok": True, "chroma_id": cid}


@router.get("/recall")
async def recall(q: str = Query(...), k: int = 5):
    return {"query": q, "hits": await memory.recall(q, k=k)}
