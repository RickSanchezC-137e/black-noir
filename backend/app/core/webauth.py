"""Web auth management — change the Caddy basic_auth password from the desktop/web.

The owner login lives in /etc/caddy/Caddyfile (basic_auth). Changing the password
re-hashes via `caddy hash-password`, rewrites the Caddyfile line(s) and reloads
Caddy. Runs behind the existing auth gate (only the owner reaches the endpoint).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

CADDY = "/etc/caddy/Caddyfile"
LOGIN = "Rick"
_CADDY_BIN = "/usr/bin/caddy"


def set_password(new: str) -> dict:
    if not new or len(new) < 6:
        return {"ok": False, "reason": "пароль слишком короткий (мин. 6 символов)"}
    try:
        h = subprocess.run([_CADDY_BIN, "hash-password", "--plaintext", new],
                           capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"хэширование не удалось: {e}"}
    if not h.startswith("$2"):
        return {"ok": False, "reason": "не удалось получить хэш"}
    cur = subprocess.run(["sudo", "cat", CADDY], capture_output=True, text=True, timeout=15).stdout
    if "basic_auth" not in cur:
        return {"ok": False, "reason": "basic_auth не найден в Caddyfile"}
    new_cfg = re.sub(r"(?m)^\s*" + re.escape(LOGIN) + r" \$2[aby]\$\S+", f"\t\t{LOGIN} {h}", cur)
    tf = tempfile.NamedTemporaryFile("w", delete=False, suffix=".caddy")
    tf.write(new_cfg); tf.close()
    try:
        cp = subprocess.run(["sudo", "cp", tf.name, CADDY], capture_output=True, text=True, timeout=15)
        if cp.returncode != 0:
            return {"ok": False, "reason": f"запись Caddyfile: {cp.stderr[:150]}"}
        rl = subprocess.run(["sudo", "systemctl", "reload", "caddy"], capture_output=True, text=True, timeout=30)
        if rl.returncode != 0:
            return {"ok": False, "reason": f"reload caddy: {rl.stderr[:150]}"}
    finally:
        os.unlink(tf.name)
    return {"ok": True, "login": LOGIN, "note": "пароль изменён — войдите заново при следующем запросе"}
