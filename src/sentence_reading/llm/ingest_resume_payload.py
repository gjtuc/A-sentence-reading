"""
design/112 — pack/unpack ingest mid-stage payloads (owner-scoped GCS).

WHY: keep paper text out of job envelope / public poll; payloads live under
users/{uid}/ingest_payloads/ only.
EDGE: never trust client paths; caller must pass session owner_uid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sentence_reading.llm.typography import PIPELINE_VERSION
from sentence_reading.models import Sentence


_PAYLOAD_V = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sentence_to_dict(s: Sentence) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": s.id,
        "text": s.text,
        "section": s.section,
        "start_char": s.start_char,
        "end_char": s.end_char,
        "text_ko": s.text_ko or "",
        "text_ko_stage": s.text_ko_stage or "",
    }
    if s.quality_flags:
        out["quality_flags"] = list(s.quality_flags)
    return out


def sentence_from_dict(d: dict[str, Any]) -> Sentence | None:
    if not isinstance(d, dict):
        return None
    sid = str(d.get("id") or "").strip()
    text = str(d.get("text") or "")
    if not sid:
        return None
    return Sentence(
        id=sid,
        text=text,
        section=(str(d["section"]) if d.get("section") is not None else None),
        start_char=d.get("start_char") if isinstance(d.get("start_char"), int) else None,
        end_char=d.get("end_char") if isinstance(d.get("end_char"), int) else None,
        text_ko=str(d.get("text_ko") or ""),
        text_ko_stage=str(d.get("text_ko_stage") or ""),
        quality_flags=tuple(
            str(f).strip()
            for f in (d.get("quality_flags") or [])
            if str(f).strip()
        ),
    )


def base_payload(
    *,
    job_id: str,
    owner_uid: str,
    content_hash: str,
    completed: str,
) -> dict[str, Any]:
    return {
        "v": _PAYLOAD_V,
        "job_id": job_id,
        "owner_uid": owner_uid,
        "pipeline_version": PIPELINE_VERSION,
        "content_hash": str(content_hash or "").strip().lower(),
        "completed": completed,
        "updated_at": utc_now_iso(),
    }


def decision_to_dict(decision: Any) -> dict[str, Any]:
    if decision is None:
        return {}
    return {
        "verdict": str(getattr(decision, "verdict", "") or ""),
        "bad_pages": [int(x) for x in (getattr(decision, "bad_pages", None) or [])],
        "notes": str(getattr(decision, "notes", "") or ""),
        "source": str(getattr(decision, "source", "") or ""),
        "warning": getattr(decision, "warning", None),
    }
