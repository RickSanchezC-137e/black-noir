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
