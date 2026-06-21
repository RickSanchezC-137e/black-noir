"""/api/visual — content channel for the desktop ВИЗУАЛ panel.

The core (or its tools) POSTs what it wants to show the owner — an image
(url/data-uri), a chart (series), or text. The desktop polls GET and renders it.
Live host-metric graphs are drawn client-side; this channel is for pushed content.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/visual")

_TABLE = ("CREATE TABLE IF NOT EXISTS visual_state("
          "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, payload TEXT)")


class VisualIn(BaseModel):
    kind: str = "image"   # image | chart | text
    payload: str          # image: url/data-uri; chart: JSON series; text: markdown


@router.get("")
async def latest():
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(_TABLE)
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT ts,kind,payload FROM visual_state ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
    if not row:
        return {"kind": "none", "payload": "", "ts": None}
    return {"kind": row["kind"], "payload": row["payload"], "ts": row["ts"]}


@router.post("")
async def push(body: VisualIn):
    ts = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(_TABLE)
        await db.execute("INSERT INTO visual_state(ts,kind,payload) VALUES(?,?,?)",
                         (ts, body.kind, body.payload))
        await db.commit()
    return {"ok": True, "kind": body.kind, "ts": ts}
