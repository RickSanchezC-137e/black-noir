"""Noir Eval runner (build plan §6.1, Rule 5 — FIRST artifact).

Usage:
    python eval/runner.py --suite all --base http://127.0.0.1:8000
    python eval/runner.py --suite core memory

Cases are YAML in eval/cases/*.yaml. Reports -> eval/results/*.jsonl + stdout pass-rate.
The harness is the build's traffic light: no stage is 'done' until its suite is green.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from scorers import check_expectations

CASES_DIR = Path(__file__).with_name("cases")
RESULTS_DIR = Path(__file__).with_name("results")


def load_cases(suites: list[str]) -> list[dict]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        for doc in yaml.safe_load_all(f.read_text()):
            if not doc:
                continue
            if "all" in suites or doc.get("suite") in suites:
                doc["_file"] = f.name
                cases.append(doc)
    return cases


def _do_request(client: httpx.Client, base: str, req: dict) -> tuple[int, object, float]:
    method = req.get("method", "GET").upper()
    url = base + req["path"]
    t0 = time.monotonic()
    r = client.request(method, url, json=req.get("json"), params=req.get("query"),
                       timeout=req.get("timeout", 30))
    dt = (time.monotonic() - t0) * 1000
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = r.text
    return r.status_code, body, dt


def run_case(client: httpx.Client, base: str, case: dict) -> dict:
    reqs = case.get("steps") or [case["request"]]
    status, body, latency = 0, None, 0.0
    try:
        for req in reqs:
            status, body, latency = _do_request(client, base, req)
    except Exception as e:  # noqa: BLE001
        return {"id": case["id"], "suite": case.get("suite"), "passed": False,
                "failures": [f"request error: {e}"], "latency_ms": 0}
    passed, fails = check_expectations(status, body, case.get("expect", {}), latency)
    return {"id": case["id"], "suite": case.get("suite"), "passed": passed,
            "failures": fails, "latency_ms": round(latency, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", nargs="+", default=["all"])
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    cases = load_cases(args.suite)
    if not cases:
        print(f"no cases for suite(s) {args.suite}")
        return 1

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"run-{stamp}.jsonl"

    results = []
    with httpx.Client() as client, out.open("w") as fh:
        for c in cases:
            res = run_case(client, args.base, c)
            results.append(res)
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            mark = "PASS" if res["passed"] else "FAIL"
            extra = "" if res["passed"] else f"  -> {res['failures']}"
            print(f"[{mark}] {res['suite']:<10} {res['id']:<20} {res['latency_ms']:>7.0f}ms{extra}")

    total = len(results)
    passed = sum(r["passed"] for r in results)
    by_suite: dict[str, list[bool]] = {}
    for r in results:
        by_suite.setdefault(r["suite"], []).append(r["passed"])

    print("\n--- pass-rate by suite ---")
    for s, ps in sorted(by_suite.items()):
        print(f"  {s:<12} {sum(ps)}/{len(ps)}")
    print(f"\nTOTAL: {passed}/{total} passed  ({100*passed//max(total,1)}%)   report: {out.name}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
