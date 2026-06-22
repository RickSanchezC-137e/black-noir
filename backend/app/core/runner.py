"""Task runner — the missing executor. Picks pending tasks and actually DOES them
via the orchestrator's tool-use (Governor-gated), moving them pending→running→
done/error with progress + a log. Drives the kanban flow and overnight automation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.config import settings


def _now():
    return datetime.now(timezone.utc).isoformat()


def _set(tid, **kw):
    kw["updated_at"] = _now()
    con = sqlite3.connect(str(settings.sqlite_path))
    con.execute("UPDATE tasks SET " + ", ".join(f"{k}=?" for k in kw) + " WHERE id=?", (*kw.values(), tid))
    con.commit(); con.close()


def _get(tid):
    con = sqlite3.connect(str(settings.sqlite_path)); con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone(); con.close()
    return dict(r) if r else None


async def run_task(tid: str) -> dict:
    """Execute one task via the core agent (tool-use). Updates status/progress/log."""
    t = _get(tid)
    if not t:
        return {"ok": False, "reason": "not found"}
    _set(tid, status="running", progress=25)
    try:
        from app.core import agent
        instr = (t.get("payload") or t.get("kind") or "").strip() or "Выполни задачу."
        r = await agent.run("Задача: " + instr, [], extra_system=(
            "Ты ИСПОЛНЯЕШЬ поставленную задачу автономно. Используй инструменты при необходимости "
            "(create_task, call_module, adopt_repo, request_module_build, remember). Кратко отчитайся о результате."))
        actions = r.get("actions") or []
        log = "\n".join(f"• {a['tool']}: {a['result']}" for a in actions)
        result = (r.get("reply") or "") + (("\n\nДействия:\n" + log) if log else "")
        _set(tid, status="done", progress=100, result=result[:4000])
        return {"ok": True, "id": tid, "actions": len(actions)}
    except Exception as e:  # noqa: BLE001
        _set(tid, status="error", result=f"ошибка выполнения: {e}")
        return {"ok": False, "id": tid, "error": str(e)}


async def tick() -> dict:
    """Process the oldest pending task (off the request path / contour)."""
    con = sqlite3.connect(str(settings.sqlite_path)); con.row_factory = sqlite3.Row
    r = con.execute("SELECT id FROM tasks WHERE status='pending' ORDER BY created_at LIMIT 1").fetchone()
    con.close()
    if not r:
        return {"ran": False, "reason": "нет задач в очереди"}
    return await run_task(r["id"])
