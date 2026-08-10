# -*- coding: utf-8 -*-
"""Email magic-link mint/redeem (design/77).

Stores only SHA-256 of the one-time token (never plaintext).
Short TTL + single-use. Optional GCS sync for multi-instance Cloud Run.

INVARIANT: do not log raw tokens, sessions, or full emails.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_accounts import normalize_email
from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)

_LOCK = threading.RLock()

# WHY: short window limits URL leakage in mail clients / history.
DEFAULT_TTL_SEC = 15 * 60
MAX_TTL_SEC = 60 * 60
# WHY: blunt email bombing / open spam without locking out forever.
REQUEST_MAX = 5
REQUEST_WINDOW_SEC = 15 * 60


def magic_links_path() -> Path:
    return project_root() / "data" / "auth" / "magic_links.json"


def magic_attempts_path() -> Path:
    return project_root() / "data" / "auth" / "magic_attempts.json"


def magic_link_enabled() -> bool:
    """design/77 kill — ASR_EMAIL_MAGIC_LINK=0 off (default on)."""
    load_asr_env()
    v = (os.environ.get("ASR_EMAIL_MAGIC_LINK") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def magic_ttl_sec() -> int:
    load_asr_env()
    raw = (os.environ.get("ASR_EMAIL_MAGIC_TTL_SEC") or "").strip()
    try:
        n = int(raw) if raw else DEFAULT_TTL_SEC
    except ValueError:
        n = DEFAULT_TTL_SEC
    return max(60, min(n, MAX_TTL_SEC))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _email_key(email: str) -> str:
    """Rate-limit key — hash so logs/files do not store raw addresses."""
    em = normalize_email(email) or ""
    return hashlib.sha256(em.encode("utf-8")).hexdigest()[:32] if em else ""


def _empty_links() -> dict[str, Any]:
    return {"version": 1, "tokens": []}


def _empty_attempts() -> dict[str, Any]:
    return {"version": 1, "by_key": {}}


def _auth_gcs_object(filename: str) -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name("auth", filename)
    except Exception:  # noqa: BLE001
        return None


def _push(path: Path, filename: str) -> None:
    try:
        from sentence_reading.llm.gcs_sync import upload_bytes

        obj = _auth_gcs_object(filename)
        if not obj or not path.is_file():
            return
        raw = path.read_bytes()
        if not raw:
            return
        upload_bytes(obj, raw, content_type="application/json; charset=utf-8")
    except Exception as exc:  # noqa: BLE001
        log.debug("magic_link gcs push skip %s: %s", filename, exc)


def _pull(filename: str) -> dict[str, Any] | None:
    try:
        from sentence_reading.llm.gcs_sync import download_bytes

        obj = _auth_gcs_object(filename)
        if not obj:
            return None
        raw = download_bytes(obj)
        if not raw:
            return None
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.debug("magic_link gcs pull skip %s: %s", filename, exc)
        return None


def _read_links() -> dict[str, Any]:
    path = magic_links_path()
    local = _empty_links()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tokens"), list):
                local = {"version": 1, "tokens": list(data["tokens"])}
        except (OSError, json.JSONDecodeError):
            local = _empty_links()
    remote = _pull("magic_links.json")
    if not remote or not isinstance(remote.get("tokens"), list):
        return local
    # Merge by hash; used wins; else newer exp.
    by_h: dict[str, dict[str, Any]] = {}
    for src in (local, remote):
        for row in src.get("tokens") or []:
            if not isinstance(row, dict):
                continue
            h = str(row.get("hash") or "").strip()
            if len(h) < 16:
                continue
            prev = by_h.get(h)
            if prev is None:
                by_h[h] = dict(row)
                continue
            if bool(row.get("used")) and not bool(prev.get("used")):
                by_h[h] = dict(row)
                continue
            if bool(prev.get("used")) and not bool(row.get("used")):
                continue
            try:
                if int(row.get("exp") or 0) >= int(prev.get("exp") or 0):
                    by_h[h] = dict(row)
            except (TypeError, ValueError):
                by_h[h] = dict(row)
    return {"version": 1, "tokens": list(by_h.values())}


def _write_links(store: dict[str, Any]) -> None:
    path = magic_links_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prune expired/used older than 2d to keep file small.
    now = int(time.time())
    kept: list[dict[str, Any]] = []
    for row in store.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        try:
            exp = int(row.get("exp") or 0)
        except (TypeError, ValueError):
            continue
        used = bool(row.get("used"))
        if used and exp < now - 2 * 86400:
            continue
        if (not used) and exp < now - 86400:
            continue
        kept.append(row)
    out = {"version": 1, "tokens": kept[-500:]}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _push(path, "magic_links.json")


def _read_attempts() -> dict[str, Any]:
    path = magic_attempts_path()
    if not path.is_file():
        return _empty_attempts()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("by_key"), dict):
            return {"version": 1, "by_key": dict(data["by_key"])}
    except (OSError, json.JSONDecodeError):
        pass
    return _empty_attempts()


def _write_attempts(store: dict[str, Any]) -> None:
    path = magic_attempts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _push(path, "magic_attempts.json")


def _rate_limit_ok(email: str) -> bool:
    key = _email_key(email)
    if not key:
        return False
    now = int(time.time())
    with _LOCK:
        store = _read_attempts()
        remote = _pull("magic_attempts.json")
        if remote and isinstance(remote.get("by_key"), dict):
            # Shallow merge windows.
            for k, v in remote["by_key"].items():
                if k not in store["by_key"]:
                    store["by_key"][k] = v
        row = store["by_key"].get(key)
        times: list[int] = []
        if isinstance(row, dict):
            raw = row.get("ts")
            if isinstance(raw, list):
                for t in raw:
                    try:
                        ti = int(t)
                    except (TypeError, ValueError):
                        continue
                    if ti >= now - REQUEST_WINDOW_SEC:
                        times.append(ti)
        if len(times) >= REQUEST_MAX:
            store["by_key"][key] = {"ts": times}
            _write_attempts(store)
            return False
        times.append(now)
        store["by_key"][key] = {"ts": times}
        _write_attempts(store)
        return True


def mint_magic_token(email: str) -> dict[str, Any]:
    """
    Create one-time token for normalized email.
    Returns plaintext token once (caller emails / admin shows once).
    """
    if not magic_link_enabled():
        raise ValueError("magic_disabled")
    em = normalize_email(email)
    if not em:
        raise ValueError("bad_email")
    if not _rate_limit_ok(em):
        raise ValueError("rate_limited")
    raw = secrets.token_urlsafe(32)
    h = _hash_token(raw)
    now = int(time.time())
    exp = now + magic_ttl_sec()
    row = {
        "hash": h,
        "email_hash": _email_key(em),
        # WHY store normalized email encrypted-at-rest would be nicer;
        # for redeem we need the address → keep email (auth store already does).
        "email": em,
        "created_at": now,
        "exp": exp,
        "used": False,
    }
    with _LOCK:
        store = _read_links()
        store["tokens"].append(row)
        _write_links(store)
    return {"token": raw, "email": em, "expires_at": exp, "ttl_seconds": magic_ttl_sec()}


def redeem_magic_token(raw_token: str) -> str:
    """
    Consume token → return normalized email.
    Raises ValueError with stable codes: bad_token | expired | used | magic_disabled
    """
    if not magic_link_enabled():
        raise ValueError("magic_disabled")
    token = (raw_token or "").strip()
    if not token or len(token) > 200:
        raise ValueError("bad_token")
    h = _hash_token(token)
    now = int(time.time())
    with _LOCK:
        store = _read_links()
        found: dict[str, Any] | None = None
        for row in store.get("tokens") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("hash") or "") == h:
                found = row
                break
        if found is None:
            raise ValueError("bad_token")
        if bool(found.get("used")):
            raise ValueError("used")
        try:
            exp = int(found.get("exp") or 0)
        except (TypeError, ValueError):
            exp = 0
        if exp < now:
            found["used"] = True
            _write_links(store)
            raise ValueError("expired")
        em = normalize_email(str(found.get("email") or ""))
        if not em:
            raise ValueError("bad_token")
        found["used"] = True
        found["redeemed_at"] = now
        _write_links(store)
        return em
