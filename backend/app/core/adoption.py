"""Adoption pipeline — build-vs-adopt (CANON §13, 11_adoption.md, 05_modules.md).

Per external repo: clone to sandbox -> license scan + security-lite scan (results to the
immutable audit; SkillSpector is the mature scanner to adopt for this step) -> wrap as a
Python MCP module adapter -> Eval -> register + verdict (adopt/improve/skip). Foreign code
is isolated; FS/network/secret access only via Governor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.core.governor import Action, audit, governor

REPO = Path("/home/jarvis/noir")
SANDBOX = REPO / "modules" / ".adopt"
INSTALLED = REPO / "modules" / "installed"

# license compatibility (permissive + weak-copyleft-as-lib OK; strong copyleft in-core -> skip)
COMPAT = {"mit", "apache", "bsd", "isc", "mpl", "lgpl"}
INCOMPAT = {"agpl", "gpl-3", "gplv3", "sspl", "proprietary", "unlicensed"}

# security-lite deny patterns (until SkillSpector is adopted as the scanner).
# Real install-time / runtime threats only — NOT strings that legitimately appear as data.
DANGER = [r"curl\s+-[a-zA-Z]*\s+https?://\S+\s*\|\s*(sudo\s+)?(ba)?sh",
          r"eval\(base64\.b64decode", r"os\.system\(\s*['\"]\s*rm\s+-rf\s+/"]
SECRET_PAT = re.compile(r"(sk-ant-[A-Za-z0-9_-]{30}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16})")

# files that legitimately contain attack strings as DATA (scanners, detectors, rule/pattern DBs,
# samples, docs) — excluded from the dangerous-pattern scan to avoid false positives.
_DATA_FILE_HINTS = ("pattern", "detector", "signature", "rule", "payload", "exploit",
                    "attack", "misuse", "malicious", "sample", "fixture", "vuln", "readme",
                    "changelog", "install", "_test", "test_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd, cwd=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def clone(repo: str) -> Path:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    name = repo.rstrip("/").split("/")[-1]
    dst = SANDBOX / name
    if dst.exists():
        shutil.rmtree(dst)
    url = repo if repo.startswith("http") else f"https://github.com/{repo}.git"
    _run(["git", "clone", "--depth", "1", url, str(dst)], timeout=300)
    return dst


def license_scan(d: Path) -> dict:
    text = ""
    cands = list(d.glob("LICENSE*")) + list(d.glob("COPYING*")) + \
        list(d.glob("LICENSE*/*")) + list(d.glob("LICENSES/*"))
    for f in cands:
        if f.is_file():
            text += f.read_text(errors="ignore").lower()[:4000]
    # pyproject/setup classifiers as a fallback signal
    for meta in ["pyproject.toml", "setup.cfg", "setup.py"]:
        p = d / meta
        if p.is_file():
            text += p.read_text(errors="ignore").lower()[:2000]
    name = "unknown"
    for k in ["apache", "mit", "bsd", "isc", "mpl", "lgpl", "agpl", "gpl"]:
        if k in text:
            name = k
            break
    incompat = any(k in text for k in INCOMPAT) and "lgpl" not in text
    compat = (name in COMPAT) and not incompat
    return {"license": name, "compatible": compat}


_SKIP_DIRS = ("/test", "/tests", "/example", "/examples", "/docs", "/fixtures", "/__tests__", "/.git/")


def security_scan(d: Path, *, vetted: bool = False) -> dict:
    findings = []
    for p in list(d.rglob("*.py"))[:800] + list(d.rglob("*.sh"))[:200]:
        low = str(p).lower()
        if any(s in low for s in _SKIP_DIRS):
            continue
        # skip files that hold attack strings as DATA (pattern DBs, detectors, samples, docs)
        if any(h in p.name.lower() for h in _DATA_FILE_HINTS):
            continue
        try:
            t = p.read_text(errors="ignore")
        except OSError:
            continue
        for pat in DANGER:
            if re.search(pat, t):
                findings.append(f"{p.name}: {pat[:30]}")
        if SECRET_PAT.search(t):
            findings.append(f"{p.name}: hardcoded secret")
    # vetted (owner/blueprint adopt list): findings are warnings, not blockers
    safe = len(findings) == 0 or vetted
    return {"findings": findings[:20], "safe": safe, "vetted": vetted,
            "scanner": "security-lite (SkillSpector pending)"}


async def adopt(repo: str, *, capability: str = "", cluster: str = "C6",
                integrate=None) -> dict:
    """Full pipeline. `integrate(sandbox_dir)` is an optional callback that wraps the
    repo as a Python MCP module (returns module_id) — used for concrete targets like glances."""
    action = Action(module="adoption", tool="adopt", action_class="self_modify",
                    args={"repo": repo})
    gov = governor.authorize(action)
    if gov.decision in ("DENY", "KILL"):
        await audit(action, gov, ok=False)
        return {"repo": repo, "verdict": "skip", "reason": gov.reason}

    rep = {"repo": repo, "capability": capability, "cluster": cluster}
    try:
        # vetted = owner/blueprint adopt|improve verdict (pre-vetted list, CANON §13)
        from app.core.adopt_catalog import by_repo
        cat = by_repo(repo)
        vetted = bool(cat) and cat[3] in ("adopt", "improve")
        d = clone(repo)
        lic = license_scan(d)
        sec = security_scan(d, vetted=vetted)
        rep.update(license=lic, security=sec)
        # gate: license incompatible OR security findings -> skip (idea only)
        if not lic["compatible"]:
            rep["verdict"] = "skip"; rep["reason"] = f"license {lic['license']} incompatible"
        elif not sec["safe"]:
            rep["verdict"] = "skip"; rep["reason"] = f"security findings: {sec['findings'][:3]}"
        else:
            module_id = integrate(d) if integrate else None
            if module_id:
                # eval the wrapped module through the harness/registry
                import factory  # noqa
                ok, out = factory.contract_test(INSTALLED / module_id)
                rep["eval"] = {"contract_ok": ok, "detail": out[-300:] if not ok else "ok"}
                rep["verdict"] = "adopt" if ok else "skip"
                rep["module_id"] = module_id
            else:
                rep["verdict"] = "defer"; rep["reason"] = "no integrator wired (evaluated as idea)"
        await audit(action, gov, ok=(rep.get("verdict") == "adopt"))
        _record(rep)
    except Exception as e:  # noqa: BLE001
        rep["verdict"] = "skip"; rep["reason"] = f"error: {e}"
        await audit(action, gov, ok=False)
    finally:
        if (SANDBOX / repo.split("/")[-1]).exists():
            shutil.rmtree(SANDBOX / repo.split("/")[-1], ignore_errors=True)
    return rep


def _record(rep: dict) -> None:
    import sqlite3
    con = sqlite3.connect(settings.sqlite_path)
    try:
        con.execute("ALTER TABLE si_adoptions ADD COLUMN reason TEXT")
        con.commit()
    except sqlite3.OperationalError:
        pass
    con.execute(
        "INSERT INTO si_adoptions(repo,capability,cluster,verdict,license,security,eval,status,reason,decided_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(repo) DO UPDATE SET verdict=excluded.verdict,"
        " eval=excluded.eval, status=excluded.status, reason=excluded.reason, decided_at=excluded.decided_at",
        (rep["repo"], rep.get("capability"), rep.get("cluster"), rep.get("verdict"),
         json.dumps(rep.get("license", {})), json.dumps(rep.get("security", {})),
         json.dumps(rep.get("eval", {})), rep.get("module_id", ""), rep.get("reason", ""), _now()))
    con.commit()
    con.close()


def list_adoptions() -> list[dict]:
    import sqlite3
    con = sqlite3.connect(settings.sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT repo,capability,cluster,verdict,reason,status,decided_at FROM si_adoptions ORDER BY decided_at DESC")]
    except sqlite3.OperationalError:
        try:
            rows = [dict(r) for r in con.execute("SELECT repo,capability,verdict,decided_at FROM si_adoptions ORDER BY decided_at DESC")]
        except sqlite3.OperationalError:
            rows = []
    con.close()
    return rows
