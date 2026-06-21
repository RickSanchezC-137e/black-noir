"""Self-analysis (introspection) — C4, 09_self_improvement.md.

Mines the system's OWN telemetry — Governor failures (agent_log), module error
logs, failed tasks — turns the strongest signals into ranked, grounded
improvement hypotheses and feeds them into the existing self-improvement queue
(selfimprove.scout). The night contour can then run the top hypothesis through
the normal Builder→Eval→Governor→promote pipeline.

This makes self-improvement *targeted* (driven by what actually breaks) instead
of blind. It never weakens safety: it only proposes hypotheses; promotion still
goes through the unchanged eval gate + Governor.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from app.config import settings
from app.core import selfimprove

_TABLE = (
    "CREATE TABLE IF NOT EXISTS si_self_analysis("
    "id TEXT PRIMARY KEY, created_at TEXT, report TEXT)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _gather(db: aiosqlite.Connection) -> list[dict]:
    """Collect ranked telemetry findings (highest count first)."""
    db.row_factory = aiosqlite.Row
    findings: list[dict] = []

    # 1) Governor / tool execution failures (ok=0) grouped by module.tool.
    #    Exclude synthetic canary/test entries — they are gate self-checks, not real defects.
    cur = await db.execute(
        "SELECT module, tool, COUNT(*) n, MAX(reason) reason FROM agent_log"
        " WHERE ok=0 AND module NOT IN ('test','canary') GROUP BY module, tool"
        " ORDER BY n DESC LIMIT 8")
    for r in await cur.fetchall():
        findings.append({"kind": "exec_failure", "module": r["module"] or "core",
                         "signal": f"{r['module']}.{r['tool']}", "count": r["n"],
                         "sample": (r["reason"] or "")[:160]})

    # 2) Module error-level logs grouped by module
    try:
        cur = await db.execute(
            "SELECT module_id, COUNT(*) n, MAX(event) ev, MAX(payload) pl"
            " FROM core__module_logs WHERE level='error' GROUP BY module_id ORDER BY n DESC LIMIT 8")
        for r in await cur.fetchall():
            findings.append({"kind": "module_error", "module": r["module_id"],
                             "signal": f"{r['module_id']} error-logs", "count": r["n"],
                             "sample": (f"{r['ev']} {r['pl'] or ''}")[:160]})
    except aiosqlite.OperationalError:
        pass

    # 3) Failed tasks
    cur = await db.execute(
        "SELECT kind, COUNT(*) n, MAX(error) err FROM tasks WHERE status='error' GROUP BY kind ORDER BY n DESC LIMIT 5")
    for r in await cur.fetchall():
        findings.append({"kind": "task_error", "module": "orchestrator",
                         "signal": f"task:{r['kind']}", "count": r["n"], "sample": (r["err"] or "")[:160]})

    findings.sort(key=lambda f: f["count"], reverse=True)
    return findings


def _intent(f: dict) -> str:
    # STABLE intent → stable scout signature → no near-duplicate hypotheses across runs
    return f"harden {f['module']}: recurring {f['kind']} on {f['signal']}"


async def analyze(top: int = 3, enqueue: bool = True) -> dict:
    """Gather telemetry, rank findings, enqueue grounded hypotheses, persist a report."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(_TABLE)
        await db.commit()
        findings = await _gather(db)

        enqueued = []
        if enqueue:
            for f in findings[:top]:
                intent = _intent(f)
                try:
                    sc = await selfimprove.scout(
                        intent, domain=f["module"], target_module=f["module"],
                        source="self_analysis", kind="capability")
                    enqueued.append({"intent": intent, "module": f["module"],
                                     "hypothesis": sc.get("id") or sc.get("hypothesis_id"),
                                     "status": sc.get("status") or sc.get("decision") or "queued"})
                except Exception as e:  # noqa: BLE001 — never let one bad signal break the report
                    enqueued.append({"intent": intent, "module": f["module"], "error": str(e)})

        report = {
            "generated_at": _now(),
            "signals": {"total_findings": len(findings),
                        "exec_failures": sum(1 for f in findings if f["kind"] == "exec_failure"),
                        "module_errors": sum(1 for f in findings if f["kind"] == "module_error"),
                        "task_errors": sum(1 for f in findings if f["kind"] == "task_error")},
            "findings": findings[:10],
            "enqueued": enqueued,
        }
        await db.execute("INSERT INTO si_self_analysis(id,created_at,report) VALUES(?,?,?)",
                         (str(uuid.uuid4()), report["generated_at"], json.dumps(report, ensure_ascii=False)))
        await db.commit()
    return report


async def run_top(base: str | None = None) -> dict:
    """Run the single highest-signal finding through the full self-improvement cycle."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        findings = await _gather(db)
    if not findings:
        return {"ran": False, "reason": "no negative signals — nothing to improve"}
    f = findings[0]
    res = await selfimprove.run_once(_intent(f), target_module=f["module"], domain=f["module"], base=base)
    return {"ran": True, "finding": f, "result": res}


async def latest() -> dict:
    """Latest persisted self-analysis report (for the desktop Systems card)."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "SELECT report FROM si_self_analysis ORDER BY created_at DESC LIMIT 1")
            row = await cur.fetchone()
        except aiosqlite.OperationalError:
            return {}
    return json.loads(row["report"]) if row else {}
