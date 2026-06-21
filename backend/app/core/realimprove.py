"""Real self-improvement cycle (09_self_improvement.md) — the genuine article.

Builder (headless Claude Code) makes an ACTUAL code change in an isolated worktree; a
CHALLENGER core is spun from that worktree and Eval'd against the live CHAMPION. Promotion
happens only if the challenger is measurably better with zero regressions and 0 violations,
then the diff is applied to the live tree, the core restarts, and live Eval must stay green —
otherwise auto-rollback. Snapshot + 1-step rollback throughout.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import httpx

from app.config import settings
from app.core import budget, builder
from app.core.governor import Action, audit, governor

REPO = Path("/home/jarvis/noir")
CHALLENGER_PORT = 8011
GATE_SUITES = ["improve", "core", "governor"]   # deterministic, no Claude cost


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _touches_constitution(diff: str) -> bool:
    return any(s in diff for s in ("app/core/governor.py", "constitution", "deny_list",
                                   "DENY_ALWAYS", "kill_switch"))


def _eval(base: str, suites: list[str]) -> dict:
    cmd = [sys.executable, str(REPO / "eval" / "runner.py"), "--suite", *suites, "--base", base]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO / "eval"), timeout=200)
    out = r.stdout + r.stderr
    passed = total = 0
    per = {}
    for line in out.splitlines():
        if line.startswith("TOTAL:"):
            frac = line.split(":")[1].strip().split()[0]
            passed, total = (int(x) for x in frac.split("/"))
        for s in suites:
            if line.strip().startswith(s + " ") or f"  {s} " in line:
                pass
    # parse per-suite pass-rate lines ("  suite   n/m")
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and "/" in parts[1] and parts[0] in suites:
            a, b = parts[1].split("/")
            per[parts[0]] = (int(a), int(b))
    return {"passed": passed, "total": total, "per": per, "ok": passed == total and total > 0}


def spin_challenger(wt: Path) -> tuple[subprocess.Popen | None, str]:
    """Start a uvicorn from the worktree on an isolated port + temp DB/data. Returns (proc, base)."""
    env = dict(os.environ,
               ANTHROPIC_API_KEY=settings.anthropic_api_key or "test",
               TAVILY_API_KEY=settings.tavily_api_key or "",
               TELEGRAM_BOT_TOKEN="", TELEGRAM_OWNER_CHAT_ID="",
               SQLITE_PATH=f"/tmp/chall_{wt.name}.sqlite",
               DATA_DIR=f"/tmp/chall_{wt.name}_data",
               CHROMA_DIR=f"/tmp/chall_{wt.name}_chroma",
               NOIR_FS_SANDBOX=f"/tmp/chall_{wt.name}_fs",
               NOIR_PIPER_VOICE="/home/jarvis/noir/secrets/voices/ru_RU-dmitri-medium.onnx")
    proc = subprocess.Popen(
        [str(REPO / "backend" / ".venv" / "bin" / "uvicorn"), "app.main:app",
         "--host", "127.0.0.1", "--port", str(CHALLENGER_PORT), "--app-dir", str(wt / "backend")],
        cwd=str(wt / "backend"), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{CHALLENGER_PORT}"
    for _ in range(40):
        time.sleep(0.5)
        try:
            if httpx.get(base + "/api/core", timeout=2).status_code == 200:
                return proc, base
        except httpx.HTTPError:
            pass
    proc.terminate()
    return None, base


async def _record_version(domain: str, reverse_patch: str) -> str:
    token = f"rb_{domain}_{uuid.uuid4().hex[:8]}"
    Path("/home/jarvis/noir/.worktrees").mkdir(exist_ok=True)
    Path(f"/home/jarvis/noir/.worktrees/{token}.patch").write_text(reverse_patch)
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cur = await (await db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM si_versions WHERE domain=?", (domain,))).fetchone()
        ver = cur[0]
        await db.execute("UPDATE si_versions SET active=0 WHERE domain=?", (domain,))
        await db.execute(
            "INSERT INTO si_versions(domain,version,experiment_id,rollback_token,active,created_at)"
            " VALUES(?,?,?,?,?,?)", (domain, ver, "real-build", token, 1, _now()))
        await db.commit()
    return token


def _restart_core() -> bool:
    subprocess.run(["sudo", "systemctl", "restart", "noir-core.service"], capture_output=True, timeout=60)
    base = "http://127.0.0.1:8000"
    for _ in range(30):
        time.sleep(1)
        try:
            if httpx.get(base + "/api/core", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
    return False


async def build_real(intent: str, *, domain: str = "core", apply_to_live: bool = False) -> dict:
    """Builder -> challenger eval -> gate. apply_to_live=False (default) is a DRY RUN: it
    proves the change passes the gate WITHOUT touching the live production core. Live promotion
    requires apply_to_live=True (explicit owner authorization)."""
    ok, why = budget.can_spend()
    if not ok:
        return {"decision": "paused", "reason": why}

    action = Action(module="realimprove", tool="build", action_class="self_modify",
                    args={"intent": intent})
    gov = governor.authorize(action)
    rep = {"intent": intent, "governor": gov.decision}

    b = builder.build(intent, timeout=600)
    budget.charge(tokens=b.get("tokens", 0), builder=1, requests=1)
    wt = Path(b["worktree"])
    rep["builder"] = {"ok": b.get("ok"), "tokens": b.get("tokens"), "diff_stat": b.get("diff_stat", "")}

    try:
        if not b.get("diff", "").strip():
            rep["decision"] = "reject"; rep["reason"] = "builder produced no change"
            await audit(action, gov, ok=False); return rep
        if _touches_constitution(b["diff"]):
            governor.engage_kill("real-build attempted to modify constitution")
            rep["decision"] = "KILL"; rep["reason"] = "diff touches constitution"
            await audit(action, gov, ok=False); return rep

        proc, base = spin_challenger(wt)
        if not proc:
            rep["decision"] = "reject"; rep["reason"] = "challenger failed to start (likely broken change)"
            await audit(action, gov, ok=False); return rep
        try:
            chall = _eval(base, GATE_SUITES)
            champ = _eval("http://127.0.0.1:8000", GATE_SUITES)
        finally:
            proc.terminate()
        rep["challenger"] = chall; rep["champion"] = champ

        # measurable improvement: challenger passes >= champion AND beats it on the 'improve' suite,
        # no regression on core/governor, 0 violations.
        ci, mi = chall["per"].get("improve", (0, 1))
        pi, _ = champ["per"].get("improve", (0, 1))
        no_regress = chall["per"].get("core", (0, 0))[0] >= champ["per"].get("core", (0, 0))[0] and \
            chall["per"].get("governor", (0, 0))[0] >= champ["per"].get("governor", (0, 0))[0]
        better = (ci > pi) and no_regress and chall["ok"]
        rep["measurably_better"] = bool(better)
        rep["improve_champion_vs_challenger"] = f"{pi} -> {ci}"
        if not (better and gov.decision in ("ALLOW", "CONFIRM")):
            rep["decision"] = "reject"
            rep["reason"] = f"not better (improve {pi}->{ci}, no_regress={no_regress}, gov={gov.decision})"
            await audit(action, gov, ok=False); return rep

        # DRY RUN: gate passed, but do NOT touch the live production core (owner authorizes live).
        if not apply_to_live:
            rep["decision"] = "would_promote"
            rep["reason"] = "gate PASSED in sandbox; live promotion withheld (dry-run, owner CONFIRM)"
            rep["diff"] = b["diff"][:4000]
            await audit(action, gov, ok=True); return rep

        # PROMOTE: apply diff to live, snapshot reverse patch, restart, verify live eval green
        reverse = subprocess.run(["git", "diff", "-R"], cwd=str(wt), capture_output=True, text=True).stdout
        apply = subprocess.run(["git", "apply"], input=b["diff"], cwd=str(REPO), capture_output=True, text=True)
        if apply.returncode != 0:
            rep["decision"] = "reject"; rep["reason"] = f"git apply failed: {apply.stderr[:200]}"
            await audit(action, gov, ok=False); return rep
        token = await _record_version(domain, reverse)
        restarted = _restart_core()
        live = _eval("http://127.0.0.1:8000", GATE_SUITES)
        if not restarted or not live["ok"]:
            # auto-rollback on regression
            subprocess.run(["git", "apply"], input=reverse, cwd=str(REPO), capture_output=True, text=True)
            _restart_core()
            rep["decision"] = "rolled_back"; rep["reason"] = "live eval red after promote -> auto-rollback"
            rep["live"] = live
            await audit(action, gov, ok=False); return rep

        rep["decision"] = "promote"; rep["rollback_token"] = token; rep["live"] = live
        await audit(action, gov, ok=True)
        return rep
    finally:
        builder.drop_worktree(wt)


async def rollback(token: str) -> dict:
    patch = Path(f"/home/jarvis/noir/.worktrees/{token}.patch")
    if not patch.exists():
        return {"ok": False, "error": "unknown rollback token"}
    r = subprocess.run(["git", "apply"], input=patch.read_text(), cwd=str(REPO),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"ok": False, "error": f"apply failed: {r.stderr[:200]}"}
    _restart_core()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute("UPDATE si_versions SET active=0 WHERE rollback_token=?", (token,))
        await db.commit()
    return {"ok": True, "rolled_back": token}


if __name__ == "__main__":
    # Run as a STANDALONE process (not inside the core it restarts):
    #   python -m app.core.realimprove build "<intent>"
    #   python -m app.core.realimprove rollback <token>
    import asyncio
    import json as _json

    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        print(_json.dumps(asyncio.run(build_real(sys.argv[2])), ensure_ascii=False, indent=2))
    elif len(sys.argv) >= 3 and sys.argv[1] == "rollback":
        print(_json.dumps(asyncio.run(rollback(sys.argv[2])), ensure_ascii=False))
    else:
        print("usage: python -m app.core.realimprove build '<intent>' | rollback <token>")
