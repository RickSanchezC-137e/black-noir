"""Module Factory (C4) — a module that creates new modules.

From a spec (name, cluster, purpose, tools, config schema) the Builder scaffolds a
fresh MCP module in a sandbox worktree, with its OWN per-module config section in the
manifest (so its settings render individually in the desktop tab — not one template).
Eval-gated, only writes its own module dir, promoted to live on owner confirm.
Feeds the self-improvement cloud: every created module is a registered, improvable unit.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path("/home/jarvis/noir")


def _instruction(mid: str, cluster: str, purpose: str, tools: list, config: list) -> str:
    toolspec = "\n".join(f"  - {{name: {t.get('name')}, action_class: {t.get('action_class','read')}, "
                         f"description: \"{t.get('description','')}\"}}" for t in tools) or "  - { name: noop, action_class: read, description: \"placeholder\" }"
    cfgspec = json.dumps(config, ensure_ascii=False)
    return (
        f"Создай НОВЫЙ MCP-модуль '{mid}' (кластер {cluster}). Назначение: {purpose}.\n"
        f"СОЗДАЙ ТОЛЬКО файлы в modules/installed/{mid}/ — ничего вне этого каталога.\n"
        f"  handler.py: 'async def call(tool, args)' (неизвестный tool → ValueError), 'async def health()'.\n"
        f"  module.yaml: manifest_version:1, module_id:{mid}, cluster:{cluster}, version:1.0.0, "
        f"runtime:in-process, namespace:m_{mid}__, display_name, description, секция tools:\n{toolspec}\n"
        f"  И ОБЯЗАТЕЛЬНО секция config: список настроек этого модуля в формате "
        f"[{{key,label,type:toggle|text|number|select,options?,default}}]. Возьми за основу: {cfgspec}\n"
        f"  test_contract.py: герметичный, печатает '{mid} contract OK'.\n"
        f"Эталон — modules/installed/mcp_glances/."
    )


async def build_module(name: str, *, cluster: str = "C6", purpose: str = "",
                       tools: list | None = None, config: list | None = None) -> dict:
    import asyncio

    from app.core import adoption, builder
    mid = "mcp_" + re.sub(r"[^a-z0-9_]", "_", (name or "").lower()) if not name.startswith("mcp_") else re.sub(r"[^a-z0-9_]", "_", name.lower())
    rep = {"module_id": mid, "cluster": cluster, "purpose": purpose}
    instr = _instruction(mid, cluster, purpose, tools or [], config or [])
    b = await asyncio.to_thread(builder.build, instr, timeout=600)
    wt = Path(b["worktree"]); rep["builder"] = {"ok": b.get("ok"), "tokens": b.get("tokens")}
    try:
        rel = f"modules/installed/{mid}"
        subprocess.run(["git", "add", "-A", rel], cwd=str(wt), capture_output=True, timeout=60)
        diff = subprocess.run(["git", "diff", "--cached", "--", rel], cwd=str(wt),
                              capture_output=True, text=True, timeout=60).stdout
        modp = wt / rel
        if not diff.strip() or not modp.exists():
            rep.update(verdict="failed", reason="Builder не создал модуль"); return rep
        touched = re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)
        outside = [f for f in touched if f != "/dev/null" and not f.startswith(rel + "/")]
        if outside:
            rep.update(verdict="rejected", reason=f"диф вне модуля: {outside[:3]}"); return rep
        import factory
        ok, out = factory.contract_test(modp)
        rep["eval"] = {"contract_ok": ok, "detail": out[-300:]}
        if not ok:
            rep.update(verdict="failed", reason="контракт-тест красный"); return rep
        from datetime import datetime, timezone
        token = "mod_" + datetime.now(timezone.utc).strftime("%H%M%S") + mid[-6:]
        adoption.WRAP_DIR.mkdir(exist_ok=True)
        (adoption.WRAP_DIR / f"{token}.patch").write_text(diff)
        rep.update(verdict="ready", token=token, diff_stat=b.get("diff_stat", ""),
                   reason="модуль собран и прошёл контракт — подтвердите создание")
    finally:
        try:
            builder.drop_worktree(wt)
        except Exception:  # noqa: BLE001
            pass
    return rep


# ---------------- autonomous build queue (off-core; processed by the contour) ----------------
import sqlite3 as _sq
from app.config import settings as _settings

_QTABLE = ("CREATE TABLE IF NOT EXISTS module_builds(id TEXT PRIMARY KEY, kind TEXT, name TEXT,"
           " cluster TEXT, purpose TEXT, tools TEXT, repo TEXT, status TEXT, token TEXT,"
           " verdict TEXT, reason TEXT, created_at TEXT, updated_at TEXT)")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def request_build(*, kind: str = "spec", name: str = "", cluster: str = "C6", purpose: str = "",
                  tools: list | None = None, repo: str = "") -> dict:
    """Enqueue a module-build request (the factory processes it off the core)."""
    import json
    import uuid
    bid = "build_" + uuid.uuid4().hex[:10]
    con = _sq.connect(str(_settings.sqlite_path)); con.execute(_QTABLE)
    con.execute("INSERT INTO module_builds(id,kind,name,cluster,purpose,tools,repo,status,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (bid, kind, name or (repo.split("/")[-1] if repo else ""), cluster, purpose,
                 json.dumps(tools or []), repo, "queued", _now(), _now()))
    con.commit(); con.close()
    return {"id": bid, "status": "queued", "kind": kind}


def list_builds(limit: int = 30) -> list[dict]:
    con = _sq.connect(str(_settings.sqlite_path)); con.row_factory = _sq.Row; con.execute(_QTABLE)
    rows = [dict(r) for r in con.execute(
        "SELECT id,kind,name,cluster,repo,status,token,verdict,reason,updated_at"
        " FROM module_builds ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    con.close(); return rows


def _set(bid: str, **kw) -> None:
    kw["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in kw)
    con = _sq.connect(str(_settings.sqlite_path))
    con.execute(f"UPDATE module_builds SET {cols} WHERE id=?", (*kw.values(), bid)); con.commit(); con.close()


async def tick() -> dict:
    """Process the oldest queued build (Builder in sandbox + eval). Off-core (contour/timer)."""
    import json
    con = _sq.connect(str(_settings.sqlite_path)); con.row_factory = _sq.Row; con.execute(_QTABLE)
    row = con.execute("SELECT * FROM module_builds WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
    con.close()
    if not row:
        return {"ran": False, "reason": "очередь пуста"}
    b = dict(row); _set(b["id"], status="building")
    try:
        if b["kind"] == "repo" and b["repo"]:
            from app.core import adoption
            r = await adoption.build_wrapper(b["repo"], cluster=b["cluster"] or "C6")
        else:
            r = await build_module(b["name"], cluster=b["cluster"] or "C6", purpose=b["purpose"] or "",
                                   tools=json.loads(b["tools"] or "[]"))
        v = r.get("verdict")
        if v == "ready":
            _set(b["id"], status="ready", token=r.get("token", ""), verdict=v, reason=r.get("reason", ""))
        else:
            _set(b["id"], status="failed", verdict=v or "failed", reason=r.get("reason", ""))
        return {"ran": True, "id": b["id"], "verdict": v, "module": r.get("module_id")}
    except Exception as e:  # noqa: BLE001
        _set(b["id"], status="failed", reason=str(e)[:160]); return {"ran": True, "id": b["id"], "error": str(e)}
