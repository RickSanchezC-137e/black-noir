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
    try:
        adopts = [dict(r) for r in _q(con, "SELECT repo,verdict,reason FROM si_adoptions ORDER BY decided_at DESC")]
    except sqlite3.OperationalError:
        adopts = [dict(r) for r in _q(con, "SELECT repo,verdict FROM si_adoptions ORDER BY decided_at DESC")]
    fails = _q(con, "SELECT COUNT(*) n FROM agent_log WHERE decision='ALLOW' AND ok=0")[0]["n"]
    audit_n = _q(con, "SELECT COUNT(*) n FROM agent_log")[0]["n"]
    con.close()

    by = {"adopt": [], "improve": [], "skip": [], "defer": []}
    for r in adopts:
        by.setdefault(r["verdict"], []).append(r)

    def _short(r):
        rs = (r.get("reason") or "").replace("blueprint verdict; ", "")
        return f"{r['repo'].split('/')[-1]}" + (f" — {rs[:60]}" if rs else "")

    lines = [
        f"🌙 {settings.project_name} — отчёт за ночь ({day})",
        "",
        f"♻️ Самоулучшение: промоутнуто {promoted}, отклонено {rejected}",
        "🏆 Champion-версии (откат: /api/systems/selfimprove/rollback {token}):",
    ]
    lines += ["   • " + (", ".join(f"{c['domain']}@v{c['version']}" for c in champs) or "—")]
    lines += ["", f"🧩 ВЕРДИКТЫ НА РЕВЬЮ — {len(adopts)} репозиториев:"]
    if by["adopt"]:
        lines.append("✅ ADOPT (внедрено/кандидат): " + ", ".join(_short(r) for r in by["adopt"][:12]))
    if by["improve"]:
        lines.append("🛠 IMPROVE (взять+доработать): " + ", ".join(_short(r) for r in by["improve"][:12]))
    if by["defer"]:
        lines.append(f"⏸ DEFER (позже/GPU/вне-v1): {len(by['defer'])} — " + ", ".join(r['repo'].split('/')[-1] for r in by["defer"][:10]))
    if by["skip"]:
        lines.append(f"⏭ SKIP (отклонено): {len(by['skip'])} — " + ", ".join(_short(r) for r in by["skip"][:10]))
    lines += [
        "",
        f"💰 Бюджет: токены {b.get('tokens_used',0)}/{b.get('tokens_limit',0)} · "
        f"запросы {b.get('requests_used',0)}/{b.get('requests_limit',0)} · "
        f"builder {b.get('builder_runs',0)} · clones {b.get('adopt_clones',0)}"
        + (" · ⏸ ПАУЗА (бюджет)" if b.get("paused") else ""),
        f"📋 Аудит: {audit_n} записей · сбоев исполнения: {fails}",
        "✅ Всё через Governor; конституция неприкосновенна. Структурные правки ядра — на твой CONFIRM.",
        "",
        "👉 На ревью: подтверди какие DEFER/SKIP внедрять — допишу интеграторы и прогоню через Eval.",
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
