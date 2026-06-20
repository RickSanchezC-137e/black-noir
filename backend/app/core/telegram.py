"""Telegram client (C1) — owner notification + Governor escalation channel.

v1 uses the Bot HTTP API directly (getMe / sendMessage): no long-polling here, because
the legacy jarvis-telegram bot still polls the same token until decommission (Step 5).
Command polling is enabled after the old bot is stopped.
"""
from __future__ import annotations

import httpx

from app.config import settings

API = "https://api.telegram.org/bot{token}/{method}"


async def _call(method: str, payload: dict | None = None) -> dict:
    if not settings.telegram_bot_token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = API.format(token=settings.telegram_bot_token, method=method)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(url, json=payload or {})
        return r.json()


async def get_me() -> dict:
    return await _call("getMe")


async def send_message(chat_id: str, text: str) -> dict:
    return await _call("sendMessage", {"chat_id": chat_id, "text": text})


async def notify_owner(text: str) -> dict:
    """Proactive owner notification (parity with old Jarvis /telegram/notify)."""
    if not settings.telegram_owner_chat_id:
        return {"ok": False, "error": "TELEGRAM_OWNER_CHAT_ID not set"}
    return await send_message(settings.telegram_owner_chat_id, f"🤖 {settings.project_name}: {text}")
