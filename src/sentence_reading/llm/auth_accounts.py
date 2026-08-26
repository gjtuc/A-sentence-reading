"""
무엇을: 내부 사용자 UID + Google/카카오/이메일 provider 연결 레지스트리.
왜: 같은 사람이 여러 로그인 수단을 써도 한 GCS 칸 (design/23).
저장: data/auth/accounts.json · (선택) GCS {prefix}/auth/accounts.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_google import AuthUser, sanitize_uid

log = logging.getLogger(__name__)

_LOCK = threading.RLock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROVIDERS = ("google", "kakao", "email")


def accounts_path() -> Path:
    return project_root() / "data" / "auth" / "accounts.json"


def _empty() -> dict[str, Any]:
    return {"version": 1, "users": {}, "by_provider": {}}


def _read_disk() -> dict[str, Any]:
    path = accounts_path()
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    users = data.get("users")
    by_p = data.get("by_provider")
    if not isinstance(users, dict):
        users = {}
    if not isinstance(by_p, dict):
        by_p = {}
    return _reconcile_by_provider({"version": 1, "users": users, "by_provider": by_p})


def _reconcile_by_provider(store: dict[str, Any]) -> dict[str, Any]:
    """by_provider ↔ users.providers 정합. 해제·GCS 병합 후 stale 키 제거."""
    users = store.get("users")
    by_p = store.get("by_provider")
    if not isinstance(users, dict) or not isinstance(by_p, dict):
        return store
    for pk, uid in list(by_p.items()):
        if not isinstance(pk, str) or ":" not in pk:
            del by_p[pk]
            continue
        prov, sub = pk.split(":", 1)
        if prov not in PROVIDERS:
            del by_p[pk]
            continue
        if not isinstance(uid, str) or uid not in users:
            del by_p[pk]
            continue
        row = users.get(uid)
        if not isinstance(row, dict):
            del by_p[pk]
            continue
        linked = row.get("providers")
        if not isinstance(linked, dict):
            del by_p[pk]
            continue
        if linked.get(prov) != sub:
            del by_p[pk]
    return store


def _write_disk(store: dict[str, Any]) -> None:
    path = accounts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(store, ensure_ascii=False, indent=2) + "\n"
    path.write_text(raw, encoding="utf-8")
    try:
        from sentence_reading.llm.gcs_sync import object_name, upload_bytes

        obj = object_name("auth", "accounts.json")
        if obj:
            upload_bytes(
                obj, raw.encode("utf-8"), content_type="application/json; charset=utf-8"
            )
    except Exception as exc:  # noqa: BLE001
        log.debug("accounts gcs push skip: %s", exc)


def pull_accounts_from_gcs() -> bool:
    """기동 시 원격 레지스트리 pull (있으면 로컬보다 우선하지 않고 병합)."""
    try:
        from sentence_reading.llm.gcs_sync import download_bytes, object_name

        obj = object_name("auth", "accounts.json")
        if not obj:
            return False
        raw = download_bytes(obj)
        if not raw:
            return False
        remote = json.loads(raw.decode("utf-8"))
        if not isinstance(remote, dict):
            return False
    except Exception as exc:  # noqa: BLE001
        log.debug("accounts gcs pull skip: %s", exc)
        return False
    with _LOCK:
        local = _read_disk()
        merged = _merge_stores(local, remote)
        _write_disk(merged)
    return True


def _merge_stores(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """by_provider 충돌 시 a 우선 · users 메타는 키 합집합."""
    out = _empty()
    users_a = a.get("users") if isinstance(a.get("users"), dict) else {}
    users_b = b.get("users") if isinstance(b.get("users"), dict) else {}
    by_a = a.get("by_provider") if isinstance(a.get("by_provider"), dict) else {}
    by_b = b.get("by_provider") if isinstance(b.get("by_provider"), dict) else {}
    out["users"] = {**users_b, **users_a}
    out["by_provider"] = {**by_b, **by_a}
    # by_provider → users 정합
    for pk, uid in list(out["by_provider"].items()):
        if uid not in out["users"]:
            del out["by_provider"][pk]
    return _reconcile_by_provider(out)


def _provider_key(provider: str, subject: str) -> str | None:
    p = (provider or "").strip().lower()
    s = (subject or "").strip()
    if p not in PROVIDERS or not s or len(s) > 320:
        return None
    if p == "email":
        s = s.lower()
    return f"{p}:{s}"


def new_internal_uid() -> str:
    """u + 22 hex — sanitize_uid 통과."""
    return "u" + uuid.uuid4().hex[:22]


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dig = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200_000, dklen=32
    )
    return f"pbkdf2_sha256$200000${salt.hex()}${dig.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds_s, salt_hex, dig_hex = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        dig = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, rounds, dklen=32
        )
        return secrets.compare_digest(dig.hex(), dig_hex)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str | None:
    e = (email or "").strip().lower()
    if not e or len(e) > 320 or not _EMAIL_RE.match(e):
        return None
    return e


def get_user_record(uid: str) -> dict[str, Any] | None:
    uid_s = sanitize_uid(uid)
    if not uid_s:
        return None
    with _LOCK:
        store = _read_disk()
        row = store["users"].get(uid_s)
        return dict(row) if isinstance(row, dict) else None


def lookup_uid(provider: str, subject: str) -> str | None:
    pk = _provider_key(provider, subject)
    if not pk:
        return None
    with _LOCK:
        store = _read_disk()
        uid = store["by_provider"].get(pk)
        return sanitize_uid(str(uid)) if uid else None


def resolve_or_create(
    provider: str,
    subject: str,
    *,
    email: str = "",
    name: str = "",
    picture: str = "",
    password: str | None = None,
    prefer_uid: str | None = None,
) -> AuthUser:
    """
    provider 로 로그인. 없으면 새 내부 UID 생성(또는 prefer_uid / 레거시 subject).
    Google 기존 칸 호환: prefer_uid 없으면 google subject 를 uid 로 재사용.
    """
    pk = _provider_key(provider, subject)
    if not pk:
        raise ValueError("invalid provider subject")
    p = provider.strip().lower()
    sub = subject.strip()
    if p == "email":
        sub = sub.lower()

    with _LOCK:
        store = _read_disk()
        existing = store["by_provider"].get(pk)
        if existing and existing in store["users"]:
            row = store["users"][existing]
            if password is not None:
                ph = str(row.get("password_hash") or "")
                if not ph or not verify_password(password, ph):
                    raise ValueError("bad_password")
            return AuthUser(
                uid=str(existing),
                email=str(row.get("email") or email or ""),
                name=str(row.get("name") or name or ""),
                picture=str(row.get("picture") or picture or ""),
            )

        # 신규
        if prefer_uid and sanitize_uid(prefer_uid):
            uid = prefer_uid
        elif p == "google" and sanitize_uid(sub):
            # WHY: 0.2.18 이 google sub 를 칸으로 씀 — 첫 로그인 호환
            uid = sub
        else:
            uid = new_internal_uid()
            while uid in store["users"]:
                uid = new_internal_uid()

        if uid in store["users"] and pk not in store["by_provider"]:
            # uid 충돌(다른 사람 칸) — 새 uid
            uid = new_internal_uid()

        row = store["users"].get(uid) if isinstance(store["users"].get(uid), dict) else {}
        providers = dict(row.get("providers") or {}) if isinstance(row.get("providers"), dict) else {}
        providers[p] = sub
        email_n = normalize_email(email) or normalize_email(str(row.get("email") or "")) or ""
        new_row: dict[str, Any] = {
            "uid": uid,
            "email": email_n or str(row.get("email") or ""),
            "name": (name or str(row.get("name") or ""))[:200],
            "picture": (picture or str(row.get("picture") or ""))[:500],
            "providers": providers,
        }
        if p == "email":
            # design/77: magic-link may create passwordless email accounts
            # (password is None). Password register/login still requires ≥8.
            if password is not None:
                if len(password) < 8:
                    raise ValueError("password_too_short")
                new_row["password_hash"] = hash_password(password)
        elif row.get("password_hash"):
            new_row["password_hash"] = row["password_hash"]

        store["users"][uid] = new_row
        store["by_provider"][pk] = uid
        _write_disk(store)
        return AuthUser(
            uid=uid,
            email=str(new_row.get("email") or ""),
            name=str(new_row.get("name") or ""),
            picture=str(new_row.get("picture") or ""),
        )


def link_provider(
    uid: str,
    provider: str,
    subject: str,
    *,
    email: str = "",
    name: str = "",
    picture: str = "",
    password: str | None = None,
) -> AuthUser:
    """로그인된 uid 에 provider 연결. 이미 다른 uid 면 ValueError('conflict')."""
    uid_s = sanitize_uid(uid)
    pk = _provider_key(provider, subject)
    if not uid_s or not pk:
        raise ValueError("invalid")
    p = provider.strip().lower()
    sub = subject.strip()
    if p == "email":
        sub = sub.lower()

    with _LOCK:
        store = _read_disk()
        if uid_s not in store["users"]:
            raise ValueError("user_missing")
        other = store["by_provider"].get(pk)
        if other and other != uid_s:
            raise ValueError("conflict")
        row = dict(store["users"][uid_s])
        providers = dict(row.get("providers") or {})
        providers[p] = sub
        row["providers"] = providers
        if email:
            en = normalize_email(email)
            if en:
                row["email"] = en
        if name:
            row["name"] = name[:200]
        if picture:
            row["picture"] = picture[:500]
        # WHY (146a): magic-link email link passes password=None — no hash.
        # Password path (POST /email/link) still requires length >= 8.
        if p == "email" and password is not None:
            if len(password) < 8:
                raise ValueError("password_too_short")
            row["password_hash"] = hash_password(password)
        store["users"][uid_s] = row
        store["by_provider"][pk] = uid_s
        _write_disk(store)
        return AuthUser(
            uid=uid_s,
            email=str(row.get("email") or ""),
            name=str(row.get("name") or ""),
            picture=str(row.get("picture") or ""),
        )


def unlink_provider(uid: str, provider: str) -> AuthUser:
    uid_s = sanitize_uid(uid)
    p = (provider or "").strip().lower()
    if not uid_s or p not in PROVIDERS:
        raise ValueError("invalid")
    with _LOCK:
        store = _read_disk()
        row = store["users"].get(uid_s)
        if not isinstance(row, dict):
            raise ValueError("user_missing")
        providers = dict(row.get("providers") or {})
        if p not in providers:
            raise ValueError("not_linked")
        if len(providers) <= 1:
            raise ValueError("last_provider")
        sub = providers.pop(p)
        pk = _provider_key(p, str(sub))
        if pk and store["by_provider"].get(pk) == uid_s:
            del store["by_provider"][pk]
        row["providers"] = providers
        if p == "email":
            row.pop("password_hash", None)
        store["users"][uid_s] = row
        _write_disk(store)
        return AuthUser(
            uid=uid_s,
            email=str(row.get("email") or ""),
            name=str(row.get("name") or ""),
            picture=str(row.get("picture") or ""),
        )


def public_user_with_providers(user: AuthUser) -> dict[str, Any]:
    row = get_user_record(user.uid) or {}
    providers = row.get("providers") if isinstance(row.get("providers"), dict) else {}
    linked = sorted([k for k in providers if k in PROVIDERS])
    out = user.public_dict()
    out["providers"] = linked
    return out
