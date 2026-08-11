"""design/80 — per-user shadowing chunk plans (Gemini).

Store under users/{uid}/shadowing/chunks/{cache_id}.json (GCS) with local
disk fallback. Practice UI is Later; this module only plans growing prefixes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from sentence_reading.llm.auth_google import sanitize_uid
from sentence_reading.llm.env import gemini_api_key, gemini_available, gemini_model
from sentence_reading.llm.gcs_sync import (
    download_bytes,
    gcs_client_ready,
    personal_object_name,
    upload_bytes,
)
from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

log = logging.getLogger(__name__)

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_MAX_SENTENCE_CHARS = 2000
_MAX_SENTENCES = 400
_MAX_STORE_BYTES = 2_000_000

_SYSTEM = """You plan shadowing (listen-and-speak) practice chunks for ONE sentence.
Return ONLY a JSON array of strings. Each string is a growing practice unit:
the first is a short prefix, each later item must start with the previous text
and add more of the sentence, and the LAST item must equal the full sentence
(plain text, same characters/spacing as given).
Include Korean or mixed EN/KO exactly as in the source — do not translate.
Choose how many steps yourself (quality over a fixed count).
No markdown fences, no commentary.
"""


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _plain(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def safe_cache_id(raw: str | None) -> str | None:
    cid = (raw or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return cid


def chunks_object_name(cache_id: str) -> str | None:
    cid = safe_cache_id(cache_id)
    if not cid:
        return None
    return personal_object_name("shadowing", "chunks", f"{cid}.json")


def _local_path(uid: str, cache_id: str) -> Path | None:
    u = sanitize_uid(uid)
    cid = safe_cache_id(cache_id)
    if not u or not cid:
        return None
    return _project_root() / "data" / "shadowing" / "users" / u / f"{cid}.json"


def empty_plan(cache_id: str) -> dict[str, Any]:
    return {
        "version": 1,
        "cache_id": cache_id,
        "status": "empty",
        "error": None,
        "sentences": {},
    }


def _decode_plan(raw: bytes | None, cache_id: str) -> dict[str, Any]:
    if not raw or len(raw) > _MAX_STORE_BYTES:
        return empty_plan(cache_id)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return empty_plan(cache_id)
    if not isinstance(data, dict):
        return empty_plan(cache_id)
    data["version"] = 1
    data["cache_id"] = cache_id
    if not isinstance(data.get("sentences"), dict):
        data["sentences"] = {}
    st = data.get("status")
    if st not in ("ok", "error", "empty", "pending"):
        data["status"] = "empty"
    return data


def load_chunk_plan(*, uid: str, cache_id: str) -> dict[str, Any]:
    """Load plan for uid+cache_id. Never reads another user's object."""
    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        return empty_plan(cache_id or "")
    # Prefer GCS when ready; else local file under this uid only.
    ready, _ = gcs_client_ready()
    if ready:
        name = chunks_object_name(cid)
        if name:
            # WHY: personal_object_name uses current_gcs_uid — caller must set it.
            raw = download_bytes(name)
            if raw is not None:
                return _decode_plan(raw, cid)
    path = _local_path(u, cid)
    if path and path.is_file():
        try:
            return _decode_plan(path.read_bytes(), cid)
        except OSError:
            return empty_plan(cid)
    return empty_plan(cid)


def save_chunk_plan(*, uid: str, cache_id: str, plan: dict[str, Any]) -> None:
    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        raise ValueError("invalid_id")
    payload = dict(plan)
    payload["version"] = 1
    payload["cache_id"] = cid
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(raw) > _MAX_STORE_BYTES:
        raise ValueError("plan_too_large")
    ready, _ = gcs_client_ready()
    if ready:
        name = chunks_object_name(cid)
        if name:
            upload_bytes(name, raw, content_type="application/json")
    path = _local_path(u, cid)
    if path is None:
        raise ValueError("invalid_id")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def delete_chunk_plan(*, uid: str, cache_id: str) -> bool:
    """design/102 — remove chunk plan object + local file for uid+cache_id."""
    from sentence_reading.llm.gcs_sync import delete_bytes

    cid = safe_cache_id(cache_id)
    u = sanitize_uid(uid)
    if not cid or not u:
        return False
    ok = True
    ready, _ = gcs_client_ready()
    if ready:
        name = chunks_object_name(cid)
        if name:
            try:
                delete_bytes(name)
            except Exception:  # noqa: BLE001
                ok = False
    path = _local_path(u, cid)
    if path is not None and path.is_file():
        try:
            path.unlink()
        except OSError:
            ok = False
    return ok


