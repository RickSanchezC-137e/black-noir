"""owner_profile — Owner Profile / Self-Model (C2), real module (no stub).

observe -> reconcile -> recall, plus a personal-hypothesis loop. Private namespace
m_owner_profile__ in the core SQLite + private Chroma collection `owner_profile`
(shared all-MiniLM-L6-v2 embedder). Sensitive domains (finance/health) are audited
by the Governor on every call. Profile never leaves by default (no network).

App/db imports are LAZY so the Factory sandbox contract test stays hermetic.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

NS = "m_owner_profile__"
COLLECTION = "owner_profile"
SENSITIVE = {"finance", "health"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> str:
    from app.config import settings
    return str(settings.sqlite_path)


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _ensure_schema() -> None:
    con = _con()
    con.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {NS}profile_fact(
          id TEXT PRIMARY KEY, domain TEXT, key TEXT, value TEXT,
          confidence REAL, source TEXT, observed_at TEXT,
          expires_at TEXT, superseded_by TEXT);
        CREATE TABLE IF NOT EXISTS {NS}schedule_item(
          id TEXT PRIMARY KEY, title TEXT, start TEXT, end TEXT,
          recurrence TEXT, source TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS {NS}finance_item(
          id TEXT PRIMARY KEY, kind TEXT, amount REAL, currency TEXT,
          category TEXT, period TEXT, planned INTEGER, observed_at TEXT);
        CREATE TABLE IF NOT EXISTS {NS}health_metric(
          id TEXT PRIMARY KEY, metric TEXT, value REAL, unit TEXT,
          observed_at TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS {NS}goal(
          id TEXT PRIMARY KEY, title TEXT, horizon TEXT, progress REAL,
          status TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS {NS}profile_hypothesis(
          id TEXT PRIMARY KEY, statement TEXT, status TEXT, metric TEXT,
          evidence TEXT, created_at TEXT, verdict TEXT);
        """
    )
    con.commit()
    con.close()


def _collection():
    from app.core.memory import get_chroma, get_embedder
    get_embedder()
    return get_chroma().get_or_create_collection(COLLECTION)


def _embed(texts: list[str]):
    from app.core.memory import get_embedder
    return get_embedder().encode(texts).tolist()


# ---- tools ----------------------------------------------------------------

def _observe(args: dict) -> dict:
    _ensure_schema()
    fid = str(uuid.uuid4())
    domain = args.get("domain", "identity")
    key = args.get("key", "note")
    value = args["value"]
    conf = float(args.get("confidence", 0.6))
    src = args.get("source", "chat")
    con = _con()
    con.execute(
        f"INSERT INTO {NS}profile_fact(id,domain,key,value,confidence,source,observed_at)"
        f" VALUES(?,?,?,?,?,?,?)", (fid, domain, key, value, conf, src, _now()))
    con.commit()
    con.close()
    text = f"[{domain}/{key}] {value}"
    _collection().add(ids=[fid], embeddings=_embed([text]), documents=[text],
                      metadatas=[{"domain": domain, "key": key, "confidence": conf,
                                  "source": src, "observed_at": _now()}])
    return {"id": fid, "domain": domain, "key": key, "stored": True}


def _get(args: dict) -> dict:
    _ensure_schema()
    query = args.get("query", "")
    domain = args.get("domain")
    where = {"domain": domain} if domain else None
    try:
        res = _collection().query(query_embeddings=_embed([query or domain or ""]),
                                  n_results=args.get("k", 5), where=where)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        hits = [{"text": d, **(m or {})} for d, m in zip(docs, metas)]
    except Exception:  # noqa: BLE001
        hits = []
    return {"query": query, "domain": domain, "hits": hits}


def _reconcile(_args: dict) -> dict:
    """Confirm/supersede/conflict across facts sharing (domain,key)."""
    _ensure_schema()
    con = _con()
    rows = con.execute(
        f"SELECT id,domain,key,value,confidence,observed_at FROM {NS}profile_fact"
        f" WHERE superseded_by IS NULL ORDER BY domain,key,observed_at").fetchall()
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["domain"], r["key"]), []).append(r)
    confirmed = superseded = conflicts = 0
    for _, items in groups.items():
        if len(items) < 2:
            continue
        latest = items[-1]
        for older in items[:-1]:
            if older["value"] == latest["value"]:
                new_conf = min(1.0, (latest["confidence"] or 0.6) + 0.1)
                con.execute(f"UPDATE {NS}profile_fact SET confidence=? WHERE id=?",
                            (new_conf, latest["id"]))
                con.execute(f"UPDATE {NS}profile_fact SET superseded_by=? WHERE id=?",
                            (latest["id"], older["id"]))
                confirmed += 1
                superseded += 1
            else:
                con.execute(f"UPDATE {NS}profile_fact SET superseded_by=? WHERE id=?",
                            (latest["id"], older["id"]))
                superseded += 1
                conflicts += 1
    con.commit()
    con.close()
    return {"confirmed": confirmed, "superseded": superseded, "conflicts": conflicts}


