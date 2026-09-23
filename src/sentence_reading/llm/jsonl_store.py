"""Shared JSONL append / rotate / GCS merge (design/318).

Buses keep their own kinds, kill switches, and schemas. This module is
only the file+object body: parse, retain, trim, pull, push.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_event_ts(raw: Any) -> datetime | None:
    """Parse ISO-Z ``ts`` to UTC. Missing/bad → None (caller keeps the row)."""
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def filter_retained(
    events: list[dict[str, Any]],
    *,
    keep_days: int,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Drop rows older than keep_days. Returns (kept, dropped_n).

    keep_days <= 0 leaves every row. Missing/bad ts is kept.
    """
    days = int(keep_days)
    if days <= 0 or not events:
        return list(events), 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for ev in events:
        if not isinstance(ev, dict):
            dropped += 1
            continue
        ts = parse_event_ts(ev.get("ts"))
        if ts is None:
            ts = parse_event_ts(ev.get("at"))
        if ts is not None and ts < cutoff:
            dropped += 1
            continue
        kept.append(ev)
    return kept, dropped


def parse_jsonl_events(raw: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id"):
            out.append(obj)
    return out


def encode_jsonl_events(events: list[dict[str, Any]]) -> bytes:
    if not events:
        return b""
    return (
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
    ).encode("utf-8")


def trim_jsonl_events(
    events: list[dict[str, Any]],
    *,
    max_keep: int,
    max_body_bytes: int,
) -> list[dict[str, Any]]:
    """Newest-tail by count, then newest half if the blob is over max_body."""
    if len(events) > max_keep:
        events = events[-max_keep:]
    blob = encode_jsonl_events(events)
    if len(blob) > max_body_bytes:
        events = events[len(events) // 2 :]
    return events


def gcs_object_name(folder: str, filename: str = "events.jsonl") -> str | None:
    try:
        from sentence_reading.llm.gcs_sync import object_name

        return object_name(folder, filename)
    except Exception:  # noqa: BLE001
        return None


def pull_events_raw(
    *,
    local_path: Path,
    gcs_object: str | None,
    logger: logging.Logger,
    label: str,
) -> bytes:
    if gcs_object:
        try:
            from sentence_reading.llm.gcs_sync import download_bytes, gcs_config

            if gcs_config().enabled:
                raw = download_bytes(gcs_object, meter=False)
                if raw is not None:
                    return raw
        except Exception:  # noqa: BLE001
            logger.warning("%s gcs pull failed", label, exc_info=True)
    if local_path.is_file():
        return local_path.read_bytes()
    return b""


def push_events_raw(
    *,
    raw: bytes,
    local_path: Path,
    gcs_object: str | None,
    logger: logging.Logger,
    label: str,
) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(raw)
    if not gcs_object:
        return
    try:
        from sentence_reading.llm.gcs_sync import gcs_config, upload_bytes

        if not gcs_config().enabled:
            return
        upload_bytes(
            gcs_object, raw, content_type="application/x-ndjson; charset=utf-8"
        )
    except Exception:  # noqa: BLE001
        logger.warning("%s gcs push failed", label, exc_info=True)
