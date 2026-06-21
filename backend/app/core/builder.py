"""Builder — headless Claude Code (CANON §2/§5) in an ISOLATED git worktree.

The Builder NEVER edits the live tree: it creates a git worktree sandbox, runs
`claude -p` there to realise a hypothesis, captures the diff + token usage, and returns
it for the Eval gate. Promotion to the live tree is a separate, Governor-gated step.
"""
from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

from app.config import settings

REPO = Path("/home/jarvis/noir")
WORKTREES = REPO / ".worktrees"


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def make_worktree() -> Path:
    WORKTREES.mkdir(exist_ok=True)
    wid = "si-" + uuid.uuid4().hex[:10]
    path = WORKTREES / wid
    _run(["git", "worktree", "add", "--detach", str(path), "HEAD"], REPO, timeout=120)
    return path


def drop_worktree(path: Path) -> None:
    _run(["git", "worktree", "remove", "--force", str(path)], REPO, timeout=120)


def build(instruction: str, *, timeout: int = 600) -> dict:
    """Realise an instruction in a sandbox worktree via headless Claude Code.
    Returns {ok, worktree, diff, tokens, summary}. Caller runs Eval, then promotes or drops.
    """
    wt = make_worktree()
    t0 = time.monotonic()
    tokens = 0
    summary = ""
    try:
        # acceptEdits: auto-apply file edits inside the sandbox; bounded by timeout.
        r = _run([settings.claude_code_bin, "-p", instruction,
                  "--output-format", "json", "--permission-mode", "acceptEdits"],
                 cwd=wt, timeout=timeout)
        try:
            data = json.loads(r.stdout)
            summary = (data.get("result") or "")[:2000]
            u = data.get("usage", {})
            tokens = int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0))
        except (ValueError, json.JSONDecodeError):
            summary = (r.stdout + r.stderr)[-2000:]
        diff = _run(["git", "diff", "--stat"], wt).stdout
        full = _run(["git", "diff"], wt).stdout
        return {"ok": r.returncode == 0, "worktree": str(wt), "diff_stat": diff,
                "diff": full[:20000], "tokens": tokens, "summary": summary,
                "ms": int((time.monotonic() - t0) * 1000)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "worktree": str(wt), "error": "builder timeout",
                "tokens": tokens, "ms": int((time.monotonic() - t0) * 1000)}


def cleanup_all() -> int:
    """Remove all stale sandbox worktrees."""
    n = 0
    if WORKTREES.exists():
        for p in WORKTREES.iterdir():
            if p.is_dir():
                drop_worktree(p)
                n += 1
    _run(["git", "worktree", "prune"], REPO)
    return n
