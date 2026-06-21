"""/api/core and /api/systems (CANON §3). Feeds the desktop HUD with live data only."""
from __future__ import annotations

import sys
import time

from fastapi import APIRouter

from app.config import settings
from app.core.governor import governor
from app.core.profiler import detect_hardware, profile_dict

router = APIRouter(prefix="/api")
_START = time.time()


def _uptime() -> str:
    s = int(time.time() - _START)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    return f"{d}d {h:02d}h {m:02d}m"


@router.get("/core")
async def core_status():
    """Core overview + the 4 AI orchestrations (CANON §5) for the HUD 'СОСТАВ ИИ'."""
    return {
        "status": "kill" if governor.killed else "ok",
        "name": settings.project_name,             # rename-friendly (CANON §14)
        "project": settings.project_name,
        "version": "v1-dev",
        "model": settings.claude_model,
        "uptime_s": round(time.time() - _START, 1),
        "governor": "engaged" if governor.killed else "active",
        "ai": [
            {"id": "orchestrator", "name": "Оркестратор", "role": "orchestrator",
             "model": settings.claude_model, "status": "active"},
            {"id": "reflex", "name": "Рефлекс", "role": "reflex",
             "model": "claude-api (no GPU)", "status": "standby"},
            {"id": "critic", "name": "Критик/Судья", "role": "critic",
             "model": settings.claude_model, "status": "active"},
            {"id": "builder", "name": "Builder", "role": "builder",
             "model": "headless claude-code", "status": "standby"},
        ],
        "stats": [{"value": settings.embedding_model, "label": "embeddings"},
                  {"value": "384", "label": "dim"}],
    }


@router.get("/systems")
async def systems():
    """Real hardware profile (Rule 7) — never demo data."""
    return {"hardware": profile_dict(), "embedding": {
        "model": settings.embedding_model, "dim": settings.embedding_dim}}


@router.get("/systems/health")
async def health():
    return {"status": "kill" if governor.killed else "ok", "version": "v1-dev"}


@router.get("/systems/version")
async def version():
    return {"project": settings.project_name, "version": "v1-dev",
            "python": sys.version.split()[0]}


@router.get("/systems/metrics")
async def metrics():
    """Real host metrics (Rule 6/7) — no demo numbers."""
    hp = detect_hardware()
    cpu = _cpu_percent()
    used_mb, total_mb = _ram_used_total()
    return {"cpu": cpu, "ram": round(100 * used_mb / total_mb, 1) if total_mb else 0,
            "ram_used_mb": used_mb, "ram_total_mb": total_mb,
            "uptime": _uptime(), "cores": hp.cpu_cores, "gpu": hp.gpu.present}


def _cpu_percent() -> float:
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        import os
        return round(min(100.0, 100.0 * load1 / (os.cpu_count() or 1)), 1)
    except OSError:
        return 0.0


def _ram_used_total() -> tuple[int, int]:
    total = avail = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) // 1024
    except OSError:
        pass
    return (total - avail, total)
