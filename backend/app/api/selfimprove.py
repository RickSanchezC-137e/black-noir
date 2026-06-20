"""/api/systems/selfimprove/* (C4, 09_self_improvement.md §13)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import selfimprove

router = APIRouter(prefix="/api/systems/selfimprove")


class RunIn(BaseModel):
    intent: str
    target_module: str = "mcp_fs"
    domain: str = "modules"
    base: str = "http://127.0.0.1:8001"


class RollbackIn(BaseModel):
    token: str


@router.get("/status")
async def status():
    return await selfimprove.status()


@router.post("/run")
async def run(body: RunIn):
    """One self-improvement iteration: scout->build->eval gate->governor->promote/reject."""
    return await selfimprove.run_once(body.intent, target_module=body.target_module,
                                      domain=body.domain, base=body.base)


@router.post("/rollback")
async def rollback(body: RollbackIn):
    return await selfimprove.rollback(body.token)
