# Black Noir

Personal autonomous AI assistant (rebuild of legacy "Jarvis"). Core on VPS-01, desktop is a Tauri+Vite "remote". Single source of truth: `../black-noir/CANON.md`.

`PROJECT_NAME = "Black Noir"` (code name "Noir") — centralized in `secrets/.env`, never hardcoded (CANON §14).

## Stack (fixed — CANON §2)
- Core: Python 3.11+ · FastAPI + Uvicorn · **:8000** · API base `/api`, WS `/ws/*` (no `/jarvis/*`).
- Memory: SQLite (aiosqlite) + ChromaDB · embeddings local `all-MiniLM-L6-v2` (dim=384).
- Brain: Claude API `claude-opus-4-8`. Builder: headless Claude Code. Modules: Python MCP servers.
- Voice: faster-whisper + Piper. Search: Tavily. Browser: Playwright.

## Layout (08_conventions §2)
```
backend/   FastAPI core (app/), Governor, memory, db schema, eval-tested
eval/      Eval harness (FIRST artifact) — runner.py, cases/, scorers.py
modules/   Python MCP servers (mcp_fs, mcp_shell, mcp_search, ...)
desktop/   Tauri + Vite HUD (live data only)
secrets/   .env + voices (OUTSIDE git)
deploy/    noir-core.service (systemd, Restart=always)
core/config/llm_layer.yaml   hardware-adaptive local-layer decision
_buildlog/ build context, autonomy inventory, deviations journal
```

## Run (dev)
```bash
# old Jarvis still holds :8000 during build → use PORT=8001
PORT=8001 scripts/dev_server.sh
python eval/runner.py --suite all --base http://127.0.0.1:8001
```

## Status (v1 build)
- [x] Secrets backup verified (outside git) · autonomy inventory · hardware profile
- [x] Eval harness · noir-core (core/chat/memory/governor) · Governor + immutable audit · SQLite + ChromaDB — **eval 8/8 green**
- [ ] Module system + Factory · perception/voice · Owner Profile · desktop · ideas+bot · self-improvement
- [ ] Green smoke → decommission old Jarvis (only then take :8000)
