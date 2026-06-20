"""Contract test for mcp_shell — runs in Factory sandbox."""
import asyncio

import handler


async def main():
    r = await handler.call("shell.run", {"cmd": "echo noir-ok"})
    assert r["rc"] == 0 and "noir-ok" in r["stdout"], r
    # denied: not in allowlist
    for bad in ["rm -rf /", "curl http://x", "echo hi && rm x", "cat /etc/passwd; ls"]:
        try:
            await handler.call("shell.run", {"cmd": bad})
            raise AssertionError(f"should have blocked: {bad}")
        except ValueError:
            pass
    print("mcp_shell contract OK")


asyncio.run(main())
