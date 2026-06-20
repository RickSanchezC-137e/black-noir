"""Smoke tests for noir-core (08_conventions §8). External APIs not called here."""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_core_status():
    with TestClient(app) as c:
        r = c.get("/api/core")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "kill")
        assert body["project"] == "Black Noir"
        assert body["model"] == "claude-opus-4-8"


def test_systems_hardware_is_real():
    with TestClient(app) as c:
        r = c.get("/api/systems")
        assert r.status_code == 200
        hw = r.json()["hardware"]
        assert "cpu_cores" in hw and hw["cpu_cores"] >= 1
        assert r.json()["embedding"]["model"] == "all-MiniLM-L6-v2"


def test_governor_decisions():
    with TestClient(app) as c:
        assert c.post("/api/governor/check", json={"action_class": "read"}).json()["decision"] == "ALLOW"
        assert c.post("/api/governor/check", json={"action_class": "money", "amount_usd": 120}).json()["decision"] == "CONFIRM"
        assert c.post("/api/governor/check", json={"action_class": "money", "amount_usd": 500}).json()["decision"] == "DENY"
        assert c.post("/api/governor/check", json={"action_class": "self_modify", "targets_constitution": True}).json()["decision"] == "KILL"
