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
    For owner_profile, returns profile facts as MemoryItem[]."""
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
        return {"module": module, "items": items, "hypotheses": hyps}
    return {"module": module, "items": [], "hypotheses": []}


@router.post("/remember")
async def remember(body: RememberIn):
    cid = await memory.remember(body.text, source=body.source, role=body.role)
    return {"ok": True, "chroma_id": cid}


@router.get("/recall")
async def recall(q: str = Query(...), k: int = 5):
    return {"query": q, "hits": await memory.recall(q, k=k)}
