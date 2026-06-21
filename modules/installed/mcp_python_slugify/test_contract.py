"""Contract test for mcp_python_slugify — hermetic (no network, no deps)."""
import asyncio
import handler


async def main():
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    print("mcp_python_slugify contract OK")


asyncio.run(main())
