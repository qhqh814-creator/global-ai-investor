"""Local secret storage (P3/P6): Windows DPAPI-encrypted, never in logs/git."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import win32crypt

SECRET_FILE = "secrets.dat"


def _root() -> Path:
    return Path(os.environ.get("GAI_ROOT", r"F:\GlobalAIInvestor"))


def _path() -> Path:
    d = _root() / "data" / "settings"
    d.mkdir(parents=True, exist_ok=True)
    return d / SECRET_FILE


def _load() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def set_secret(name: str, value: str) -> None:
    """Encrypt with the current Windows user's DPAPI key and store base64."""
    if not value:
        raise ValueError("secret value is empty")
    encrypted = win32crypt.CryptProtectData(value.encode("utf-8"), name, None, None, None, 0)
    data = _load()
    data[name] = base64.b64encode(encrypted).decode("ascii")
    p = _path()
    p.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def get_secret(name: str) -> str | None:
    raw = _load().get(name)
    if not raw:
        return None
    try:
        return win32crypt.CryptUnprotectData(base64.b64decode(raw), None, None, None, 0)[1].decode("utf-8")
    except Exception:  # noqa: BLE001 - wrong user/machine or corrupted file
        return None


def delete_secret(name: str) -> bool:
    data = _load()
    if name not in data:
        return False
    del data[name]
    _path().write_text(json.dumps(data), encoding="utf-8")
    return True
