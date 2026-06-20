"""Contract test for mcp_search — hermetic (no secrets in sandbox, §4.2).
Live Tavily call is exercised by the eval suite against the running core.
"""
import asyncio
import os

import handler


async def main():
    os.environ.pop("TAVILY_API_KEY", None)
    # unknown tool rejected
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    # missing key handled gracefully (contract), not a crash
    try:
        await handler.call("search.web", {"query": "test"})
        raise AssertionError("should require key")
    except ValueError as e:
        assert "TAVILY_API_KEY" in str(e), e
    print("mcp_search contract OK")


asyncio.run(main())
