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


class FactoryIn(BaseModel):
    name: str
    cluster: str = "C6"
    purpose: str = ""
    tools: list = []
    config: list = []


class FactoryPromoteIn(BaseModel):
    token: str


@router.post("/factory/build")
async def factory_build(body: FactoryIn):
    """Module Factory: Builder scaffolds a new module (eval-gated, owner promotes)."""
    from app.core import module_factory
    return await module_factory.build_module(body.name, cluster=body.cluster, purpose=body.purpose,
                                             tools=body.tools, config=body.config)


@router.post("/factory/promote")
async def factory_promote(body: FactoryPromoteIn):
    from app.core import adoption
    return await adoption.promote_wrapper(body.token)


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


@router.get("/{module}/source")
async def source(module: str):
    """How the module is built now: manifest + files + improvement (version) log."""
    import aiosqlite
    from pathlib import Path
    from app.config import settings
    base = Path("/home/jarvis/noir/modules/installed") / module
    manifest, files = "", []
    if base.exists():
        files = sorted(p.name for p in base.iterdir() if p.is_file())
        y = base / "module.yaml"
        if y.exists():
            manifest = y.read_text(errors="ignore")[:3000]
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "SELECT version,experiment_id,rollback_token,active,created_at FROM si_versions"
                " WHERE domain=? ORDER BY created_at DESC LIMIT 20", (module,))
            versions = [dict(r) for r in await cur.fetchall()]
        except aiosqlite.OperationalError:
            versions = []
    return {"module": module, "manifest": manifest, "files": files, "improvements": versions}


@router.post("/{module}/call")
async def call(module: str, body: CallIn):
    return await manager.call(module, body.tool, body.args)


class ConfigIn(BaseModel):
    key: str
    value: object = ""


@router.post("/{module}/config")
async def set_config(module: str, body: ConfigIn):
    """Apply a per-module setting (dynamic config schema → UI)."""
    return manager.set_config(module, body.key, body.value)


@router.post("/{module}/disable")
async def disable(module: str):
    return manager.set_enabled(module, False)


@router.post("/{module}/enable")
async def enable(module: str):
    return manager.set_enabled(module, True)
