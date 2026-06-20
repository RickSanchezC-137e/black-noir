"""Governor — Noir constitution (CANON §6, 04_governor.md).

Decisions: ALLOW | CONFIRM | DENY | KILL.
Action classes: read | local_write | external_send | money | system | self_modify.

Pipeline: classify -> deterministic deny-list -> judgement+critic -> reversibility wrapper
-> limits/rails -> execute (by caller) -> immutable audit log.

The constitution itself (Governor, kill-switch, deny-list, Eval, rollback) is IMMUTABLE:
any attempt to modify it is an auto-trigger for KILL.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiosqlite

from app.config import settings

ALLOW, CONFIRM, DENY, KILL = "ALLOW", "CONFIRM", "DENY", "KILL"
CLASSES = ("read", "local_write", "external_send", "money", "system", "self_modify")

# Deterministic deny-list (absolute stop-crane). Constitution is immutable.
DENY_ALWAYS = {"constitution_modify", "secret_exfiltration"}

# Paths agents/modules may never write or delete (backup protection, Rule 8).
PROTECTED_PATHS = ("/home/jarvis/secrets-backup", "/home/jarvis/noir/secrets")

# Auto-allow classes (read/local_write are safe by default; rest escalate).
ALLOW_WITHOUT_CONFIRM = {"read", "local_write"}

# Money rails (carried over and hardened from old Jarvis financial policy).
MONEY_AUTO_LIMIT_USD = 50.0
MONEY_DAILY_CAP_USD = 200.0


@dataclass
class Action:
    module: str
    tool: str
    action_class: str
    args: dict = field(default_factory=dict)
    amount_usd: float = 0.0
    targets_constitution: bool = False
    targets_protected_path: bool = False


@dataclass
class Decision:
    decision: str
    reason: str
    reversible: bool = True


class Governor:
    """Mandatory mediator before any effectful tool/autonomous action."""

    def __init__(self) -> None:
        self._killed = False
        self._spent_today = 0.0
        self._day = datetime.now(timezone.utc).date()

    def authorize(self, a: Action) -> Decision:
        """Pure classification (no side effects) — safe to call as a dry-run probe.
        The real kill switch is engaged separately by the execution layer (enforce)."""
        if self._killed:
            return Decision(KILL, "kill switch engaged", reversible=False)

        if a.action_class not in CLASSES:
            return Decision(DENY, f"unknown action_class '{a.action_class}'")

        # 1) deterministic deny-list + immutable constitution
        if a.targets_constitution or a.tool in DENY_ALWAYS:
            return Decision(KILL, "constitution is immutable — kill switch", reversible=False)
        if a.targets_protected_path:
            return Decision(DENY, "write/delete to protected secrets/backup path is forbidden")

        # 2) money rails
        if a.action_class == "money":
            self._roll_day()
            if self._spent_today + a.amount_usd > MONEY_DAILY_CAP_USD:
                return Decision(DENY, f"daily money cap ${MONEY_DAILY_CAP_USD} exceeded")
            if a.amount_usd > MONEY_AUTO_LIMIT_USD:
                return Decision(CONFIRM, f"money ${a.amount_usd:.2f} > ${MONEY_AUTO_LIMIT_USD} — owner confirm")
            return Decision(ALLOW, "money within auto limit (rails: limit/delay/revoke)")

        # 3) class policy
        if a.action_class in ALLOW_WITHOUT_CONFIRM:
            return Decision(ALLOW, "auto-allowed class")
        # external_send / system / self_modify -> escalate
        return Decision(CONFIRM, f"class '{a.action_class}' requires owner confirm")

    def record_spend(self, amount_usd: float) -> None:
        self._roll_day()
        self._spent_today += amount_usd

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            self._day, self._spent_today = today, 0.0

    # --- kill switch ---
    def engage_kill(self, reason: str) -> None:
        self._killed = True

    @property
    def killed(self) -> bool:
        return self._killed


governor = Governor()


async def audit(action: Action, decision: Decision, *, ok: bool, duration_ms: int = 0) -> None:
    """Insert-only immutable audit log to agent_log."""
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO agent_log(module,tool,args,decision,action_class,reason,ok,duration_ms,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (action.module, action.tool, json.dumps(action.args, ensure_ascii=False),
             decision.decision, action.action_class, decision.reason,
             1 if ok else 0, duration_ms, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def guard(action: Action):
    """Authorize + audit. Returns Decision. Caller executes only on ALLOW."""
    t0 = time.monotonic()
    dec = governor.authorize(action)
    await audit(action, dec, ok=(dec.decision == ALLOW), duration_ms=int((time.monotonic() - t0) * 1000))
    return dec
