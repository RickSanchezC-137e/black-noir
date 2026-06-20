"""ModuleManager — core-side runtime for Noir modules (05_modules.md §1/§2/§3).

On startup: Factory installs each discovered module (contract test in sandbox ->
register + Governor grants). Tools are invoked ONLY through here: every call is
classified by the manifest's action_class, gated by Governor, and audited to
agent_log (+ live core__module_logs). No module touches effectful resources directly.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from app.config import settings
from app.core.governor import ALLOW, Action, audit, governor

_REPO = Path(__file__).resolve().parents[3]   # noir/ (portable; not hardcoded to prod path)
_MODULES = _REPO / "modules"
for p in (str(_MODULES),):
    if p not in sys.path:
        sys.path.insert(0, p)

import factory  # noqa: E402
import registry  # noqa: E402
from base import Manifest, load_manifest  # noqa: E402


class ModuleManager:
    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}
        self._manifests: dict[str, Manifest] = {}
        self._install_report: list[dict] = []
        self._disabled: set[str] = set()

    def set_enabled(self, module: str, on: bool) -> dict:
        if module not in self._manifests:
            return {"ok": False, "error": f"module '{module}' not installed"}
        db = str(settings.sqlite_path)
        if on:
            self._disabled.discard(module)
            registry.set_status(db, module, "idle", enabled=1)
        else:
            self._disabled.add(module)
            registry.set_status(db, module, "offline", enabled=0)
        return {"ok": True, "module": module, "enabled": on}

    async def startup(self) -> None:
        # expose declared secrets to in-process modules via env (resolved from settings)
        import os
        if settings.tavily_api_key:
            os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)

        db = str(settings.sqlite_path)
        registry.ensure_tables(db)
        for mod_id in factory.discover():
            rep = factory.install(db, mod_id)
            self._install_report.append(rep)
            if rep.get("installed"):
                man = load_manifest(factory.INSTALLED / mod_id / "module.yaml")
                self._manifests[man.module_id] = man
                self._handlers[man.module_id] = factory.load_handler(factory.INSTALLED / mod_id)

    def list(self) -> list[dict]:
        rows = registry.list_modules(str(settings.sqlite_path))
        for r in rows:
            man = self._manifests.get(r["name"])
            r["cluster"] = man.cluster if man else None
            r["display_name"] = man.display_name if man else r["name"]
            r["tools"] = [t.name for t in man.tools] if man else []
        return rows

    def install_report(self) -> list[dict]:
        return self._install_report

    async def call(self, module: str, tool: str, args: dict) -> dict:
        db = str(settings.sqlite_path)
        man = self._manifests.get(module)
        if not man:
            return {"ok": False, "error": f"module '{module}' not installed"}
        if module in self._disabled:
            return {"ok": False, "error": f"module '{module}' is disabled (unloaded)"}
        spec = man.tool(tool)
        if not spec:
            return {"ok": False, "error": f"tool '{tool}' not declared by {module}"}

        action = Action(module=module, tool=tool, action_class=spec.action_class, args=args)
        decision = governor.authorize(action)
        if decision.decision != ALLOW:
            await audit(action, decision, ok=False)
            registry.log(db, module, "tool_denied", {"tool": tool, "decision": decision.decision})
            return {"ok": False, "blocked": True, "decision": decision.decision,
                    "reason": decision.reason}

        registry.set_status(db, module, "busy")
        t0 = time.monotonic()
        try:
            out = await self._handlers[module].call(tool, args)
            dt = int((time.monotonic() - t0) * 1000)
            await audit(action, decision, ok=True, duration_ms=dt)
            registry.log(db, module, "tool_call", {"tool": tool, "ms": dt})
            registry.set_status(db, module, "idle")
            return {"ok": True, "decision": ALLOW, "output": out, "ms": dt}
        except Exception as e:  # noqa: BLE001
            dt = int((time.monotonic() - t0) * 1000)
            await audit(action, decision, ok=False, duration_ms=dt)
            registry.log(db, module, "tool_error", {"tool": tool, "error": str(e)}, level="error")
            registry.set_status(db, module, "error")
            return {"ok": False, "error": str(e)}

    async def health_all(self) -> dict:
        out = {}
        for mid, h in self._handlers.items():
            try:
                out[mid] = await h.health()
            except Exception as e:  # noqa: BLE001
                out[mid] = {"ok": False, "error": str(e)}
        return out


manager = ModuleManager()
