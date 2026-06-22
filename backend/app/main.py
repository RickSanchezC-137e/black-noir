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

# Owner auth gate: every /api/* (except the auth endpoints) needs a valid session
# cookie. Static frontend assets are NOT secret and stay open so the login overlay
# can load; all real data flows through /api + /ws, which are gated. (WS handshakes
# are checked inside app/api/ws.py — middleware doesn't see websocket scopes.)
from starlette.responses import JSONResponse  # noqa: E402
from app.core import webauth  # noqa: E402

_AUTH_OPEN = {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}


@app.middleware("http")
async def _auth_gate(request, call_next):
    p = request.url.path
    if p.startswith("/api/") and p not in _AUTH_OPEN:
        if not webauth.valid(request.cookies.get(webauth.COOKIE)):
            return JSONResponse({"detail": "auth required"}, status_code=401)
    return await call_next(request)


# routers (imported after app to avoid cycles)
from app.api import (auth, chat, core, governor, ideas, memory,  # noqa: E402
                     modules, selfimprove, tasks, visual, ws)

for r in (auth.router, core.router, chat.router, memory.router, governor.router, modules.router,
          ideas.router, tasks.router, selfimprove.router, visual.router, ws.router):
    app.include_router(r)

# Serve the web HUD (same build as desktop) at "/" so it's reachable by link
# (PC + phone) on the same origin as /api + /ws. Mounted AFTER routers so API wins.
try:
    from fastapi.staticfiles import StaticFiles
    import os as _os

    class _NoCacheStatic(StaticFiles):
        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            if path.endswith(".html") or path in (".", "index.html"):
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return resp

    _dist = "/home/jarvis/noir/desktop/dist"
    if _os.path.isdir(_dist):
        app.mount("/", _NoCacheStatic(directory=_dist, html=True), name="hud")
except Exception:  # noqa: BLE001
    pass
