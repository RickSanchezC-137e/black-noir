"""Mediator (Передатчик) — interaction-layer agent (cluster C1).

Two-way translator between the owner and the core:
  • owner → core: consolidates the owner's (often fragmented) messages into ONE
    clear, well-scoped task before bothering the core — fewer, richer requests.
  • core → owner: takes the core's detailed answer and conveys only the essence
    the owner needs, concisely.

So the owner and the core understand each other better and the core is not spammed
with tiny disjoint queries. Persistent memory comes from the chat session history
(passed in by the /api/chat handler).
"""
from __future__ import annotations

from app.core import claude

_TASK_SYS = (
    "Ты — «Передатчик», посредник между владельцем и ядром ИИ. "
    "Тебе дают одно или несколько коротких/отрывочных сообщений владельца (они могут "
    "относиться к ОДНОЙ задаче). Собери их в ОДИН чёткий, полный, однозначный запрос к "
    "ядру: убери воду, дополни недостающий контекст из истории, сформулируй цель и "
    "критерий результата. Верни ТОЛЬКО переформулированный запрос к ядру, без пояснений."
)
_ESSENCE_SYS = (
    "Ты — «Передатчик». Ядро дало подробный ответ. Передай владельцу ТОЛЬКО важную для "
    "него суть: кратко, простыми словами, по-русски, без технического шума. Если есть "
    "конкретные действия/числа/решения — вынеси их. 2–5 предложений максимум."
)


async def relay(message: str, history: list[dict] | None = None) -> dict:
    """owner message(s) → formed task → core answer → concise essence.

    Returns {reply, task, core_reply}: `reply` is the concise essence for the owner;
    `task` is what was actually sent to the core; `core_reply` is the full core answer.
    """
    task, _, _ = await claude.chat_as(_TASK_SYS, message, history)
    task = task.strip() or message
    core_reply, _, _ = await claude.chat(task)
    essence, _, _ = await claude.chat_as(
        _ESSENCE_SYS, f"Запрос к ядру:\n{task}\n\nПодробный ответ ядра:\n{core_reply}")
    return {"reply": essence.strip() or core_reply, "task": task, "core_reply": core_reply}
