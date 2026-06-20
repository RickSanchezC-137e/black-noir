"""Contract test for mcp_voice — hermetic (no model load in Factory sandbox).
Real TTS->STT roundtrip is exercised by the perception eval suite against the core.
"""
import asyncio

import handler


async def main():
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    # path-escape refused without loading models
    try:
        handler._safe("../../etc/passwd")
        raise AssertionError("escape not blocked")
    except ValueError:
        pass
    print("mcp_voice contract OK")


asyncio.run(main())
