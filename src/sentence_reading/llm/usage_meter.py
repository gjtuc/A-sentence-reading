"""
무엇을: uid별 Gemini·TTS·GCS 사용량 계측 + 추정 비용.
왜: 운영자 결제 · 유저는 자기 소비만 (design/27).
저장: data/usage/{uid}.json · GCS users/{uid}/usage.json
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.auth_google import current_gcs_uid, sanitize_uid
from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)
_LOCK = threading.RLock()

# 추정 단가 USD (무료 한도·청구서와 불일치 가능 — UI에 「추정」고지)
_PRICE = {
    "gemini_in_per_mtok": 0.30,
    "gemini_out_per_mtok": 2.50,
    "tts_neural2_per_mchar": 16.0,
    "gcs_upload_per_gb": 0.08,  # class A-ish rough
    "gcs_download_per_gb": 0.12,
}


def _empty(uid: str) -> dict[str, Any]:
    return {
        "version": 1,
        "uid": uid,
        "email": "",
        "updated_at": "",
        "totals": {
            "gemini_calls": 0,
            "gemini_input_chars": 0,
            "gemini_output_chars": 0,
            "tts_cloud_calls": 0,
            "tts_chars": 0,
            "gcs_ops": 0,
            "gcs_upload_bytes": 0,
            "gcs_download_bytes": 0,
        },
    }


def usage_local_path(uid: str) -> Path:
    return project_root() / "data" / "usage" / f"{uid}.json"


def admin_emails() -> set[str]:
    load_asr_env()
    raw = (os.environ.get("ASR_ADMIN_EMAILS") or "").strip()
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin_email(email: str | None) -> bool:
    if not email:
        return False
    return email.strip().lower() in admin_emails()


def estimate_usd(totals: dict[str, Any]) -> dict[str, float]:
    """문자≈토큰 근사 · 추정만."""
    gin = int(totals.get("gemini_input_chars") or 0)
    gout = int(totals.get("gemini_output_chars") or 0)
    tts = int(totals.get("tts_chars") or 0)
    up = int(totals.get("gcs_upload_bytes") or 0)
    down = int(totals.get("gcs_download_bytes") or 0)
    gemini = (gin / 1_000_000.0) * _PRICE["gemini_in_per_mtok"] + (
        gout / 1_000_000.0
    ) * _PRICE["gemini_out_per_mtok"]
    tts_usd = (tts / 1_000_000.0) * _PRICE["tts_neural2_per_mchar"]
    gcs_usd = (up / (1024**3)) * _PRICE["gcs_upload_per_gb"] + (
        down / (1024**3)
    ) * _PRICE["gcs_download_per_gb"]
    total = gemini + tts_usd + gcs_usd
    return {
        "gemini_usd": round(gemini, 6),
        "tts_usd": round(tts_usd, 6),
        "gcs_usd": round(gcs_usd, 6),
        "total_usd": round(total, 6),
    }


def _read(uid: str) -> dict[str, Any]:
    path = usage_local_path(uid)
    if not path.is_file():
        return _empty(uid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty(uid)
    if not isinstance(data, dict):
        return _empty(uid)
    base = _empty(uid)
    base.update({k: data.get(k, base.get(k)) for k in ("version", "uid", "email", "updated_at")})
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    merged = dict(base["totals"])
    for k in merged:
        try:
            merged[k] = int(totals.get(k) or 0)
        except (TypeError, ValueError):
            pass
    base["totals"] = merged
    base["uid"] = uid
    return base


def _write(row: dict[str, Any]) -> None:
    uid = sanitize_uid(str(row.get("uid") or ""))
    if not uid:
        return
    row["uid"] = uid
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = usage_local_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(row, ensure_ascii=False, indent=2) + "\n"
    path.write_text(raw, encoding="utf-8")
    try:
        from sentence_reading.llm.gcs_sync import object_name, upload_bytes

        # WHY: row uid 기준 경로 (personal_object_name 은 current context만 봄)
        # WHY: 계측 push 는 재귀 계측하지 않음 — upload_bytes(meter=False)
        obj = object_name("users", uid, "usage.json")
        if obj:
            upload_bytes(
                obj,
                raw.encode("utf-8"),
                content_type="application/json; charset=utf-8",
                meter=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.debug("usage gcs push skip: %s", exc)


def record(
    *,
    gemini_calls: int = 0,
    gemini_input_chars: int = 0,
    gemini_output_chars: int = 0,
    tts_cloud_calls: int = 0,
    tts_chars: int = 0,
    gcs_ops: int = 0,
    gcs_upload_bytes: int = 0,
    gcs_download_bytes: int = 0,
    email: str = "",
    uid: str | None = None,
) -> None:
    uid_s = sanitize_uid(uid) if uid else current_gcs_uid()
    if not uid_s:
        return
    with _LOCK:
        row = _read(uid_s)
        if email:
            row["email"] = email[:320]
        t = row["totals"]
        t["gemini_calls"] += max(0, int(gemini_calls))
        t["gemini_input_chars"] += max(0, int(gemini_input_chars))
        t["gemini_output_chars"] += max(0, int(gemini_output_chars))
        t["tts_cloud_calls"] += max(0, int(tts_cloud_calls))
        t["tts_chars"] += max(0, int(tts_chars))
        t["gcs_ops"] += max(0, int(gcs_ops))
        t["gcs_upload_bytes"] += max(0, int(gcs_upload_bytes))
        t["gcs_download_bytes"] += max(0, int(gcs_download_bytes))
        _write(row)


def public_usage(uid: str | None = None, *, email: str = "") -> dict[str, Any]:
    uid_s = sanitize_uid(uid) if uid else current_gcs_uid()
    if not uid_s:
        return {"ok": False, "error": "auth_required"}
    with _LOCK:
        row = _read(uid_s)
    if email and not row.get("email"):
        row["email"] = email
    est = estimate_usd(row["totals"])
    return {
        "ok": True,
        "uid": uid_s,
        "email": row.get("email") or email,
        "updated_at": row.get("updated_at") or "",
        "totals": row["totals"],
        "estimate_usd": est,
        "estimate_note": "추정(무료한도·청구서와 다를 수 있음)",
        "prices": dict(_PRICE),
    }


def admin_usage_report() -> dict[str, Any]:
    from sentence_reading.llm.auth_accounts import accounts_path

    users: list[dict[str, Any]] = []
    # accounts.json 유저 + 로컬 usage 파일
    uids: set[str] = set()
    try:
        raw = json.loads(accounts_path().read_text(encoding="utf-8"))
        for uid in (raw.get("users") or {}):
            s = sanitize_uid(str(uid))
            if s:
                uids.add(s)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    usage_dir = project_root() / "data" / "usage"
    if usage_dir.is_dir():
        for p in usage_dir.glob("*.json"):
            s = sanitize_uid(p.stem)
            if s:
                uids.add(s)
    grand = _empty("_total")["totals"]
    for uid in sorted(uids):
        with _LOCK:
            row = _read(uid)
        est = estimate_usd(row["totals"])
        users.append(
            {
                "uid": uid,
                "email": row.get("email") or "",
                "totals": row["totals"],
                "estimate_usd": est,
                "updated_at": row.get("updated_at") or "",
            }
        )
        for k, v in row["totals"].items():
            grand[k] = int(grand.get(k) or 0) + int(v or 0)
    return {
        "ok": True,
        "users": users,
        "grand_totals": grand,
        "grand_estimate_usd": estimate_usd(grand),
        "estimate_note": "추정(무료한도·청구서와 다를 수 있음)",
        "prices": dict(_PRICE),
    }


def record_gemini_response(prompt: str, response: Any) -> None:
    """generate_content 응답에서 usage 또는 문자 근사."""
    in_c = len(prompt or "")
    out_c = 0
    try:
        um = getattr(response, "usage_metadata", None)
        if um is not None:
            pt = int(getattr(um, "prompt_token_count", 0) or 0)
            ct = int(getattr(um, "candidates_token_count", 0) or 0)
            if pt or ct:
                in_c, out_c = pt, ct
        text = getattr(response, "text", None)
        if out_c == 0 and text:
            out_c = len(str(text))
    except Exception:  # noqa: BLE001
        pass
    record(
        gemini_calls=1,
        gemini_input_chars=in_c,
        gemini_output_chars=out_c,
    )