def _hyp_add(args: dict) -> dict:
    _ensure_schema()
    hid = str(uuid.uuid4())
    con = _con()
    con.execute(
        f"INSERT INTO {NS}profile_hypothesis(id,statement,status,metric,evidence,created_at,verdict)"
        f" VALUES(?,?,?,?,?,?,?)",
        (hid, args["statement"], "open", args.get("metric", ""), "[]", _now(), None))
    con.commit()
    con.close()
    return {"id": hid, "statement": args["statement"], "status": "open"}


def _hyp_test(args: dict) -> dict:
    """Gather evidence via RAG over profile facts -> verdict."""
    _ensure_schema()
    hid = args["id"]
    con = _con()
    row = con.execute(f"SELECT statement FROM {NS}profile_hypothesis WHERE id=?", (hid,)).fetchone()
    if not row:
        con.close()
        return {"id": hid, "error": "hypothesis not found"}
    statement = row["statement"]
    ev = _get({"query": statement, "k": 5})["hits"]
    toks = {w.lower().strip(".,!?") for w in statement.split() if len(w) > 4}
    support = [h for h in ev if toks & {w.lower().strip(".,!?") for w in h["text"].split()}]
    verdict = "supported" if support else ("inconclusive" if ev else "no_evidence")
    import json
    con.execute(f"UPDATE {NS}profile_hypothesis SET status=?, verdict=?, evidence=? WHERE id=?",
                ("tested", verdict, json.dumps([h["text"] for h in support], ensure_ascii=False), hid))
    con.commit()
    con.close()
    return {"id": hid, "statement": statement, "verdict": verdict,
            "evidence": [h["text"] for h in support]}


def _health_log(args: dict) -> dict:
    _ensure_schema()
    mid = str(uuid.uuid4())
    con = _con()
    con.execute(f"INSERT INTO {NS}health_metric(id,metric,value,unit,observed_at,source)"
                f" VALUES(?,?,?,?,?,?)",
                (mid, args["metric"], float(args.get("value", 0)), args.get("unit", ""),
                 _now(), args.get("source", "manual")))
    con.commit()
    con.close()
    return {"id": mid, "metric": args["metric"], "sensitive": True}


def _health_summary(_args: dict) -> dict:
    _ensure_schema()
    con = _con()
    rows = con.execute(f"SELECT metric, COUNT(*) n, AVG(value) avg FROM {NS}health_metric"
                       f" GROUP BY metric").fetchall()
    con.close()
    return {"sensitive": True, "metrics": [dict(r) for r in rows]}


def _schedule_get(args: dict) -> dict:
    _ensure_schema()
    con = _con()
    rows = con.execute(f"SELECT id,title,start,end,status FROM {NS}schedule_item"
                       f" ORDER BY start LIMIT ?", (args.get("limit", 20),)).fetchall()
    con.close()
    return {"items": [dict(r) for r in rows]}


def _schedule_plan(args: dict) -> dict:
    _ensure_schema()
    sid = str(uuid.uuid4())
    con = _con()
    con.execute(f"INSERT INTO {NS}schedule_item(id,title,start,end,recurrence,source,status)"
                f" VALUES(?,?,?,?,?,?,?)",
                (sid, args["title"], args.get("start", ""), args.get("end", ""),
                 args.get("recurrence", ""), "planner", "planned"))
    con.commit()
    con.close()
    return {"id": sid, "title": args["title"], "status": "planned"}


_TOOLS = {
    "profile.observe": _observe, "profile.get": _get, "profile.reconcile": _reconcile,
    "profile.hypothesis.add": _hyp_add, "profile.hypothesis.test": _hyp_test,
    "health.log": _health_log, "health.summary": _health_summary,
    "schedule.get": _schedule_get, "schedule.plan": _schedule_plan,
}


async def call(tool: str, args: dict) -> dict:
    fn = _TOOLS.get(tool)
    if not fn:
        raise ValueError(f"unknown tool {tool}")
    return fn(args)


async def health() -> dict:
    return {"ok": True, "namespace": NS, "collection": COLLECTION}
