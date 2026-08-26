"""design/144 — paper library retention TTL (90d default · warn · extend · reading grace)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

RETENTION_DAYS = int(os.environ.get("ASR_PAPER_RETENTION_DAYS", "90") or "90")
WARN_DAYS = int(os.environ.get("ASR_PAPER_RETENTION_WARN_DAYS", "30") or "30")
EXTEND_DAYS = int(os.environ.get("ASR_PAPER_RETENTION_EXTEND_DAYS", "14") or "14")
READING_GRACE_DAYS = int(
    os.environ.get("ASR_PAPER_RETENTION_READING_GRACE_DAYS", "3") or "3"
)


def retention_enabled() -> bool:
    """Kill: ASR_PAPER_RETENTION=0 disables TTL purge/warn/extend."""
    v = (os.environ.get("ASR_PAPER_RETENTION") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def default_expires_at(*, now: datetime | None = None) -> str:
    """Fresh retention deadline (ISO UTC)."""
    base = now or _utc_now()
    return (base + timedelta(days=RETENTION_DAYS)).isoformat()


def ensure_entry_retention(entry: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Migrate missing expires_at → now+90 (배포 후 공평 시작)."""
    out = dict(entry)
    if not retention_enabled():
        return out
    if _parse_iso(out.get("expires_at")) is not None:
        return out
    base = now or _utc_now()
    out["expires_at"] = default_expires_at(now=base)
    return out


def expires_at_dt(entry: dict[str, Any]) -> datetime | None:
    return _parse_iso(entry.get("expires_at"))


def is_expired(entry: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not retention_enabled():
        return False
    exp = expires_at_dt(entry)
    if exp is None:
        return False
    return (now or _utc_now()) >= exp


def days_until_expiry(entry: dict[str, Any], *, now: datetime | None = None) -> int | None:
    exp = expires_at_dt(entry)
    if exp is None:
        return None
    delta = exp - (now or _utc_now())
    # ceil so “0 days” on last calendar day still warns
    days = delta.total_seconds() / 86400.0
    return int(days) if days >= 0 else -1


def retention_public(entry: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Client-facing retention block for list API."""
    if not retention_enabled():
        return {
            "enabled": False,
            "days_until_expiry": None,
            "warn": False,
            "can_extend": False,
            "extend_days": EXTEND_DAYS,
        }
    exp = entry.get("expires_at")
    days = days_until_expiry(entry, now=now)
    warn = days is not None and 0 < days <= WARN_DAYS
    can_extend = days is not None and 0 < days <= WARN_DAYS
    return {
        "enabled": True,
        "expires_at": exp,
        "days_until_expiry": days,
        "warn": warn,
        "can_extend": can_extend,
        "extend_days": EXTEND_DAYS,
    }


def can_extend_retention(entry: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not retention_enabled():
        return False
    days = days_until_expiry(entry, now=now)
    return days is not None and 0 < days <= WARN_DAYS


def extend_retention(entry: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """+EXTEND_DAYS from current expires_at. Raises ValueError if not allowed."""
    if not can_extend_retention(entry, now=now):
        raise ValueError("extend_not_allowed")
    exp = expires_at_dt(entry)
    if exp is None:
        raise ValueError("missing_expires_at")
    out = dict(entry)
    new_exp = exp + timedelta(days=EXTEND_DAYS)
    out["expires_at"] = new_exp.isoformat()
    out["retention_extended_count"] = int(out.get("retention_extended_count") or 0) + 1
    out["last_extended_at"] = (now or _utc_now()).isoformat()
    # WHY: manual extend starts a new expiry window — grace may apply again later.
    out.pop("reading_grace_from", None)
    return out


def apply_reading_grace(
    entry: dict[str, Any], *, now: datetime | None = None
) -> tuple[dict[str, Any], bool]:
    """If expired while reading: expires_at += READING_GRACE_DAYS (once per expiry instant)."""
    if not retention_enabled():
        return entry, False
    base = now or _utc_now()
    exp = expires_at_dt(entry)
    if exp is None or base < exp:
        return entry, False
    grace_from = str(entry.get("reading_grace_from") or "").strip()
    if grace_from and grace_from == exp.isoformat():
        return entry, False
    out = dict(entry)
    out["reading_grace_from"] = exp.isoformat()
    out["expires_at"] = (exp + timedelta(days=READING_GRACE_DAYS)).isoformat()
    return out, True


def reset_retention_on_save(*, now: datetime | None = None) -> dict[str, Any]:
    """Reanalyze / new save — full 90-day window from now."""
    return {
        "expires_at": default_expires_at(now=now or _utc_now()),
        "retention_extended_count": 0,
    }
