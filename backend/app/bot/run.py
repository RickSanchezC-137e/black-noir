"""noir-bot — Telegram long-polling bot (C1). Separate service (noir-bot.service).

Thin client over the core HTTP API (localhost:8000): commands and chat go through
/api/*; the bot never touches modules directly. Access restricted to
TELEGRAM_ALLOWED_USER_IDS (privacy, parity with old Jarvis). Long-polling via Bot API
getUpdates — no extra heavy deps.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s noir.bot %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)   # don't log token URLs to journal
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("noir.bot")

API = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{{m}}"
CORE = f"http://127.0.0.1:{settings.api_port}"

HELP = (
    "🤖 {name} на связи. Команды:\n"
    "/status — состояние ядра и модулей\n"
    "/ideas — показать идеи\n"
    "/idea <тема> — сгенерировать идеи\n"
    "/help — помощь\n"
    "Любой текст — вопрос ядру (живой чат)."
)


def _allowed() -> set[int]:
    raw = settings.telegram_allowed_user_ids or ""
    out = set()
    for p in raw.replace(";", ",").split(","):
        p = p.strip()
        if p.isdigit():
            out.add(int(p))
    return out


async def _tg(client: httpx.AsyncClient, method: str, **payload):
    r = await client.post(API.format(m=method), json=payload, timeout=70)
    return r.json()


async def _send(client: httpx.AsyncClient, chat_id: int, text: str):
    await _tg(client, "sendMessage", chat_id=chat_id, text=text[:4000])


async def _core_get(client: httpx.AsyncClient, path: str):
    r = await client.get(CORE + path, timeout=30)
    return r.json()


async def _core_post(client: httpx.AsyncClient, path: str, body: dict):
    r = await client.post(CORE + path, json=body, timeout=60)
    return r.json()


async def handle(client: httpx.AsyncClient, msg: dict):
    chat_id = msg["chat"]["id"]
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    allow = _allowed()
    if allow and uid not in allow:
        await _send(client, chat_id, "⛔ Доступ ограничён владельцем.")
        return

    if text in ("/start", "/help"):
        await _send(client, chat_id, HELP.format(name=settings.project_name))
    elif text == "/status":
        core = await _core_get(client, "/api/core")
        mods = await _core_get(client, "/api/modules")
        names = ", ".join(m["name"] for m in mods.get("modules", []))
        await _send(client, chat_id,
                    f"🟢 {core['name']} · {core['status']} · {core['model']}\n"
                    f"модулей: {len(mods.get('modules', []))} ({names})")
    elif text == "/ideas":
        d = await _core_get(client, "/api/ideas?limit=8")
        items = d.get("ideas", [])
        body = "\n".join(f"• {i['text']}" for i in items) or "(пусто)"
        await _send(client, chat_id, "💡 Идеи:\n" + body)
    elif text.startswith("/idea"):
        topic = text[5:].strip() or "продуктивность и проекты владельца"
        await _send(client, chat_id, "⏳ генерирую…")
        d = await _core_post(client, "/api/ideas/generate", {"n": 3, "topic": topic})
        body = "\n".join(f"• {i['text']}" for i in d.get("ideas", []))
        await _send(client, chat_id, "💡 " + (body or "(нет)"))
    elif text.startswith("/"):
        await _send(client, chat_id, "Неизвестная команда. /help")
    elif text:
        r = await _core_post(client, "/api/chat", {"message": text})
        await _send(client, chat_id, r.get("reply", "(нет ответа)"))


async def main():
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN not set — exiting")
        return
    async with httpx.AsyncClient() as client:
        me = await _tg(client, "getMe")
        log.info("bot online: @%s (allowed: %s)", me.get("result", {}).get("username"), _allowed() or "ALL")
        if settings.telegram_owner_chat_id:
            try:
                await _send(client, int(settings.telegram_owner_chat_id),
                            f"🤖 {settings.project_name} онлайн — ядро на :{settings.api_port}, бот на связи.")
            except Exception as e:  # noqa: BLE001
                log.warning("owner notify failed: %s", e)
        offset = None
        while True:
            try:
                upd = await _tg(client, "getUpdates", offset=offset, timeout=50)
                for u in upd.get("result", []):
                    offset = u["update_id"] + 1
                    if "message" in u:
                        try:
                            await handle(client, u["message"])
                        except Exception as e:  # noqa: BLE001
                            log.exception("handle error: %s", e)
            except httpx.HTTPError as e:
                log.warning("poll error: %s", e)
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
