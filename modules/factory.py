"""Module Factory (05_modules.md §5, build plan §6.3).

Installs a module via the sandbox pipeline: copy module into a sandbox worktree,
run its contract test in isolation, and ONLY on green register it in the SQLite
registry + record Governor grants (the manifest's declared action classes).
A module that fails its contract test is NOT registered (no stubs go live).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from base import Manifest, load_manifest  # type: ignore
import registry

REPO = Path(__file__).resolve().parent.parent          # /home/jarvis/noir
INSTALLED = REPO / "modules" / "installed"
SANDBOX = REPO / "modules" / ".sandbox"


def load_handler(mod_dir: Path):
    """Dynamically import handler.py from a module directory."""
    spec = importlib.util.spec_from_file_location(f"noirmod_{mod_dir.name}", mod_dir / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def contract_test(mod_dir: Path) -> tuple[bool, str]:
    """Run the module's contract test in a sandbox copy (isolation, §4.2)."""
    sbx = SANDBOX / mod_dir.name
    if sbx.exists():
        shutil.rmtree(sbx)
    sbx.mkdir(parents=True)
    shutil.copytree(mod_dir, sbx / mod_dir.name)
    test = sbx / mod_dir.name / "test_contract.py"
    if not test.exists():
        return False, "no test_contract.py"
    r = subprocess.run([sys.executable, str(test)], capture_output=True, text=True,
                       cwd=str(sbx / mod_dir.name), timeout=120)
    shutil.rmtree(sbx, ignore_errors=True)
    return (r.returncode == 0, (r.stdout + r.stderr)[-2000:])


def install(db_path: str, module_id: str) -> dict:
    """Full install: contract test -> register -> grants. Returns report."""
    mod_dir = INSTALLED / module_id
    if not (mod_dir / "module.yaml").exists():
        return {"module": module_id, "installed": False, "reason": "no module.yaml"}

    man: Manifest = load_manifest(mod_dir / "module.yaml")
    registry.ensure_tables(db_path)

    ok, out = contract_test(mod_dir)
    if not ok:
        registry.register(db_path, name=man.module_id, version=man.version,
                          namespace=man.namespace, manifest=_man_dict(man), status="error")
        return {"module": module_id, "installed": False, "reason": "contract test failed",
                "detail": out}

    registry.register(db_path, name=man.module_id, version=man.version,
                      namespace=man.namespace, manifest=_man_dict(man), status="idle")
    # Governor grants = declared action classes (checked at call time)
    for cls in sorted({t.action_class for t in man.tools}):
        registry.grant(db_path, man.module_id, "action_class", cls)
    return {"module": module_id, "installed": True, "version": man.version,
            "tools": [t.name for t in man.tools], "grants": sorted({t.action_class for t in man.tools})}


def _man_dict(m: Manifest) -> dict:
    return {"module_id": m.module_id, "cluster": m.cluster, "version": m.version,
            "runtime": m.runtime, "namespace": m.namespace,
            "tools": [{"name": t.name, "action_class": t.action_class} for t in m.tools],
            "capabilities": m.capabilities}


def discover() -> list[str]:
    if not INSTALLED.exists():
        return []
    return sorted(p.name for p in INSTALLED.iterdir() if (p / "module.yaml").exists())
