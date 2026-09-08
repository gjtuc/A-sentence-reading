"""design/187 — wipe shadowing + voice after device migrate ACK."""

from __future__ import annotations

import logging
from typing import Any

from sentence_reading.llm.gcs_sync import (
    delete_bytes,
    delete_prefix,
    gcs_client_ready,
    gcs_config,
    personal_object_name,
)
from sentence_reading.llm.user_artifacts_local_sot import shadowing_local_sot_enabled
from sentence_reading.llm.voice_gcs import voice_blob_object

log = logging.getLogger(__name__)


def refuse_shadowing_cloud_write_if_local_sot() -> dict[str, object] | None:
    if not shadowing_local_sot_enabled():
        return None
    return {
        "ok": False,
        "error": "shadowing_local_sot",
        "message": "shadowing/voice are device SoT; cloud write refused",
        "available": False,
    }


def wipe_shadowing_and_voice_for_uid() -> dict[str, Any]:
    """Best-effort delete users/{uid}/shadowing/ and users/{uid}/voice/ prefixes."""
    ready, _ = gcs_client_ready()
    if not gcs_config().enabled or not ready:
        return {"ok": False, "error": "gcs_unavailable", "shadowing_n": 0, "voice_n": 0}
    out: dict[str, Any] = {"ok": True, "shadowing_n": 0, "voice_n": 0}
    sh = personal_object_name("shadowing")
    if sh:
        # prefix delete needs trailing path; personal_object_name("shadowing") may be dir root
        pref = sh if sh.endswith("/") else sh.rstrip("/") + "/"
        try:
            stats = delete_prefix(pref)
            out["shadowing_n"] = int(stats.get("deleted_n") or 0)
        except Exception as exc:  # noqa: BLE001
            log.warning("shadowing wipe failed: %s", exc)
            out["ok"] = False
            out["shadowing_error"] = str(exc)[:200]
    vo = personal_object_name("voice")
    if vo:
        pref = vo if vo.endswith("/") else vo.rstrip("/") + "/"
        try:
            stats = delete_prefix(pref)
            out["voice_n"] = int(stats.get("deleted_n") or 0)
        except Exception as exc:  # noqa: BLE001
            log.warning("voice wipe failed: %s", exc)
            out["ok"] = False
            out["voice_error"] = str(exc)[:200]
    return out


def wipe_voice_blob_key(blob_key: str) -> bool:
    obj = voice_blob_object(blob_key)
    if not obj:
        return False
    return bool(delete_bytes(obj))
