"""Intake & triage (C4) — ingest anything the owner throws in (repo / YouTube /
reel / link / file / text), study it, sort it (good/bad/review), and route the
worthy ones into the self-improvement contour.

Repos go through the real adoption pipeline (license+security+eval). Everything
else is classified by the core from available metadata (e.g. YouTube title) —
deep video understanding is future work (needs C3 vision/transcription).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

import aiosqlite
import httpx

from app.config import settings
from app.core import claude

_TRIAGE_SYS = (
    "Ты — модуль разбора входящего системы Black Noir. Тебе дают элемент (источник + "
    "значение/заголовок). Оцени, полезен ли он для системы или владельца и стоит ли "
    "отправлять его в контур самоулучшения (C4). Верни СТРОГО JSON без пояснений: "
    '{"category":"good|bad|review","reason":"кратко","summary":"о чём это","self_improve":true|false}.'
)


async def _yt_context(url: str) -> str:
    """Best-effort YouTube CONTENT context: title+author (oEmbed) + the video's own
    description + transcript if the library is available — so we classify by content,
    not just the title. Falls back gracefully."""
    parts = []
    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
            if r.status_code == 200:
                d = r.json(); parts.append(f"заголовок: {d.get('title','')} — {d.get('author_name','')}")
            pg = await c.get(url)
            if pg.status_code == 200:
                m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', pg.text)
                if m:
                    try:
                        desc = json.loads('"' + m.group(1) + '"')
                    except Exception:  # noqa: BLE001
                        desc = m.group(1)
                    if desc.strip():
                        parts.append("описание: " + desc[:1500])
    except Exception:  # noqa: BLE001
        pass
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        import urllib.parse as up
        vid = up.parse_qs(up.urlparse(url).query).get("v", [""])[0] or url.rsplit("/", 1)[-1]
        tr = YouTubeTranscriptApi.get_transcript(vid, languages=["ru", "en"])
        txt = " ".join(x["text"] for x in tr)[:2000]
        if txt.strip():
            parts.append("субтитры: " + txt)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(parts)


async def _classify(source: str, value: str) -> dict:
    ctx = value
    if source in ("youtube", "reel", "video") and value.startswith("http"):
        c = await _yt_context(value)
        if c:
            ctx = f"{value}\n{c}"
    try:
        raw, _, _ = await claude.chat_as(_TRIAGE_SYS, f"источник: {source}\nэлемент: {ctx}")
        d = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return {"category": d.get("category", "review"), "reason": d.get("reason", ""),
                "summary": d.get("summary", ""), "self_improve": bool(d.get("self_improve"))}
    except Exception as e:  # noqa: BLE001
        return {"category": "review", "reason": f"не удалось классифицировать ({e})", "summary": "", "self_improve": False}


async def _store_idea(text: str, status: str) -> str:
    iid = str(uuid.uuid4())
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute("INSERT INTO ideas(id,text,status,created_at) VALUES(?,?,?,?)",
                         (iid, text, status, datetime.now(timezone.utc).isoformat()))
        await db.commit()
    return iid


async def triage(source: str, value: str) -> dict:
    """Study one incoming item, sort it, and route worthy items to self-improvement."""
    value = (value or "").strip()
    if not value:
        return {"category": "bad", "reason": "пусто"}

    # repos → real adoption analysis (license + security + eval)
    if source == "repo" or "github.com" in value:
        from app.core import adoption
        repo = value.replace("https://github.com/", "").replace(".git", "").strip("/")
        rep = await adoption.adopt(repo, capability="", cluster="C6")
        v = rep.get("verdict")
        # adopt = готов/внедрён → хорошие; defer = совместим, ждёт обёртку → на разборе; skip = плохие
        cat = {"adopt": "good", "defer": "review"}.get(v, "bad")
        reason = rep.get("reason", "") or v
        status = {"good": "accepted", "review": "new", "bad": "rejected"}.get(cat, "new")
        await _store_idea(f"[repo] {repo} — {reason}", status)
        routed = False
        if cat in ("good", "review"):
            from app.core import selfimprove, module_factory
            await selfimprove.scout(f"рассмотреть репозиторий {repo} к внедрению",
                                    domain="modules", target_module="mcp_fs", source="intake")
            module_factory.request_build(kind="repo", repo=repo, cluster="C6")  # фабрика соберёт обёртку off-core
            routed = True
        return {"category": cat, "reason": reason, "summary": v, "routed": routed}

    # everything else → core classification from available metadata
    c = await _classify(source, value)
    status = {"good": "accepted", "bad": "rejected"}.get(c["category"], "new")
    await _store_idea(f"[{source}] {value}" + (f" — {c['summary']}" if c.get("summary") else ""), status)
    routed = False
    if c["category"] == "good" and c.get("self_improve"):
        from app.core import selfimprove
        await selfimprove.scout(f"из входящего ({source}): {c.get('summary') or value}",
                                domain="modules", target_module="mcp_fs", source="intake")
        routed = True
    return {"category": c["category"], "reason": c["reason"], "summary": c.get("summary"), "routed": routed}


# ---------------- deep per-item analysis (detail panel + readiness) ----------------
_DETAIL = ("CREATE TABLE IF NOT EXISTS idea_detail(idea_id TEXT PRIMARY KEY, progress INTEGER,"
           " data TEXT, updated_at TEXT)")

_DEEP_SYS = (
    "Ты — аналитик входящего для Black Noir. По данным ниже дай развёрнутый разбор. "
    "Верни СТРОГО JSON: {\"what\":\"что это и что делает\",\"why\":\"зачем/польза владельцу или системе\","
    "\"structure\":\"кратко об устройстве\",\"fit_cluster\":\"C1..C6\",\"fit_reason\":\"куда и как интегрировать\","
    "\"overlaps\":\"какой наш модуль дополняет/заменяет или 'нет'\",\"recommendation\":\"внедрить|на доработку|отклонить + почему\","
    "\"test_plan\":\"как проверить перед внедрением\"}."
)


def _parse_idea(text: str) -> tuple[str, str]:
    src, val = "text", text
    if text.startswith("[") and "]" in text:
        src = text[1:text.index("]")]
        val = text[text.index("]") + 1:].split(" — ")[0].strip()
    return src, val


async def analyze_detail(idea_id: str) -> dict:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT id,text FROM ideas WHERE id=?", (idea_id,))).fetchone()
    if not row:
        return {"error": "idea not found"}
    src, val = _parse_idea(row["text"])
    data: dict = {"source": src, "value": val}
    lic = sec = None
    structure = readme = ""
    if src == "repo" or "github.com" in val:
        from app.core import adoption
        repo = val.replace("https://github.com/", "").replace(".git", "").strip("/")
        try:
            d = adoption.clone(repo)
            lic = adoption.license_scan(d); sec = adoption.security_scan(d)
            structure = ", ".join(sorted(p.name for p in d.iterdir())[:25])
            for n in ("README.md", "README.rst", "readme.md", "Readme.md"):
                if (d / n).exists():
                    readme = (d / n).read_text(errors="ignore")[:3000]; break
        except Exception as e:  # noqa: BLE001
            data["clone_error"] = str(e)
    elif src in ("youtube", "reel", "video") and val.startswith("http"):
        readme = await _yt_context(val)

    from app.core.modules_runtime import manager
    mods = ", ".join(f"{m['name']}({m.get('cluster')})" for m in manager.list())
    ctx = (f"источник: {src}\nэлемент: {val}\nструктура: {structure}\n"
           f"лицензия: {lic}\nбезопасность: {(sec or {}).get('safe') if sec else '-'}\n"
           f"наши модули: {mods}\nREADME/контекст:\n{readme}")
    try:
        raw, _, _ = await claude.chat_as(_DEEP_SYS, ctx)
        deep = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception as e:  # noqa: BLE001
        deep = {"what": f"(не удалось разобрать: {e})"}
    data.update(deep)
    if lic:
        data["license"] = lic.get("license"); data["license_ok"] = lic.get("compatible")
    if sec:
        data["security_ok"] = sec.get("safe")

    # readiness 0..100
    prog = 0
    if data.get("what") and not str(data.get("what")).startswith("(не"):
        prog += 40
    if lic is not None:
        prog += 20 if data.get("license_ok") else 0
        prog += 20 if data.get("security_ok") else 0
    else:
        prog += 30  # non-repo: no license/security gates
    if str(data.get("recommendation", "")).startswith("внедрить"):
        prog += 20
    prog = min(100, prog)

    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(_DETAIL)
        await db.execute("INSERT INTO idea_detail(idea_id,progress,data,updated_at) VALUES(?,?,?,?)"
                         " ON CONFLICT(idea_id) DO UPDATE SET progress=excluded.progress,"
                         " data=excluded.data, updated_at=excluded.updated_at",
                         (idea_id, prog, json.dumps(data, ensure_ascii=False),
                          datetime.now(timezone.utc).isoformat()))
        await db.commit()
    return {"idea_id": idea_id, "progress": prog, "data": data}


async def get_detail(idea_id: str) -> dict:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(_DETAIL)
        idea = await (await db.execute("SELECT id,text,status,score,created_at FROM ideas WHERE id=?", (idea_id,))).fetchone()
        det = await (await db.execute("SELECT progress,data,updated_at FROM idea_detail WHERE idea_id=?", (idea_id,))).fetchone()
    if not idea:
        return {"error": "idea not found"}
    out = {"idea": dict(idea), "progress": 0, "data": None}
    if det:
        out["progress"] = det["progress"]; out["data"] = json.loads(det["data"]); out["updated_at"] = det["updated_at"]
    return out
