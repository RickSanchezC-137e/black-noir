"""Memory layer (CANON §10, 03_memory.md).

Episodic -> SQLite (this module). Semantic/RAG -> ChromaDB with local all-MiniLM-L6-v2
embeddings (wired in step 6.2 memory; lazy-loaded to keep core startup light).
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.config import settings

_chroma = None
_embedder = None
_collection = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_chroma():
    """Lazy import of heavy deps (chromadb + sentence-transformers)."""
    global _chroma, _embedder, _collection
    if _collection is not None:
        return _collection
    import chromadb
    from sentence_transformers import SentenceTransformer

    _embedder = SentenceTransformer(settings.embedding_model)
    _chroma = chromadb.PersistentClient(path=str(settings.chroma_dir))
    _collection = _chroma.get_or_create_collection("memory_longterm")
    return _collection


async def remember(text: str, *, source: str = "chat", role: str = "user") -> str:
    """Write episodic row (SQLite) + semantic vector (Chroma). Returns chroma_id."""
    cid = f"mem-{int(datetime.now(timezone.utc).timestamp()*1000)}"
    try:
        col = _ensure_chroma()
        emb = _embedder.encode([text]).tolist()
        col.add(ids=[cid], embeddings=emb, documents=[text],
                metadatas=[{"ts": _now(), "source": source, "role": role}])
    except Exception:  # noqa: BLE001 — semantic layer optional at this stage
        cid = ""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO episodic(ts,source,role,content,chroma_id) VALUES(?,?,?,?,?)",
            (_now(), source, role, text, cid),
        )
        await db.commit()
    return cid


async def recall(query: str, k: int = 5) -> list[dict]:
    """Semantic recall via Chroma; falls back to SQLite substring if Chroma unavailable."""
    try:
        col = _ensure_chroma()
        emb = _embedder.encode([query]).tolist()
        res = col.query(query_embeddings=emb, n_results=k)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        return [{"content": d, **(m or {})} for d, m in zip(docs, metas)]
    except Exception:  # noqa: BLE001
        async with aiosqlite.connect(settings.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT content,source,role,ts FROM episodic WHERE content LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{query}%", k),
            )
            return [dict(r) for r in await cur.fetchall()]
