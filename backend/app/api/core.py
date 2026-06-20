"""/api/core and /api/systems (CANON §3)."""
from __future__ import annotations

import time

from fastapi import APIRouter

from app.config import settings
from app.core.governor import governor
from app.core.profiler import profile_dict

router = APIRouter(prefix="/api")
_START = time.time()


@router.get("/core")
async def core_status():
    return {
        "status": "kill" if governor.killed else "ok",
        "project": settings.project_name,          # rename-friendly (CANON §14)
        "version": "v1-dev",
        "model": settings.claude_model,
        "uptime_s": round(time.time() - _START, 1),
        "governor": "engaged" if governor.killed else "active",
    }


@router.get("/systems")
async def systems():
    """Real hardware profile (Rule 7) — never demo data."""
    return {"hardware": profile_dict(), "embedding": {
        "model": settings.embedding_model, "dim": settings.embedding_dim}}
