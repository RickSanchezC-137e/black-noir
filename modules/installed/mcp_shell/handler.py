"""mcp_shell — real shell module with a strict command allowlist (no stub).

Only read-only, non-destructive commands are permitted. The first token must be in
ALLOW; shell metacharacters that could chain/escape are refused. Governor still gates
this as action_class=system on top of the allowlist (defense in depth).
"""
from __future__ import annotations

import shlex
import subprocess

ALLOW = {
    "ls", "cat", "pwd", "whoami", "date", "uname", "df", "free", "uptime",
    "echo", "head", "tail", "wc", "grep", "find", "stat", "id", "hostname",
    "ps", "ss", "systemctl",  # systemctl is read-only-gated below
}
# tokens that indicate shell chaining/redirection/escape — refuse
BAD = {"&&", "||", ";", "|", ">", ">>", "<", "`", "$(", "&"}
# systemctl: only read-only subcommands
SYSTEMCTL_RO = {"status", "is-active", "is-enabled", "list-units", "list-unit-files", "show", "cat"}


PROTECTED = ("/home/jarvis/secrets-backup", "/home/jarvis/noir/secrets")


def _validate(cmd: str) -> list[str]:
    if any(b in cmd for b in BAD):
        raise ValueError("shell metacharacters not allowed")
    if any(p in cmd for p in PROTECTED):
        raise ValueError("access to protected secrets path is forbidden")
    parts = shlex.split(cmd)
    if not parts:
        raise ValueError("empty command")
    if parts[0] not in ALLOW:
        raise ValueError(f"command '{parts[0]}' not in allowlist")
    if parts[0] == "systemctl":
        sub = next((p for p in parts[1:] if not p.startswith("-")), "")
        if sub not in SYSTEMCTL_RO:
            raise ValueError(f"systemctl '{sub}' is not read-only")
    return parts


async def call(tool: str, args: dict) -> dict:
    if tool != "shell.run":
        raise ValueError(f"unknown tool {tool}")
    parts = _validate(args["cmd"])
    r = subprocess.run(parts, capture_output=True, text=True, timeout=args.get("timeout", 20))
    return {"cmd": args["cmd"], "rc": r.returncode,
            "stdout": r.stdout[-8000:], "stderr": r.stderr[-2000:]}


async def health() -> dict:
    return {"ok": True, "allow_count": len(ALLOW)}
