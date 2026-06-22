"""Core AI roster — the orchestration agents (orchestrator/reflex/critic/builder, C5/§5).

Editable: rename, set model, enable/disable, set persona, add new agents. Each is
chattable personally (target ai:<id>) with its own persistent session (= its log).
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from app.config import settings

_T = ("CREATE TABLE IF NOT EXISTS core_ai(id TEXT PRIMARY KEY, name TEXT, role TEXT,"
      " model TEXT, active INTEGER DEFAULT 1, system TEXT, created_at TEXT)")

_SEED = [
    ("orchestrator", "Оркестратор", "orchestrator", "Координирует задачи, решает что и каким модулем делать."),
    ("reflex", "Рефлекс", "reflex", "Быстрые короткие реакции и проверки на лету."),
    ("critic", "Критик/Судья", "critic", "Оценивает и проверяет ответы/изменения на ошибки и риски."),
    ("builder", "Builder", "builder", "Пишет код и собирает модули в песочнице (headless Claude Code)."),
]


def _con():
    c = sqlite3.connect(str(settings.sqlite_path)); c.row_factory = sqlite3.Row; c.execute(_T)
    return c


def seed() -> None:
    c = _con()
    if c.execute("SELECT COUNT(*) FROM core_ai").fetchone()[0] == 0:
        for aid, name, role, sysd in _SEED:
            c.execute("INSERT INTO core_ai(id,name,role,model,active,system,created_at) VALUES(?,?,?,?,?,?,?)",
                      (aid, name, role, settings.claude_model, 1, sysd, datetime.now(timezone.utc).isoformat()))
        c.commit()
    c.close()


def list_ai() -> list[dict]:
    seed(); c = _con()
    rows = [dict(r) for r in c.execute("SELECT id,name,role,model,active,system FROM core_ai ORDER BY created_at").fetchall()]
    c.close()
    for r in rows:
        r["active"] = bool(r["active"])
    return rows


def get_ai(aid: str) -> dict:
    c = _con(); r = c.execute("SELECT * FROM core_ai WHERE id=?", (aid,)).fetchone(); c.close()
    return dict(r) if r else {}


def update_ai(aid: str, **kw) -> dict:
    allowed = {k: v for k, v in kw.items() if k in ("name", "role", "model", "active", "system") and v is not None}
    if not allowed:
        return {"ok": False, "reason": "nothing to update"}
    if "active" in allowed:
        allowed["active"] = 1 if allowed["active"] else 0
    c = _con()
    c.execute("UPDATE core_ai SET " + ", ".join(f"{k}=?" for k in allowed) + " WHERE id=?",
              (*allowed.values(), aid))
    c.commit(); c.close()
    return {"ok": True, "id": aid}


def add_ai(name: str, role: str = "agent", model: str = "", system: str = "") -> dict:
    aid = "ai_" + uuid.uuid4().hex[:8]
    c = _con()
    c.execute("INSERT INTO core_ai(id,name,role,model,active,system,created_at) VALUES(?,?,?,?,?,?,?)",
              (aid, name, role, model or settings.claude_model, 1, system, datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    return {"ok": True, "id": aid, "name": name}
