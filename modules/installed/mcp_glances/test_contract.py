"""Contract test for mcp_glances — hermetic."""
import asyncio
import handler


async def main():
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    print("mcp_glances contract OK")


asyncio.run(main())
