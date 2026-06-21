"""Orchestrator agent loop — the core with hands (tool-use under Governor).

Runs a bounded Anthropic tool-use loop: the model may call core tools (create_task,
call_module, …); each effectful tool is Governor-gated inside tools.run(). Returns
the final reply plus the list of actions actually taken (for the desktop).
"""
from __future__ import annotations

from app.config import settings
from app.core import claude, tools

_SYS = (
    "Ты — {name}, автономное ядро системы Noir. Отвечай кратко, по-русски. У тебя есть "
    "ИНСТРУМЕНТЫ: используй их, когда владелец просит ДЕЙСТВИЕ (создать задачу, вызвать "
    "модуль, сохранить факт, завести идею) — не описывай, а делай через инструмент. Для "
    "обычных вопросов отвечай текстом без инструментов. Каждое действие проходит через "
    "Governor; если он отклонил — честно сообщи."
)


async def run(message: str, history: list[dict] | None = None, extra_system: str = "",
              max_steps: int = 5) -> dict:
    """Returns {reply, actions: [{tool, input, result}]}."""
    system = _SYS.format(name=settings.project_name) + (("\n\n" + extra_system) if extra_system else "")
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})
    actions: list[dict] = []

    for _ in range(max_steps):
        resp = await claude.client().messages.create(
            model=settings.claude_model, max_tokens=settings.llm_max_tokens,
            system=system, tools=tools.SCHEMAS, messages=msgs)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return {"reply": text.strip(), "actions": actions}
        # rebuild assistant turn (text + tool_use blocks) then answer each tool_use
        acontent, results = [], []
        for b in resp.content:
            if b.type == "text":
                acontent.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                acontent.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                out = await tools.run(b.name, b.input or {})
                actions.append({"tool": b.name, "input": b.input, "result": out})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        msgs.append({"role": "assistant", "content": acontent})
        msgs.append({"role": "user", "content": results})

    return {"reply": "(достигнут лимит шагов инструментов)", "actions": actions}
