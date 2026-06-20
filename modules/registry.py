"""Module registry in SQLite (05_modules.md §3, 08_conventions §6).

Uses the canonical `modules` table for status (HUD rings) + manifest/version/namespace,
plus `core__module_grants` (what Governor granted) and `core__module_logs` (live logs).
Standalone: takes an explicit sqlite path (no backend import) to avoid cycles.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_tables(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS core__module_grants (
          module_id   TEXT NOT NULL,
          grant_type  TEXT NOT NULL,   -- action_class|secret|filesystem|network
          grant_value TEXT NOT NULL,
          granted_at  TEXT NOT NULL,
          PRIMARY KEY (module_id, grant_type, grant_value)
        );
        CREATE TABLE IF NOT EXISTS core__module_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          module_id TEXT NOT NULL, ts TEXT NOT NULL, level TEXT NOT NULL,
          event TEXT NOT NULL, payload TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_modlogs ON core__module_logs(module_id, ts);
        """
    )
    con.commit()
    con.close()


def register(db_path: str, *, name: str, version: str, namespace: str,
             manifest: dict, status: str = "idle") -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO modules(name,enabled,status,config,namespace,manifest,version,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?)"
        " ON CONFLICT(name) DO UPDATE SET status=excluded.status,"
        " namespace=excluded.namespace, manifest=excluded.manifest,"
        " version=excluded.version, updated_at=excluded.updated_at",
        (name, 1, status, "{}", namespace, json.dumps(manifest, ensure_ascii=False),
         version, _now()),
    )
    con.commit()
    con.close()


def grant(db_path: str, module_id: str, grant_type: str, grant_value: str) -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR IGNORE INTO core__module_grants(module_id,grant_type,grant_value,granted_at)"
        " VALUES(?,?,?,?)", (module_id, grant_type, grant_value, _now()))
    con.commit()
    con.close()


def set_status(db_path: str, name: str, status: str, *, enabled: int | None = None) -> None:
    con = sqlite3.connect(db_path)
    if enabled is None:
        con.execute("UPDATE modules SET status=?, updated_at=? WHERE name=?", (status, _now(), name))
    else:
        con.execute("UPDATE modules SET status=?, enabled=?, updated_at=? WHERE name=?",
                    (status, enabled, _now(), name))
    con.commit()
    con.close()


def log(db_path: str, module_id: str, event: str, payload: dict, level: str = "info") -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO core__module_logs(module_id,ts,level,event,payload) VALUES(?,?,?,?,?)",
        (module_id, _now(), level, event, json.dumps(payload, ensure_ascii=False)[:4000]))
    con.commit()
    con.close()


def list_modules(db_path: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT name,enabled,status,namespace,version FROM modules ORDER BY name").fetchall()
    con.close()
    return [dict(r) for r in rows]


def grants_for(db_path: str, module_id: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT grant_type,grant_value FROM core__module_grants WHERE module_id=?",
        (module_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
