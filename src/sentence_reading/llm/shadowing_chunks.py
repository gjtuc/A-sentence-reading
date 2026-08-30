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
# WHY: Cloud Run --timeout 300; leave headroom so we return JSON before gateway 504.
_DEFAULT_BUDGET_S = 90.0
_MIN_BUDGET_S = 15.0
_MAX_BUDGET_S = 240.0


def chunk_build_budget_seconds() -> float:
    """Per-request wall time for Gemini slice (design/113)."""
    import os

    raw = (os.environ.get("ASR_SHADOWING_CHUNK_BUDGET_S") or "").strip()
    if not raw:
        return _DEFAULT_BUDGET_S
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_BUDGET_S
    if val < _MIN_BUDGET_S or val > _MAX_BUDGET_S:
        return _DEFAULT_BUDGET_S
    return val

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


def _fallback_word_chunks(full: str) -> list[str]:
    """Deterministic growing chunks when Gemini output cannot be parsed (design/119+).

    WHY: one bad model response must not block the whole paper (120 sentences).
    """
    words = full.split()
    if len(words) <= 1:
        return [full]
    out: list[str] = []
    step = max(1, len(words) // 4)
    for end in range(step, len(words), step):
        out.append(" ".join(words[:end]))
    if not out or out[-1] != full:
        out.append(full)
    prev = ""
    fixed: list[str] = []
    for step_text in out:
        if step_text == prev:
            continue
        fixed.append(step_text)
        prev = step_text
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
    for attempt in range(3):
        try:
            raw = gen(_SYSTEM, f"Sentence:\n{full}")
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            # WHY: google.genai / network errors must not become raw HTTP 500 (design/119).
            # EDGE: log type only — never API key or prompt body.
            log.warning("shadowing chunk gemini failed: %s", type(exc).__name__)
            raise ValueError("gemini_unavailable") from exc
        if not raw:
            raise ValueError("gemini_unavailable")
        chunks = _parse_chunks_json(raw, full)
        if chunks:
            return chunks
        log.warning(
            "shadowing chunk parse failed (attempt %s/3)",
            attempt + 1,
        )
    log.warning(
        "shadowing chunk using word fallback after parse failures (len=%s)",
        len(full),
    )
    return _fallback_word_chunks(full)

def build_chunk_plan(
    *,
    uid: str,
    cache_id: str,
    sentences: list[dict[str, Any]],
    generate: Callable[[str, str], str | None] | None = None,
    budget_s: float | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """
    Build plan for a paper in time-budgeted slices (design/113).

    WHY: full-paper sync Gemini exceeded Cloud Run → HTTP 504 with no JSON.
    EDGE: budget hit → status=pending + partial sentences saved (not ok, not silent).
    Hard Gemini/parse failure → status=error (UI may retry; partial kept for resume).
    """
    import time

    if not shadowing_practice_enabled():
        raise PermissionError("shadowing_disabled")
    if not sanitize_uid(uid) or not safe_cache_id(cache_id):
        raise ValueError("invalid_id")
    if not isinstance(sentences, list) or len(sentences) > _MAX_SENTENCES:
        raise ValueError("bad_sentences")

    if budget_s is None:
        limit = float(chunk_build_budget_seconds())
    else:
        # Explicit override (tests / callers); still cap absurd highs.
        limit = float(budget_s)
        if limit < 0.01:
            limit = 0.01
        if limit > _MAX_BUDGET_S:
            limit = _MAX_BUDGET_S

    # Resume: keep already-built sentence chunks (cost + consistency).
    built: dict[str, Any] = {}
    if resume:
        prev = load_chunk_plan(uid=uid, cache_id=cache_id)
        prev_sents = prev.get("sentences") if isinstance(prev, dict) else None
        if isinstance(prev_sents, dict):
            for sid, row in prev_sents.items():
                if not isinstance(row, dict):
                    continue
                chunks = row.get("chunks")
                text = _plain(str(row.get("text") or ""))
                if isinstance(chunks, list) and chunks and text:
                    built[str(sid)] = {"text": text, "chunks": list(chunks)}

    plan = empty_plan(cache_id)
    plan["status"] = "pending"
    plan["error"] = None
    err: str | None = None
    started = time.monotonic()
    new_this_slice = 0
    total_work = 0
    for row in sentences:
        if not isinstance(row, dict):
            continue
        text = _plain(str(row.get("text") or row.get("text_en") or ""))
        if text:
            total_work += 1

    for i, row in enumerate(sentences):
        if not isinstance(row, dict):
            err = "bad_sentence_row"
            break
        sid = str(row.get("id") or row.get("sentence_id") or i)
        text = _plain(str(row.get("text") or row.get("text_en") or ""))
        if not text:
            continue
        # Already planned on a prior slice — skip Gemini.
        if sid in built and isinstance(built[sid].get("chunks"), list):
            continue
        elapsed = time.monotonic() - started
        # WHY: stop before gateway kill; leave ~few seconds for save+JSON.
        if elapsed >= limit and new_this_slice > 0:
            break
        if elapsed >= limit and new_this_slice == 0:
            # EDGE: first sentence alone exceeded budget — still try one, then pending.
            pass
        try:
            chunks = plan_sentence_chunks(text, generate=generate)
        except ValueError as exc:
            err = str(exc)[:120]
            break
        built[sid] = {"text": text, "chunks": chunks}
        new_this_slice += 1
        # Persist mid-slice so reclaim/retry after crash keeps progress.
        if new_this_slice % 5 == 0:
            plan["sentences"] = built
            plan["status"] = "pending"
            plan["progress"] = {
                "done": len(built),
                "total": max(total_work, len(built)),
            }
            try:
                save_chunk_plan(uid=uid, cache_id=cache_id, plan=plan)
            except Exception:  # noqa: BLE001
                pass
        if time.monotonic() - started >= limit:
            break

    plan["sentences"] = built
    plan["progress"] = {
        "done": len(built),
        "total": max(total_work, len(built)),
    }
    if err:
        plan["status"] = "error"
        plan["error"] = err
    elif not built and total_work == 0:
        plan["status"] = "error"
        plan["error"] = "no_sentences"
    elif total_work > 0 and len(built) >= total_work:
        plan["status"] = "ok"
        plan["error"] = None
    else:
        # Incomplete slice — honest pending (client continues).
        plan["status"] = "pending"
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
