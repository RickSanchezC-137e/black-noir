"""Council of models — fault-tolerant multi-LLM core (CANON §5 extension).

Fan out a query to every enabled provider in parallel, each with its own timeout.
Models that hang/fail/time out simply drop out (non-deciding). The survivors'
answers are synthesized into one relevant answer by Opus (best-of). Governor still
gates any resulting effect — the council only produces text.
"""
from __future__ import annotations

import asyncio
import time

from app.config import settings
from app.core import claude, providers

_SYNTH_SYS = (
    "Ты — синтезатор «Совета ИИ» ядра Black Noir. Тебе дают ответы нескольких моделей на "
    "один и тот же запрос. Сформируй ОДИН лучший ответ: возьми верное, отбрось ошибочное и "
    "противоречивое, будь краток и по-русски. Если модели заметно расходятся — одной строкой "
    "отметь, в чём консенсус и в чём расхождение."
)


async def _one(pid: str, system: str, message: str, history) -> dict:
    t0 = time.monotonic()
    try:
        txt = await asyncio.wait_for(
            providers.FNS[pid](system, message, history), timeout=settings.council_timeout_s)
        return {"provider": pid, "ok": True, "ms": int((time.monotonic() - t0) * 1000),
                "text": (txt or "").strip()}
    except Exception as e:  # noqa: BLE001 — a failed/hung member is simply non-deciding
        return {"provider": pid, "ok": False, "ms": int((time.monotonic() - t0) * 1000),
                "error": str(e)[:160]}


async def deliberate(message: str, history: list[dict] | None = None) -> dict:
    """Returns {reply, members, synth}. members = per-model {provider, ok, ms, ...}."""
    system = claude.SYSTEM.format(name=settings.project_name)
    enabled = [m["id"] for m in providers.roster() if m["enabled"] and m["active"]]
    results = await asyncio.gather(*[_one(pid, system, message, history) for pid in enabled])
    ok = [r for r in results if r["ok"] and r.get("text")]
    if not ok:
        return {"reply": "[Совет недоступен: ни одна модель не ответила]", "members": results, "synth": False}
    if len(ok) == 1:
        return {"reply": ok[0]["text"], "members": results, "synth": False}
    block = "\n\n".join(f"[{r['provider']}]:\n{r['text']}" for r in ok)
    try:
        synth, _, _ = await claude.chat_as(_SYNTH_SYS, f"Запрос:\n{message}\n\nОтветы моделей:\n{block}")
        reply = synth.strip() or ok[0]["text"]
    except Exception:  # noqa: BLE001 — synthesizer down → fall back to the first good answer
        reply = ok[0]["text"]
    return {"reply": reply, "members": results, "synth": True}
