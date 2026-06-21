"""mcp_glances — live host metrics via the glances engine (psutil). Adopted from
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
