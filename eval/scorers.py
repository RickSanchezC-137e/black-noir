"""Eval scorers (build plan §6.1, eval/README.md): success-rate, latency, cost, violations=0."""
from __future__ import annotations

import json
from typing import Any


def _walk(obj: Any):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def text_blob(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def check_expectations(resp_status: int, body: Any, expect: dict, latency_ms: float) -> tuple[bool, list[str]]:
    """Return (passed, failures)."""
    fails: list[str] = []

    if "status" in expect and resp_status != expect["status"]:
        fails.append(f"status {resp_status} != {expect['status']}")

    if "json_has_keys" in expect:
        keys = expect["json_has_keys"]
        if not isinstance(body, dict) or any(k not in body for k in keys):
            fails.append(f"missing keys {keys}")

    if "json_contains" in expect:
        for k, v in expect["json_contains"].items():
            if not (isinstance(body, dict) and str(body.get(k)) == str(v)):
                fails.append(f"json_contains {k}={v} (got {body.get(k) if isinstance(body, dict) else body!r})")

    if "contains" in expect:
        blob = text_blob(body)
        for needle in expect["contains"]:
            if needle.lower() not in blob.lower():
                fails.append(f"missing substring '{needle}'")

    if "reply_contains_any" in expect:
        blob = text_blob(body).lower()
        if not any(n.lower() in blob for n in expect["reply_contains_any"]):
            fails.append(f"none of {expect['reply_contains_any']} in reply")

    if "max_latency_ms" in expect and latency_ms > expect["max_latency_ms"]:
        fails.append(f"latency {latency_ms:.0f}ms > {expect['max_latency_ms']}ms")

    # violations: 0 — governance expectation; a DENY/KILL leaking where not expected
    if expect.get("violations", None) == 0:
        blob = text_blob(body)
        # only a real violation if the case did not explicitly expect a deny/kill decision
        if not expect.get("json_contains", {}).get("decision") in ("DENY", "KILL"):
            if '"decision": "KILL"' in blob and "kill" not in str(expect).lower():
                fails.append("unexpected KILL violation")

    return (len(fails) == 0, fails)