def _parse_chunks_json(raw: str, full: str) -> list[str] | None:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or not data:
        return None
    out: list[str] = []
    for item in data:
        if not isinstance(item, str):
            return None
        t = _plain(item)
        if not t:
            return None
        out.append(t)
    # Last must match full; each step grows.
    if out[-1] != full:
        # EDGE: model drops punctuation — accept if full startswith last or vice versa soft fail
        if full.startswith(out[-1]) or out[-1].startswith(full):
            out[-1] = full
        else:
            out.append(full)
    prev = ""
    fixed: list[str] = []
    for step in out:
        if prev and not step.startswith(prev):
            # fail-closed for this sentence
            return None
        if step == prev:
            continue
        fixed.append(step)
        prev = step
    return fixed or [full]


def plan_sentence_chunks(
    text: str,
    *,
    generate: Callable[[str, str], str | None] | None = None,
) -> list[str]:
    """Return growing chunk strings for one sentence. Raises ValueError on fail."""
    full = _plain(text)
    if not full:
        raise ValueError("empty_sentence")
    if len(full) > _MAX_SENTENCE_CHARS:
        full = full[:_MAX_SENTENCE_CHARS]
    # Short sentences: single chunk (no Gemini cost).
    if len(full.split()) <= 3 and len(full) < 40:
        return [full]

    def _default_generate(system: str, user: str) -> str | None:
        if not gemini_api_key():
            return None
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_api_key())
        response = client.models.generate_content(
            model=gemini_model(),
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.4,
                max_output_tokens=1024,
            ),
        )
        try:
            from sentence_reading.llm.usage_meter import record_gemini_response

            record_gemini_response(user, response)
        except Exception:  # noqa: BLE001
            pass
        return (getattr(response, "text", None) or "").strip() or None

    gen = generate or _default_generate
    raw = gen(_SYSTEM, f"Sentence:\n{full}")
    if not raw:
        raise ValueError("gemini_unavailable")
    chunks = _parse_chunks_json(raw, full)
    if not chunks:
        raise ValueError("bad_chunk_plan")
    return chunks


def build_chunk_plan(
    *,
    uid: str,
    cache_id: str,
    sentences: list[dict[str, Any]],
    generate: Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """
    Build full plan for a paper. Fail-closed: any hard failure → status=error
    (partial sentences may still be present for debugging; UI must not treat as ok).
    """
    if not shadowing_practice_enabled():
        raise PermissionError("shadowing_disabled")
    if not sanitize_uid(uid) or not safe_cache_id(cache_id):
        raise ValueError("invalid_id")
    if not isinstance(sentences, list) or len(sentences) > _MAX_SENTENCES:
        raise ValueError("bad_sentences")

    plan = empty_plan(cache_id)
    plan["status"] = "pending"
    plan["error"] = None
    built: dict[str, Any] = {}
    err: str | None = None

    for i, row in enumerate(sentences):
        if not isinstance(row, dict):
            err = "bad_sentence_row"
            break
        sid = str(row.get("id") or row.get("sentence_id") or i)
        text = _plain(str(row.get("text") or row.get("text_en") or ""))
        if not text:
            continue
        try:
            chunks = plan_sentence_chunks(text, generate=generate)
        except ValueError as exc:
            err = str(exc)[:120]
            break
        built[sid] = {"text": text, "chunks": chunks}

    plan["sentences"] = built
    if err:
        plan["status"] = "error"
        plan["error"] = err
    elif not built:
        plan["status"] = "error"
        plan["error"] = "no_sentences"
    else:
        plan["status"] = "ok"
        plan["error"] = None
    save_chunk_plan(uid=uid, cache_id=cache_id, plan=plan)
    return plan


def needs_chunk_backfill(plan: dict[str, Any] | None) -> bool:
    if not plan or not isinstance(plan, dict):
        return True
    st = plan.get("status")
    if st in ("empty", "error", "pending"):
        return True
    if st == "ok" and isinstance(plan.get("sentences"), dict) and plan["sentences"]:
        return False
    return True
