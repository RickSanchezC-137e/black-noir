"""/api/modules — registry, live status (HUD rings), tool invocation via Governor."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.modules_runtime import manager

router = APIRouter(prefix="/api/modules")


class CallIn(BaseModel):
    tool: str
    args: dict = {}


@router.get("")
async def list_modules():
    """Live module status for HUD rings (idle|busy|error|offline) — not demo data."""
    return {"modules": manager.list(), "install_report": manager.install_report()}


@router.get("/health")
async def health():
    return await manager.health_all()


@router.get("/{module}/logs")
async def logs(module: str, tail: int = 40):
    """Live module logs (core__module_logs) for the HUD inspector."""
    import aiosqlite

    from app.config import settings
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "SELECT ts,level,event,payload FROM core__module_logs WHERE module_id=?"
                " ORDER BY id DESC LIMIT ?", (module, tail))
            rows = [dict(r) for r in await cur.fetchall()]
        except aiosqlite.OperationalError:
            rows = []
    return {"module": module, "logs": rows}


@router.post("/{module}/call")
async def call(module: str, body: CallIn):
    return await manager.call(module, body.tool, body.args)


@router.post("/{module}/disable")
async def disable(module: str):
    return manager.set_enabled(module, False)


@router.post("/{module}/enable")
async def enable(module: str):
    return manager.set_enabled(module, True)
