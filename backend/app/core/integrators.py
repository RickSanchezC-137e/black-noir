"""Concrete adoption integrators — turn a scanned repo into a Python MCP module.

glances (#5, 11_adoption.md): adopt the lightweight engine (psutil, which glances installs
and is built on) to provide RICH live host metrics (per-core CPU, disk, net) — "лёгкое ядро
решения" per CANON §13. Foreign source is scanned in the sandbox first (adoption.py).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

INSTALLED = Path("/home/jarvis/noir/modules/installed")

_GLANCES_HANDLER = '''"""mcp_glances — live host metrics via the glances engine (psutil). Adopted from
nicolargo/glances (11_adoption.md #5). Read-only; richer than core /api/systems/metrics."""
from __future__ import annotations


def _psutil():
    import psutil
    return psutil


async def call(tool: str, args: dict) -> dict:
    if tool != "glances.snapshot":
        raise ValueError(f"unknown tool {tool}")
    ps = _psutil()
    vm = ps.virtual_memory()
    disk = ps.disk_usage("/")
    net = ps.net_io_counters()
    return {
        "cpu_percent": ps.cpu_percent(interval=0.2),
        "cpu_per_core": ps.cpu_percent(interval=0.2, percpu=True),
        "load": list(getattr(ps, "getloadavg", lambda: (0, 0, 0))()),
        "mem": {"percent": vm.percent, "used_mb": vm.used // 1048576, "total_mb": vm.total // 1048576},
        "disk": {"percent": disk.percent, "used_gb": disk.used // 1073741824, "total_gb": disk.total // 1073741824},
        "net": {"sent_mb": net.bytes_sent // 1048576, "recv_mb": net.bytes_recv // 1048576},
    }


async def health() -> dict:
    try:
        import psutil  # noqa
        return {"ok": True, "engine": "glances/psutil"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
'''

_GLANCES_MANIFEST = '''manifest_version: 1
module_id: mcp_glances
cluster: C6
display_name: "Host Metrics (glances)"
description: "Live host metrics (per-core CPU, RAM, disk, net) via the glances engine."
version: 1.0.0
runtime: in-process
namespace: m_mcp_glances__
tools:
  - { name: glances.snapshot, action_class: read, description: "Snapshot live host metrics" }
capabilities:
  filesystem: read
  network: none
  action_classes: [read]
  origin: "github.com/nicolargo/glances"
  license: "LGPL-3.0 (engine adopted as lib)"
'''

_GLANCES_TEST = '''"""Contract test for mcp_glances — hermetic."""
import asyncio
import handler


async def main():
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    print("mcp_glances contract OK")


asyncio.run(main())
'''


def glances_integrator(sandbox_dir: Path) -> str:
    """Install the engine + generate the mcp_glances module. Returns module_id."""
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psutil"],
                   capture_output=True, timeout=300)
    mod = INSTALLED / "mcp_glances"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "handler.py").write_text(_GLANCES_HANDLER)
    (mod / "module.yaml").write_text(_GLANCES_MANIFEST)
    (mod / "test_contract.py").write_text(_GLANCES_TEST)
    return "mcp_glances"
