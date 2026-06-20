"""Contract test for owner_profile — hermetic (no app/db/model load in sandbox)."""
import asyncio

import handler


async def main():
    try:
        await handler.call("nope", {})
        raise AssertionError("unknown tool not rejected")
    except ValueError:
        pass
    # all 9 declared tools are registered
    expected = {"profile.observe", "profile.get", "profile.reconcile",
                "profile.hypothesis.add", "profile.hypothesis.test",
                "health.log", "health.summary", "schedule.get", "schedule.plan"}
    assert expected <= set(handler._TOOLS), set(handler._TOOLS)
    print("owner_profile contract OK")


asyncio.run(main())
