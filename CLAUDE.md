# CLAUDE.md — Black Noir build guidance

**Single source of truth: `/home/jarvis/black-noir/CANON.md`.** On any conflict, CANON wins. Build order: `07_build_plan.md`. Control contract: `INSTRUCTIONS.md`.

## Hard rules (stop-crane)
1. **Never touch `/home/jarvis/secrets-backup/`** (verified secrets backup, outside git) or `secrets/`.
2. **Do not decommission old Jarvis** (`/home/jarvis/jarvis`, systemd `jarvis*`) until new core smoke is green (Rule 2). Old Jarvis holds `:8000` → build/test on `:8001`.
3. Stack is fixed (CANON §2): FastAPI+Uvicorn :8000, SQLite+ChromaDB, `all-MiniLM-L6-v2` dim=384, Python MCP modules, `/api` + `/ws/*` (never `/jarvis/*`, never :8080, no Postgres/Redis/pgvector/S3).
4. Every effectful action goes through **Governor** (`app/core/governor.py`): ALLOW/CONFIRM/DENY/KILL → immutable `agent_log`. Constitution is immutable.
5. `PROJECT_NAME` is the only place the name lives — never hardcode "Black Noir"/"Noir"/"Jarvis" in UI/paths/namespaces.
6. Modules are LIVE (real MCP servers), never demo stubs. Desktop renders live `/api/*` data only.
7. Eval is the traffic light: a stage isn't done until its suite is green (`python eval/runner.py`).

## Env
- venv: `backend/.venv` (Python 3.12). Secrets: `secrets/.env` (migrated from old Jarvis; `DUCKDNS_TOKEN` is MISSING — owner must supply).
- Hardware: no GPU, 4 vCPU, 7.8 GiB RAM → cloud-only local layer (`core/config/llm_layer.yaml`).
- Deviations recorded in `_buildlog/DEVIATIONS.md`; autonomy map in `_buildlog/01_autonomy_inventory.md`.
