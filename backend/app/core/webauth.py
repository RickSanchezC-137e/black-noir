"""Web auth — app-level owner login (replaces Caddy basic_auth's ugly native popup).

Credentials live in secrets/webauth.json ({login, bcrypt hash}); seeded on first
use from the previous Caddy hash so the existing password keeps working. Sessions
are stateless: an HMAC-signed token (api_secret_key) stored in an HttpOnly cookie.
The /api gate + WS handshakes verify it; the login UI is a Fallout-styled overlay.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import bcrypt

from app.config import settings

_CREDS = Path(__file__).resolve().parents[3] / "secrets" / "webauth.json"
_DEFAULT_LOGIN = "Rick"
# Seed = the password that was already in use (carried over from Caddy basic_auth).
_SEED_HASH = "$2a$14$lO0aPiALB5ULC3FjqkzSMufmEkuQia1CeLWoaNoM9fBzen4g.Ux0m"
TOKEN_TTL = 30 * 24 * 3600  # 30 days
COOKIE = "noir_session"


def _load() -> dict:
    if _CREDS.exists():
        try:
            return json.loads(_CREDS.read_text())
        except (ValueError, OSError):
            pass
    d = {"login": _DEFAULT_LOGIN, "hash": _SEED_HASH}
    _save(d)
    return d


def _save(d: dict) -> None:
    _CREDS.parent.mkdir(parents=True, exist_ok=True)
    _CREDS.write_text(json.dumps(d))
    try:
        _CREDS.chmod(0o600)
    except OSError:
        pass


def current_login() -> str:
    return _load()["login"]


def verify(login: str, password: str) -> bool:
    d = _load()
    if (login or "") != d["login"]:
        return False
    try:
        return bcrypt.checkpw(password.encode(), d["hash"].encode())
    except (ValueError, TypeError):
        return False


def set_password(new: str, login: str | None = None) -> dict:
    if not new or len(new) < 6:
        return {"ok": False, "reason": "пароль слишком короткий (мин. 6 символов)"}
    d = _load()
    d["hash"] = bcrypt.hashpw(new.encode(), bcrypt.gensalt(rounds=12)).decode()
    if login and login.strip():
        d["login"] = login.strip()
    _save(d)
    return {"ok": True, "login": d["login"], "note": "пароль изменён — войдите заново при следующем входе"}


# ---- stateless session token (HMAC) ----

def _secret() -> bytes:
    return (settings.api_secret_key or "noir-dev-secret-change-me").encode()


def issue(login: str) -> str:
    msg = f"{login}.{int(time.time()) + TOKEN_TTL}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{msg}.{sig}".encode()).decode()


def valid(token: str | None) -> str | None:
    """Return the login if the token is authentic and unexpired, else None."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        login, exp, sig = raw.rsplit(".", 2)
        if int(exp) < time.time():
            return None
        good = hmac.new(_secret(), f"{login}.{exp}".encode(), hashlib.sha256).hexdigest()
        return login if hmac.compare_digest(good, sig) else None
    except (ValueError, TypeError):
        return None
