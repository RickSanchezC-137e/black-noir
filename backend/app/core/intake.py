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
        cat = "good" if rep.get("verdict") in ("adopt", "defer") else "bad"
        reason = rep.get("reason", "") or rep.get("verdict", "")
        status = {"good": "accepted", "bad": "rejected"}.get(cat, "new")
        await _store_idea(f"[repo] {repo} — {reason}", status)
        routed = False
        if cat == "good":
            from app.core import selfimprove
            await selfimprove.scout(f"рассмотреть репозиторий {repo} к внедрению",
                                    domain="modules", target_module="mcp_fs", source="intake")
            routed = True
        return {"category": cat, "reason": reason, "summary": rep.get("verdict"), "routed": routed}

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
