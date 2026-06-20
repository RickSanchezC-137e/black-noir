"""Self-improvement loop (C4, 09_self_improvement.md).

Scout -> queue (dedup) -> Factory (sandbox) -> Eval (gate) -> Governor+quality_gate ->
Champion (version + 1-step rollback). v1 uses a cheap no-Claude eval gate (modules/core/
governor suites) so the loop is verifiable without token spend; promotion requires the
gate suite 100% green and safety_violations == 0 (canonical hard gate).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.config import settings
from app.core.governor import Action, audit, governor

REPO = Path("/home/jarvis/noir")
GATE_SUITES = ["core", "governor"]   # deterministic, instant, no network/Claude cost

# constitution HARD-DENY intents (cannot be self-applied)
HARD_DENY = ("disable audit", "disable logging", "weaken governor", "modify constitution",
             "bypass budget", "remove rollback", "deploy without eval")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(domain: str, kind: str, intent: str) -> str:
    return hashlib.sha256(f"{domain}|{kind}|{intent}".strip().lower().encode()).hexdigest()


def _constitution_check(intent: str) -> tuple[bool, str]:
    low = intent.lower()
    for bad in HARD_DENY:
        if bad in low:
            return False, f"HARD-DENY: '{bad}'"
    return True, "ok"


def _run_eval_gate(base: str) -> dict:
    """Run the cheap gate suites via the eval harness (challenger gate)."""
    cmd = [sys.executable, str(REPO / "eval" / "runner.py"), "--suite", *GATE_SUITES, "--base", base]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO / "eval"), timeout=180)
    out = r.stdout + r.stderr
    passed = total = 0
    for line in out.splitlines():
        if line.startswith("TOTAL:"):
            frac = line.split(":")[1].strip().split()[0]
            passed, total = (int(x) for x in frac.split("/"))
    violations = out.count("unexpected KILL violation")
    return {"passed": passed, "total": total,
            "success_rate": (passed / total) if total else 0.0,
            "safety_violations": violations, "ok": (passed == total and total > 0)}


async def scout(intent: str, *, domain: str = "modules", target_module: str = "mcp_fs",
                source: str = "logs", kind: str = "capability") -> dict:
    """Synthesize + enqueue a hypothesis (dedup by signature). Deterministic for a given intent."""
    sig = _signature(domain, kind, intent)
    hid = f"hyp_{uuid.uuid4().hex[:10]}"
    async with aiosqlite.connect(settings.sqlite_path) as db:
        dup = await (await db.execute("SELECT id FROM si_hypotheses WHERE signature=?", (sig,))).fetchone()
        if dup:
            return {"hypothesis_id": dup[0], "duplicate": True}
        await db.execute(
            "INSERT INTO si_hypotheses(id,created_at,source,kind,domain,intent,summary,evidence,"
            "impact,confidence,cost,priority,signature,contour,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hid, _now(), source, kind, domain, intent, intent, json.dumps([f"module:{target_module}"]),
             0.6, 0.6, 0.3, 0.6 * 0.6 / 0.3, sig, "structural", "queued"))
        await db.commit()
    return {"hypothesis_id": hid, "duplicate": False, "target_module": target_module}


async def run_once(intent: str, *, target_module: str = "mcp_fs", domain: str = "modules",
                   base: str = "http://127.0.0.1:8001") -> dict:
    """One full loop iteration: scout -> build -> eval gate -> governor gate -> promote/reject."""
    sc = await scout(intent, domain=domain, target_module=target_module)
    hid = sc["hypothesis_id"]

    # 1) constitution (static)
    cons_ok, cons_reason = _constitution_check(intent)

    # 2) Factory build/verify in sandbox (real contract test of the target module)
    import factory  # added to sys.path by modules_runtime
    build_ok, build_out = (False, "skipped")
    if cons_ok:
        build_ok, build_out = factory.contract_test(factory.INSTALLED / target_module)

    # 3) Eval gate (challenger): cheap suites must be 100% green, 0 safety violations.
    # Run in a worker thread: the gate eval calls back into THIS same core, so the event
    # loop must stay free to serve it (blocking here would deadlock).
    if cons_ok and build_ok:
        ev = await asyncio.to_thread(_run_eval_gate, base)
    else:
        ev = {"ok": False, "success_rate": 0.0, "safety_violations": 0, "passed": 0, "total": 0}

    # 4) Governor gate (self_modify) + quality gate
    action = Action(module="selfimprove", tool="promote", action_class="self_modify",
                    args={"hypothesis": hid, "intent": intent})
    gov = governor.authorize(action)
    # Canon §10.3/§11: structural self_modify auto-promotes when the gate passes (CONFIRM = owner
    # notified + canary rollback). DENY/KILL from Governor hard-blocks promotion.
    quality_ok = (cons_ok and build_ok and ev["ok"] and ev["safety_violations"] == 0
                  and gov.decision in ("ALLOW", "CONFIRM"))

    exp_id = f"exp_{uuid.uuid4().hex[:10]}"
    vrd_id = f"vrd_{uuid.uuid4().hex[:10]}"
    decision = "promote" if quality_ok else "reject"
    contour = "structural"

    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO si_experiments(id,hypothesis_id,domain,constitution,eval,status,started_at,finished_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (exp_id, hid, domain, json.dumps({"passed": cons_ok, "reason": cons_reason}),
             json.dumps(ev), "evaluated", _now(), _now()))
        await db.execute(
            "INSERT INTO si_verdicts(id,experiment_id,decision,contour,constitution_passed,governor,"
            "quality_gate,decided_at) VALUES(?,?,?,?,?,?,?,?)",
            (vrd_id, exp_id, decision, contour, 1 if cons_ok else 0,
             json.dumps({"decision": gov.decision, "reason": gov.reason}),
             json.dumps({"quality_ok": quality_ok, **ev}), _now()))
        await db.execute("UPDATE si_hypotheses SET status=?, experiment_id=?, verdict_id=? WHERE id=?",
                         (decision + ("d" if decision == "promote" else "ed"), exp_id, vrd_id, hid))

        rollback_token = None
        if decision == "promote":
            cur = await (await db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM si_versions WHERE domain=?", (domain,))).fetchone()
            ver = cur[0]
            rollback_token = f"rb_{domain}_v{ver}_{uuid.uuid4().hex[:6]}"
            await db.execute("UPDATE si_versions SET active=0 WHERE domain=?", (domain,))
            await db.execute(
                "INSERT INTO si_versions(domain,version,experiment_id,rollback_token,active,created_at)"
                " VALUES(?,?,?,?,?,?)", (domain, ver, exp_id, rollback_token, 1, _now()))
        await db.commit()

    await audit(action, gov, ok=(decision == "promote"))
    return {"hypothesis_id": hid, "experiment_id": exp_id, "verdict_id": vrd_id,
            "constitution": {"passed": cons_ok, "reason": cons_reason},
            "build_ok": build_ok, "eval": ev, "governor": gov.decision,
            "decision": decision, "contour": contour, "rollback_token": rollback_token}


async def rollback(token: str) -> dict:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT domain,version FROM si_versions WHERE rollback_token=?", (token,))).fetchone()
        if not row:
            return {"ok": False, "error": "unknown rollback_token"}
        domain, ver = row["domain"], row["version"]
        await db.execute("UPDATE si_versions SET active=0 WHERE domain=? AND version=?", (domain, ver))
        prev = await (await db.execute(
            "SELECT version FROM si_versions WHERE domain=? AND version<? ORDER BY version DESC LIMIT 1",
            (domain, ver))).fetchone()
        if prev:
            await db.execute("UPDATE si_versions SET active=1 WHERE domain=? AND version=?",
                             (domain, prev["version"]))
        await db.commit()
    return {"ok": True, "rolled_back": f"{domain}@v{ver}",
            "active_now": f"{domain}@v{prev['version']}" if prev else None}


async def status() -> dict:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        q = await (await db.execute(
            "SELECT status, COUNT(*) n FROM si_hypotheses GROUP BY status")).fetchall()
        champ = await (await db.execute(
            "SELECT domain,version,rollback_token FROM si_versions WHERE active=1")).fetchall()
        return {"queue": {r["status"]: r["n"] for r in q},
                "champions": [dict(r) for r in champ], "gate_suites": GATE_SUITES}
