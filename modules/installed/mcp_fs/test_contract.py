"""Contract test for mcp_fs — runs in Factory sandbox (isolation)."""
import asyncio
import os
import tempfile

os.environ["NOIR_FS_SANDBOX"] = tempfile.mkdtemp(prefix="mcp_fs_test_")

import handler


async def main():
    w = await handler.call("fs.write", {"path": "a/b.txt", "content": "hello"})
    assert w["bytes"] == 5, w
    r = await handler.call("fs.read", {"path": "a/b.txt"})
    assert r["content"] == "hello", r
    ls = await handler.call("fs.list", {"path": "a"})
    assert "b.txt" in ls["entries"], ls
    # traversal must be refused
    try:
        await handler.call("fs.read", {"path": "../../../etc/passwd"})
        raise AssertionError("traversal not blocked")
    except ValueError:
        pass
    print("mcp_fs contract OK")


asyncio.run(main())
