"""mcp_python_slugify — turn text into URL-safe slugs via the python-slugify engine.
Adopted from un33k/python-slugify. Pure transform; no network, no filesystem."""
from __future__ import annotations


def _slugify():
    from slugify import slugify
    return slugify


async def call(tool: str, args: dict) -> dict:
    if tool != "slugify.make":
        raise ValueError(f"unknown tool {tool}")
    slugify = _slugify()
    text = args.get("text", "")
    if not isinstance(text, str):
        raise ValueError("args.text must be a string")
    # Pass through the supported slugify options when provided.
    opts = {}
    for key in (
        "entities", "decimal", "hexadecimal", "max_length", "word_boundary",
        "separator", "save_order", "stopwords", "regex_pattern", "lowercase",
        "replacements", "allow_unicode",
    ):
        if key in args:
            opts[key] = args[key]
    slug = slugify(text, **opts)
    return {"slug": slug, "text": text}


async def health() -> dict:
    try:
        from slugify import slugify  # noqa
        return {"ok": True, "engine": "python-slugify"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
