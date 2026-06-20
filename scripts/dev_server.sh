#!/usr/bin/env bash
# Dev launcher for noir-core on VPS-01 (08_conventions §9).
# During parallel build the old Jarvis holds :8000 — use PORT=8001 until decommission.
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -e . 2>/dev/null || true
PORT="${PORT:-8000}"
exec uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --app-dir . --reload
