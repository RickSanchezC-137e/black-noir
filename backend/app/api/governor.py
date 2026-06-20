"""/api/governor — inspect decisions and audit (CANON §3/§6)."""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core.governor import ALLOW, CLASSES, Action, governor, guard

router = APIRouter(prefix="/api/governor")


class CheckIn(BaseModel):
    module: str = "test"
    tool: str = "noop"
    action_class: str
    amount_usd: float = 0.0
    targets_constitution: bool = False


@router.get("")
async def status():
    return {"killed": governor.killed, "classes": list(CLASSES),
            "decisions": [ALLOW, "CONFIRM", "DENY", "KILL"]}


@router.post("/check")
async def check(body: CheckIn):
    a = Action(module=body.module, tool=body.tool, action_class=body.action_class,
               amount_usd=body.amount_usd, targets_constitution=body.targets_constitution)
    dec = await guard(a)
    return {"decision": dec.decision, "reason": dec.reason, "reversible": dec.reversible}


@router.get("/audit")
async def audit(limit: int = 20):
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT module,tool,decision,action_class,reason,ok,created_at"
            " FROM agent_log ORDER BY id DESC LIMIT ?", (limit,))
        return {"audit": [dict(r) for r in await cur.fetchall()]}
