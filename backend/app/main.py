"""Noir core — FastAPI app (08_conventions §2/§7). Uvicorn on :8000 (CANON §2).

API base /api, WS /ws/* — neutral namespace (NO /jarvis/*).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_or_die
from app.core.profiler import detect_hardware
from app.db.session import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("noir.core")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_or_die()
    await init_db()
    hp = detect_hardware()
    log.info("hardware: cpu=%s ram_mb=%s gpu=%s -> %s", hp.cpu_cores, hp.ram_mb,
             hp.gpu.present, hp.local_layer)
    from app.core.modules_runtime import manager
    await manager.startup()
    installed = [r["module"] for r in manager.install_report() if r.get("installed")]
    log.info("modules installed: %s", installed)
    log.info("%s core up — model=%s embeddings=%s", settings.project_name,
             settings.claude_model, settings.embedding_model)
    yield


app = FastAPI(title=f"{settings.project_name} core", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# routers (imported after app to avoid cycles)
from app.api import (chat, core, governor, ideas, memory,  # noqa: E402
                     modules, selfimprove, tasks, visual, ws)

for r in (core.router, chat.router, memory.router, governor.router, modules.router,
          ideas.router, tasks.router, selfimprove.router, visual.router, ws.router):
    app.include_router(r)
