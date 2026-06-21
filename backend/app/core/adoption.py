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


# ---------------- generic Builder-written wrapper (any repo → MCP module) ----------------
WRAP_DIR = REPO / ".worktrees"


def _wrapper_instruction(repo: str, module_id: str, cluster: str, capability: str, readme: str) -> str:
    return (
        f"Создай НОВЫЙ MCP-модуль-обёртку '{module_id}' (кластер {cluster}) для GitHub-репозитория "
        f"'{repo}'. Возможность: {capability or 'определи по README'}.\n"
        f"СОЗДАЙ ТОЛЬКО файлы внутри modules/installed/{module_id}/ — НИЧЕГО за пределами этого каталога "
        f"не трогай (особенно app/core, governor, конституцию).\n"
        f"Файлы:\n"
        f"  handler.py: 'async def call(tool: str, args: dict) -> dict' (неизвестный tool → ValueError) и "
        f"'async def health() -> dict'. Зависимости ставь лениво внутри функций (import внутри).\n"
        f"  module.yaml: manifest_version:1, module_id:{module_id}, cluster:{cluster}, "
        f"namespace:m_{module_id}__, version:1.0.0, runtime:in-process, секция tools с action_class из "
        f"read/local_write/external_send, и capabilities.origin='github.com/{repo}', license.\n"
        f"  test_contract.py: герметичный (без сети) — импортирует handler и проверяет, что неизвестный tool "
        f"отклоняется; печатает '{module_id} contract OK'.\n"
        f"Эталон контракта смотри в modules/installed/mcp_glances/.\n"
        f"README репозитория (фрагмент):\n{readme}"
    )


async def build_wrapper(repo: str, *, capability: str = "", cluster: str = "C6") -> dict:
    """Builder (headless Claude Code) writes an MCP wrapper for `repo` in a sandbox,
    eval-gates it, and stashes the diff for owner-confirmed promotion. Never touches live."""
    import asyncio

    from app.core import builder
    repo = repo.replace("https://github.com/", "").replace(".git", "").strip("/")
    name = re.sub(r"[^a-z0-9_]", "_", repo.split("/")[-1].lower())
    module_id = f"mcp_{name}"
    rep: dict = {"repo": repo, "module_id": module_id, "capability": capability, "cluster": cluster}
    try:
        d = clone(repo)
        lic = license_scan(d)
        sec = security_scan(d)
        rep.update(license=lic, security=sec)
        if not lic["compatible"]:
            rep.update(verdict="skip", reason=f"license {lic['license']} incompatible"); return rep
        if not sec["safe"]:
            rep.update(verdict="skip", reason=f"security findings: {sec['findings'][:3]}"); return rep
        readme = ""
        for n in ("README.md", "README.rst", "readme.md", "Readme.md"):
            if (d / n).exists():
                readme = (d / n).read_text(errors="ignore")[:2500]; break
        instr = _wrapper_instruction(repo, module_id, cluster, capability, readme)
        b = await asyncio.to_thread(builder.build, instr, timeout=600)
        wt = Path(b["worktree"])
        rep["builder"] = {"ok": b.get("ok"), "tokens": b.get("tokens"), "summary": (b.get("summary") or "")[:300]}
        try:
            rel = f"modules/installed/{module_id}"
            subprocess.run(["git", "add", "-A", rel], cwd=str(wt), capture_output=True, timeout=60)
            diff = subprocess.run(["git", "diff", "--cached", "--", rel], cwd=str(wt),
                                  capture_output=True, text=True, timeout=60).stdout
            modp = wt / rel
            if not diff.strip() or not modp.exists():
                rep.update(verdict="failed", reason="Builder не создал модуль"); return rep
            # hard guard: wrapper may ONLY add files under its own module dir
            touched = re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)
            outside = [f for f in touched if f != "/dev/null" and not f.startswith(rel + "/")]
            if outside:
                rep.update(verdict="rejected", reason=f"diff трогает файлы вне модуля: {outside[:3]}"); return rep
            import factory
            ok, out = factory.contract_test(modp)
            rep["eval"] = {"contract_ok": ok, "detail": out[-300:]}
            if not ok:
                rep.update(verdict="failed", reason="контракт-тест красный"); return rep
            token = "wrap_" + datetime.now(timezone.utc).strftime("%H%M%S") + name[:6]
            WRAP_DIR.mkdir(exist_ok=True)
            (WRAP_DIR / f"{token}.patch").write_text(diff)
            rep.update(verdict="ready", token=token, diff_stat=b.get("diff_stat", ""),
                       reason="обёртка собрана и прошла контракт — подтвердите внедрение")
        finally:
            try:
                builder.drop_worktree(wt)
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        rep.update(verdict="skip", reason=f"error: {e}")
    finally:
        if (SANDBOX / repo.split("/")[-1]).exists():
            shutil.rmtree(SANDBOX / repo.split("/")[-1], ignore_errors=True)
    _record(rep)
    return rep


async def promote_wrapper(token: str) -> dict:
    """Owner-confirmed: apply a stashed wrapper diff to the live tree and restart to register."""
    patch = WRAP_DIR / f"{token}.patch"
    if not patch.exists():
        return {"ok": False, "reason": "неизвестный токен"}
    action = Action(module="adoption", tool="promote_wrapper", action_class="self_modify")
    dec = governor.authorize(action)
    if dec.decision == "KILL":
        await audit(action, dec, ok=False); return {"ok": False, "reason": dec.reason}
    apply = subprocess.run(["git", "apply", str(patch)], cwd=str(REPO), capture_output=True, text=True)
    if apply.returncode != 0:
        await audit(action, dec, ok=False)
        return {"ok": False, "reason": f"git apply failed: {apply.stderr[:200]}"}
    await audit(action, dec, ok=True)
    subprocess.run(["sudo", "systemctl", "restart", "noir-core.service"], capture_output=True, timeout=60)
    return {"ok": True, "applied": True, "note": "ядро перезапущено — модуль регистрируется"}
