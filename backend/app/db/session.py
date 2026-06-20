"""aiosqlite access + schema application (08_conventions §6/§9)."""
from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.config import settings

_SCHEMA = Path(__file__).with_name("schema.sql")


async def init_db() -> None:
    settings.ensure_dirs()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(_SCHEMA.read_text())
        await db.commit()


async def connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(settings.sqlite_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON;")
    return db
