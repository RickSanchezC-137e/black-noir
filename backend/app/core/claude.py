"""Claude API client (Oрхестратор brain). Model claude-opus-4-8 (CANON §1/§5)."""
from __future__ import annotations

from anthropic import AsyncAnthropic

from app.config import settings

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM = (
    "Ты — {name}, личный автономный ИИ-ассистент владельца. Отвечай кратко, по делу, "
    "на русском. Ты ядро системы Noir."
)


async def chat(message: str, history: list[dict] | None = None, extra_system: str = "") -> tuple[str, int, int]:
    """Returns (reply, tokens_in, tokens_out). extra_system = memory context (summary/recall)."""
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})
    system = SYSTEM.format(name=settings.project_name)
    if extra_system:
        system += "\n\n" + extra_system
    resp = await client().messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=msgs,
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


async def chat_as(system: str, message: str, history: list[dict] | None = None) -> tuple[str, int, int]:
    """Like chat() but with a custom system prompt (used by the Mediator agent, C1)."""
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})
    resp = await client().messages.create(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=system,
        messages=msgs,
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


async def stream(message: str, history: list[dict] | None = None):
    """Async generator of text tokens for /ws/chat."""
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})
    async with client().messages.stream(
        model=settings.claude_model,
        max_tokens=settings.llm_max_tokens,
        system=SYSTEM.format(name=settings.project_name),
        messages=msgs,
    ) as s:
        async for text in s.text_stream:
            yield text
