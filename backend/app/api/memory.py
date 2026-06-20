"""/api/memory — remember/recall (CANON §3/§10)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core import memory

router = APIRouter(prefix="/api/memory")


class RememberIn(BaseModel):
    text: str
    source: str = "chat"
    role: str = "user"


@router.post("/remember")
async def remember(body: RememberIn):
    cid = await memory.remember(body.text, source=body.source, role=body.role)
    return {"ok": True, "chroma_id": cid}


@router.get("/recall")
async def recall(q: str = Query(...), k: int = 5):
    return {"query": q, "hits": await memory.recall(q, k=k)}
