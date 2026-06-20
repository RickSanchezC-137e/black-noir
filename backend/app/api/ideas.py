"""/api/ideas (C4) — generate + list proactive initiatives. Telegram channel status."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import ideas as ideas_svc
from app.core import telegram

router = APIRouter(prefix="/api/ideas")


class GenIn(BaseModel):
    n: int = 3
    topic: str = "продуктивность и проекты владельца"


@router.get("")
async def list_ideas(limit: int = 20):
    return {"ideas": await ideas_svc.list_ideas(limit)}


@router.post("/generate")
async def generate(body: GenIn):
    return {"ideas": await ideas_svc.generate(n=body.n, topic=body.topic)}


@router.get("/bot")
async def bot_status():
    """Live Telegram bot identity (getMe) — proves the escalation channel is wired."""
    me = await telegram.get_me()
    return {"telegram": me.get("result") if me.get("ok") else me}
