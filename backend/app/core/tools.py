"""Core tools — the actions the orchestrator may take from chat (CANON §5/§6).

Every EFFECTFUL tool passes through the Governor (ALLOW/CONFIRM/DENY/KILL +
immutable audit). Read tools are free; local writes auto-allow; module calls are
governed inside the module manager. CONFIRM-class actions are NOT auto-run — the
model is told they need the owner's confirmation.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from app.config import settings
from app.core import memory
from app.core.governor import ALLOW, Action, guard
from app.core.modules_runtime import manager

SCHEMAS = [
    {"name": "create_task", "description": "Создать задачу в канбане (очередь). Используй, когда владелец просит что-то сделать/запланировать.",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "description": "короткий заголовок задачи"},
         "payload": {"type": "string", "description": "детали/контекст"}}, "required": ["kind"]}},
    {"name": "list_modules", "description": "Список живых модулей системы (имя, кластер, статус, инструменты).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_module_logs", "description": "Хвост логов модуля.",
     "input_schema": {"type": "object", "properties": {
         "module": {"type": "string"}, "tail": {"type": "integer"}}, "required": ["module"]}},
    {"name": "call_module", "description": "Вызвать инструмент модуля (действие проходит через Governor).",
     "input_schema": {"type": "object", "properties": {
         "module": {"type": "string"}, "tool": {"type": "string"},
         "args": {"type": "object"}}, "required": ["module", "tool"]}},
    {"name": "remember", "description": "Сохранить факт в долгую память.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "create_idea", "description": "Завести идею на разбор (контур самоулучшения).",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "adopt_repo", "description": "Разобрать GitHub-репозиторий (лицензия+безопасность+eval) и внедрить, если стоящий и совместимый.",
     "input_schema": {"type": "object", "properties": {
         "repo": {"type": "string", "description": "owner/name или URL"},
         "capability": {"type": "string"}, "cluster": {"type": "string"}}, "required": ["repo"]}},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _governed(tool: str, action_class: str, run) -> str:
    """Guard an effectful action; execute only on ALLOW."""
    dec = await guard(Action(module="core", tool=tool, action_class=action_class))
    if dec.decision != ALLOW:
        return f"[Governor: {dec.decision} — {dec.reason}] действие не выполнено"
    return await run()


async def run(name: str, inp: dict) -> str:
    try:
        if name == "create_task":
            async def _do():
                tid = str(uuid.uuid4())
                async with aiosqlite.connect(settings.sqlite_path) as db:
                    await db.execute(
                        "INSERT INTO tasks(id,kind,status,payload,created_at,updated_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (tid, inp.get("kind", "задача"), "pending", inp.get("payload", ""), _now(), _now()))
                    await db.commit()
                return f"создана задача {tid[:8]} «{inp.get('kind','задача')}» (статус pending)"
            return await _governed("create_task", "local_write", _do)

        if name == "list_modules":
            mods = manager.list()
            return json.dumps([{"name": m["name"], "cluster": m.get("cluster"),
                                "status": m.get("status"), "tools": m.get("tools")} for m in mods],
                              ensure_ascii=False)

        if name == "get_module_logs":
            async with aiosqlite.connect(settings.sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                try:
                    cur = await db.execute(
                        "SELECT ts,level,event,payload FROM core__module_logs WHERE module_id=?"
                        " ORDER BY id DESC LIMIT ?", (inp["module"], int(inp.get("tail", 20))))
                    rows = [dict(r) for r in await cur.fetchall()]
                except aiosqlite.OperationalError:
                    rows = []
            return json.dumps(rows, ensure_ascii=False) or "[]"

        if name == "call_module":
            res = await manager.call(inp["module"], inp["tool"], inp.get("args", {}) or {})
            return json.dumps(res, ensure_ascii=False)

        if name == "remember":
            async def _do():
                await memory.remember(inp["text"], source="core_tool", role="assistant")
                return "сохранено в память"
            return await _governed("remember", "local_write", _do)

        if name == "create_idea":
            async def _do():
                iid = str(uuid.uuid4())
                async with aiosqlite.connect(settings.sqlite_path) as db:
                    await db.execute("INSERT INTO ideas(id,text,status,created_at) VALUES(?,?,?,?)",
                                     (iid, inp["text"], "new", _now()))
                    await db.commit()
                return f"идея {iid[:8]} заведена на разбор"
            return await _governed("create_idea", "local_write", _do)

        if name == "adopt_repo":
            from app.core import adoption
            repo = (inp.get("repo") or "").replace("https://github.com/", "").replace(".git", "").strip("/")
            rep = await adoption.adopt(repo, capability=inp.get("capability", ""), cluster=inp.get("cluster", "C6"))
            return json.dumps({"repo": repo, "verdict": rep.get("verdict"), "reason": rep.get("reason"),
                               "license": rep.get("license"), "security": (rep.get("security") or {}).get("safe"),
                               "module_id": rep.get("module_id")}, ensure_ascii=False)

        return f"[неизвестный инструмент: {name}]"
    except Exception as e:  # noqa: BLE001 — surface error to the model, don't crash the turn
        return f"[ошибка инструмента {name}: {e}]"
