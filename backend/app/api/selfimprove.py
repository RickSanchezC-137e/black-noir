"""/api/systems/selfimprove/* (C4, 09_self_improvement.md §13)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import selfimprove

router = APIRouter(prefix="/api/systems/selfimprove")


@router.get("/budget")
async def budget_status():
    from app.core import budget
    return budget.status()


@router.get("/adoptions")
async def adoptions():
    from app.core import adoption
    return {"adoptions": adoption.list_adoptions()}


@router.post("/canary")
async def run_canary():
    from app.core import night
    return await night.canary()


@router.post("/night")
async def night_tick():
    from app.core import night
    return await night.night_tick()


class RunIn(BaseModel):
    intent: str
    target_module: str = "mcp_fs"
    domain: str = "modules"
    base: str | None = None   # defaults to the core's own port (self)


class RollbackIn(BaseModel):
    token: str


@router.get("/status")
async def status():
    return await selfimprove.status()


@router.post("/scout")
async def scout():
    """Autonomous Scout tick (driven by noir-scout.timer)."""
    return await selfimprove.scout_cycle()


@router.post("/analyze")
async def analyze():
    """Self-analysis: mine own telemetry → ranked grounded improvement hypotheses."""
    from app.core import self_analysis
    return await self_analysis.analyze()


@router.get("/analysis")
async def analysis():
    """Latest self-analysis report (desktop Systems card)."""
    from app.core import self_analysis
    return await self_analysis.latest()


@router.get("/board")
async def board():
    """Full self-improvement dashboard: hypotheses (kanban), experiments, versions, budget, analysis."""
    import aiosqlite
    from app.config import settings
    out = {"hypotheses": [], "experiments": [], "versions": [], "audit": []}
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id,summary,intent,kind,domain,status,priority,created_at"
                               " FROM si_hypotheses ORDER BY created_at DESC LIMIT 60")
        out["hypotheses"] = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT id,hypothesis_id,domain,status,started_at,finished_at"
                               " FROM si_experiments ORDER BY started_at DESC LIMIT 25")
        out["experiments"] = [dict(r) for r in await cur.fetchall()]
        try:
            cur = await db.execute("SELECT domain,version,exp_id,token,active,created_at FROM si_versions ORDER BY rowid DESC LIMIT 12")
            out["versions"] = [dict(r) for r in await cur.fetchall()]
        except aiosqlite.OperationalError:
            cur = await db.execute("SELECT * FROM si_versions ORDER BY rowid DESC LIMIT 12")
            out["versions"] = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT module,tool,decision,action_class,ok,created_at FROM agent_log"
                               " WHERE module IN ('selfimprove','adoption','core','canary') ORDER BY id DESC LIMIT 20")
        out["audit"] = [dict(r) for r in await cur.fetchall()]
    try:
        from app.core import budget
        out["budget"] = budget.status()
    except Exception:  # noqa: BLE001
        out["budget"] = {}
    try:
        from app.core import self_analysis
        out["analysis"] = await self_analysis.latest()
    except Exception:  # noqa: BLE001
        out["analysis"] = {}
    return out


@router.post("/run")
async def run(body: RunIn):
    """One self-improvement iteration: scout->build->eval gate->governor->promote/reject."""
    return await selfimprove.run_once(body.intent, target_module=body.target_module,
                                      domain=body.domain, base=body.base)


class ImproveIn(BaseModel):
    module: str = "core"
    intent: str = ""


class ImpPromoteIn(BaseModel):
    token: str


@router.post("/improve")
async def improve(body: ImproveIn):
    """Owner-initiated improvement of a module: Builder→eval→diff (promote on confirm)."""
    from app.core import realimprove
    intent = (f"Улучши модуль {body.module}: {body.intent}. Меняй только относящийся к нему код; "
              f"НЕ трогай Governor/конституцию; eval должен остаться зелёным.")
    return await realimprove.owner_improve(intent, domain=body.module)


@router.post("/improve/promote")
async def improve_promote(body: ImpPromoteIn):
    from app.core import realimprove
    return await realimprove.owner_promote(body.token)


@router.post("/rollback")
async def rollback(body: RollbackIn):
    return await selfimprove.rollback(body.token)
