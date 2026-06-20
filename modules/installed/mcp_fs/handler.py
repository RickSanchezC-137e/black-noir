"""mcp_fs — real sandboxed filesystem module (no stub).

All paths are confined to ROOT. Traversal outside ROOT (and any access to the
secrets/backup protected paths) is refused — defense in depth alongside Governor.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("NOIR_FS_SANDBOX", "/home/jarvis/noir/backend/data/fs_sandbox")).resolve()
PROTECTED = (Path("/home/jarvis/secrets-backup"), Path("/home/jarvis/noir/secrets"))


def _safe(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if not (p == ROOT or ROOT in p.parents):
        raise ValueError("path escapes sandbox root")
    for prot in PROTECTED:
        if p == prot or prot in p.parents:
            raise ValueError("protected path")
    return p


async def call(tool: str, args: dict) -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    if tool == "fs.list":
        d = _safe(args.get("path", "."))
        return {"path": str(d.relative_to(ROOT)), "entries": sorted(os.listdir(d))}
    if tool == "fs.read":
        f = _safe(args["path"])
        return {"path": args["path"], "content": f.read_text()}
    if tool == "fs.write":
        f = _safe(args["path"])
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(args.get("content", ""))
        return {"path": args["path"], "bytes": f.stat().st_size}
    raise ValueError(f"unknown tool {tool}")


async def health() -> dict:
    return {"ok": True, "root": str(ROOT)}
