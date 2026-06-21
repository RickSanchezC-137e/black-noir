"""Daily budget ledger for the self-improvement contour (09_self_improvement.md §9).

Caps tokens / requests / builder-runs / adopt-clones per UTC day. When any cap is hit
the loop pauses (a Governor kill-switch auto-trigger for anomalous spend). Persisted in
si_budget_ledger so a restart does not reset the night's spend.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.config import settings


def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _con():
    return sqlite3.connect(settings.sqlite_path)


def _row(con) -> sqlite3.Row:
    con.row_factory = sqlite3.Row
    d = _day()
    r = con.execute("SELECT * FROM si_budget_ledger WHERE day=?", (d,)).fetchone()
    if not r:
        con.execute(
            "INSERT INTO si_budget_ledger(day,tokens_limit,requests_limit) VALUES(?,?,?)",
            (d, settings.selfimprove_daily_budget_tokens, settings.selfimprove_daily_budget_requests))
        con.commit()
        r = con.execute("SELECT * FROM si_budget_ledger WHERE day=?", (d,)).fetchone()
    return r


def status() -> dict:
    con = _con()
    r = _row(con)
    out = dict(r)
    con.close()
    out["remaining_tokens"] = max(0, out["tokens_limit"] - out["tokens_used"])
    out["over"] = _over(out)
    return out


def _over(r: dict) -> bool:
    return (r["tokens_used"] >= r["tokens_limit"]
            or r["requests_used"] >= r["requests_limit"]
            or r["builder_runs"] >= settings.selfimprove_max_builder_runs
            or r["adopt_clones"] >= settings.selfimprove_max_adopt_clones)


def can_spend() -> tuple[bool, str]:
    r = status()
    if r["paused"]:
        return False, "loop paused"
    if r["over"]:
        return False, "daily budget reached"
    return True, "ok"


def charge(*, tokens: int = 0, requests: int = 1, builder: int = 0, clones: int = 0) -> None:
    con = _con()
    _row(con)
    con.execute(
        "UPDATE si_budget_ledger SET tokens_used=tokens_used+?, requests_used=requests_used+?,"
        " builder_runs=builder_runs+?, adopt_clones=adopt_clones+? WHERE day=?",
        (tokens, requests, builder, clones, _day()))
    con.commit()
    # auto-pause on cap (anomalous-spend kill-switch trigger)
    r = _row(con)
    if _over(dict(r)) and not r["paused"]:
        con.execute("UPDATE si_budget_ledger SET paused=1 WHERE day=?", (_day(),))
        con.commit()
    con.close()


def pause(on: bool = True) -> None:
    con = _con()
    _row(con)
    con.execute("UPDATE si_budget_ledger SET paused=? WHERE day=?", (1 if on else 0, _day()))
    con.commit()
    con.close()
