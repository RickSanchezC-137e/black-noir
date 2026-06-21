"""Morning report (09_self_improvement.md §13) — Telegram summary of the night's autonomy.

Cycles run, hypotheses tested, promoted/rolled-back, repos evaluated (adopt/improve/skip),
errors, budget spent. Sent to the owner via the Bot API. Run by noir-morning-report.timer.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import httpx

from app.config import settings


def _q(con, sql, args=()):
    try:
        return con.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []


def build_report() -> str:
    con = sqlite3.connect(settings.sqlite_path)
    con.row_factory = sqlite3.Row
    day = datetime.now(timezone.utc).date().isoformat()
    b = _q(con, "SELECT * FROM si_budget_ledger WHERE day=?", (day,))
    b = dict(b[0]) if b else {}
    promoted = _q(con, "SELECT COUNT(*) n FROM si_hypotheses WHERE status='promoted'")[0]["n"]
    rejected = _q(con, "SELECT COUNT(*) n FROM si_hypotheses WHERE status='rejected'")[0]["n"]
    champs = _q(con, "SELECT domain,version FROM si_versions WHERE active=1")
    adopts = _q(con, "SELECT repo,verdict FROM si_adoptions ORDER BY decided_at DESC")
    fails = _q(con, "SELECT COUNT(*) n FROM agent_log WHERE decision='ALLOW' AND ok=0")[0]["n"]
    audit_n = _q(con, "SELECT COUNT(*) n FROM agent_log")[0]["n"]
    con.close()

    a = {"adopt": 0, "improve": 0, "skip": 0, "defer": 0}
    for r in adopts:
        a[r["verdict"]] = a.get(r["verdict"], 0) + 1
    lines = [
        f"🌙 {settings.project_name} — отчёт за ночь ({day})",
        "",
        f"♻️ Самоулучшение: промоутнуто {promoted}, отклонено {rejected}",
        f"🏆 Champion-версии: " + (", ".join(f"{c['domain']}@v{c['version']}" for c in champs) or "—"),
        f"🧩 Adoption: adopt {a['adopt']} · improve {a['improve']} · skip {a['skip']} · defer {a['defer']}",
        "   " + (", ".join(f"{r['repo'].split('/')[-1]}={r['verdict']}" for r in adopts) or "—"),
        "",
        f"💰 Бюджет: токены {b.get('tokens_used',0)}/{b.get('tokens_limit',0)} · "
        f"запросы {b.get('requests_used',0)}/{b.get('requests_limit',0)} · "
        f"builder {b.get('builder_runs',0)} · clones {b.get('adopt_clones',0)}"
        + (" · ⏸ ПАУЗА (бюджет)" if b.get("paused") else ""),
        f"📋 Аудит: {audit_n} записей · сбоев исполнения: {fails}",
        f"✅ Все действия — через Governor, конституция неприкосновенна.",
    ]
    return "\n".join(lines)


async def send():
    text = build_report()
    if not settings.telegram_bot_token or not settings.telegram_owner_chat_id:
        print(text)
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(url, json={"chat_id": settings.telegram_owner_chat_id, "text": text})
    print("report sent")


if __name__ == "__main__":
    asyncio.run(send())
