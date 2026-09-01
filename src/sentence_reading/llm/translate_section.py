"""
무엇을: ingest 시 섹션 단위 영→한 (기존 pipeline + 요지 재감수 + 캡션).
왜: 문장 단독 live 번역보다 말투·용어·대기 개선 (design/40).
다음에: 용어집·부분 재번역 API.

흐름 (섹션마다):
  1) 문장별 translate_dispatch(pipeline) — design/46 동시 N
  2) 섹션 EN 묶음 → digest(EN+KO)
  3) digest로 각 text_ko harmonize — design/46 동시 N
  4) 그림 caption도 pipeline (+ body digest 재감수) — 캡션 동시 N

INVARIANT: 점수/채점 없음. 실패는 항목 단위 스킵(경고만).
NOTE: Live Enable / IPS 는 Trading Gate — ASR 밖.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

from sentence_reading.llm import translate as tr
from sentence_reading.llm.env import (
    gemini_api_key,
    translate_backend,
    translate_gemini_post,
)
from sentence_reading.llm import translate_google as tg
from sentence_reading.models import Figure, Sentence

log = logging.getLogger(__name__)

# design/169c — optional job/cache ids for call_fail/slow (set by enrich kwargs).
_EVIDENCE_CTX = threading.local()
_CALL_SLOW_MS = 60_000

# WHY: rich-v* 와 분리 — 번역만 바뀌어도 PDF 재분석 강제하지 않음
TRANSLATE_DOC_VERSION = "doc-v1"

# on_progress(message, fraction 0..1) — job badge용 (design/43)
ProgressCb = Callable[[str, float], None]
# on_item(kind, index, ko, stage) — progressive 세션 패치 (design/45)
ItemCb = Callable[[str, int, str, str], None]

_FINAL_STAGES = frozenset({"polish", "harmonize", "google"})
_DEFAULT_WORKERS = 4
_MAX_WORKERS = 8


def translate_worker_count() -> int:
    """
    동시 Gemini 작업 수 (design/46).
    ASR_TRANSLATE_WORKERS — 없으면 4, 범위 1–8.
    """
    raw = (os.environ.get("ASR_TRANSLATE_WORKERS") or "").strip()
    if not raw:
        return _DEFAULT_WORKERS
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_WORKERS
    return max(1, min(_MAX_WORKERS, n))


_SEC_LABEL_KO: dict[str, str] = {
    "title": "제목",
    "abstract": "초록",
    "introduction": "서론",
    "methods": "방법",
    "experimental": "실험",
    "results": "결과",
    "discussion": "토론",
    "conclusion": "결론",
    "body": "본문",
}


def _sec_label(section: str) -> str:
    return _SEC_LABEL_KO.get(section, section or "본문")


def ko_counts(
    sentences: list[Sentence] | None,
    figures: list[Figure] | None,
) -> tuple[int, int]:
    """Non-empty text_ko / caption_ko counts (design/169c). No text payload."""
    sk = sum(
        1
        for s in (sentences or [])
        if str(getattr(s, "text_ko", "") or "").strip()
    )
    fk = sum(
        1
        for f in (figures or [])
        if str(getattr(f, "caption_ko", "") or "").strip()
    )
    return sk, fk


def should_sample_translate_item(index: int, stage: str) -> bool:
    """Spam guard: first, every 5th, or final harmonize."""
    st = (stage or "").strip().lower()
    if index == 0 or index % 5 == 0:
        return True
    return st == "harmonize"


def _exc_type_snake(exc: BaseException) -> str:
    name = type(exc).__name__
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    s = re.sub(r"[^a-z0-9_]", "", s)
    if not s or not re.match(r"^[a-z]", s):
        return "exc"
    return s[:64]


def _evidence_ids() -> tuple[str, str, str, str]:
    return (
        str(getattr(_EVIDENCE_CTX, "job_id", "") or ""),
        str(getattr(_EVIDENCE_CTX, "cache_id", "") or ""),
        str(getattr(_EVIDENCE_CTX, "owner_uid", "") or ""),
        str(getattr(_EVIDENCE_CTX, "trace_id", "") or ""),
    )


def _bind_evidence_ctx(
    job_id: str,
    cache_id: str,
    owner_uid: str,
    trace_id: str,
    *,
    section: str = "",
) -> None:
    """
    design/169h H0 — copy ids onto this thread's local.
    ThreadPool workers do not inherit the parent threading.local.
    """
    _EVIDENCE_CTX.job_id = str(job_id or "")
    _EVIDENCE_CTX.cache_id = str(cache_id or "")
    _EVIDENCE_CTX.owner_uid = str(owner_uid or "")
    _EVIDENCE_CTX.trace_id = str(trace_id or "")
    if section:
        _EVIDENCE_CTX.section = str(section)[:64]


def _emit_translate_call(
    kind: str,
    *,
    call_kind: str,
    elapsed_ms: int | None = None,
    exc: BaseException | None = None,
    batch_n: int | None = None,
    chunk_i: int | None = None,
    chunk_n: int | None = None,
    section: str = "",
    job_id: str | None = None,
    cache_id: str | None = None,
    owner_uid: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Fire-and-forget design/169c/e call sensors. Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        ctx_job, ctx_cache, ctx_uid, ctx_trace = _evidence_ids()
        job_id = str(job_id if job_id is not None else ctx_job or "")
        cache_id = str(cache_id if cache_id is not None else ctx_cache or "")
        owner_uid = str(owner_uid if owner_uid is not None else ctx_uid or "")
        trace_id = str(trace_id if trace_id is not None else ctx_trace or "")
        details: dict[str, Any] = {
            "call_kind": str(call_kind or "unknown")[:64],
        }
        if elapsed_ms is not None:
            details["elapsed_ms"] = int(elapsed_ms)
        if exc is not None:
            details["exc_type"] = _exc_type_snake(exc)
        if batch_n is not None:
            details["batch_n"] = int(batch_n)
        if chunk_i is not None:
            details["chunk_i"] = int(chunk_i)
        if chunk_n is not None:
            details["chunk_n"] = int(chunk_n)
        sec = str(section or getattr(_EVIDENCE_CTX, "section", "") or "").strip().lower()
        sec = re.sub(r"[^a-z0-9_]", "", sec.replace("-", "_").replace(" ", "_"))[:64]
        if sec and re.match(r"^[a-z]", sec):
            details["section"] = sec
        sev = "error" if kind == "translate_call_fail" else "boundary"
        if kind == "translate_call_start":
            sev = "boundary"
        eb.emit(
            kind,
            severity=sev,
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="translate",
            details=details,
            ok=kind != "translate_call_fail",
            code=kind,
        )
    except Exception:  # noqa: BLE001
        log.warning("translate evidence emit failed kind=%s", kind, exc_info=True)


def _stage_token(raw: str) -> str:
    """Snake token for evidence details (colon stages are stripped by _safe_details)."""
    s = str(raw or "").strip().lower().replace(":", "_").replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)[:64]
    if not s or not re.match(r"^[a-z]", s):
        return "unknown"
    return s


_CALLBACK_SLOW_MS = 200


def _emit_checkpoint(
    checkpoint: str,
    *,
    section: str = "",
    blocked_on: str = "",
    in_n: int | None = None,
    out_n: int | None = None,
    remaining: int | None = None,
    worker_n: int | None = None,
    elapsed_ms: int | None = None,
    ok: bool = True,
    exc: BaseException | None = None,
    index: int | None = None,
    stage: str = "",
    job_id: str | None = None,
    cache_id: str | None = None,
    owner_uid: str | None = None,
    trace_id: str | None = None,
) -> None:
    """design/169h — interior milestone (no paper text). Never raises."""
    try:
        from sentence_reading.llm import evidence_bus as eb

        ctx_job, ctx_cache, ctx_uid, ctx_trace = _evidence_ids()
        details: dict[str, Any] = {
            "checkpoint": _stage_token(checkpoint),
        }
        sec = _stage_token(section or getattr(_EVIDENCE_CTX, "section", "") or "")
        if sec != "unknown":
            details["section"] = sec
        bo = _stage_token(blocked_on) if blocked_on else ""
        if bo and bo != "unknown":
            details["blocked_on"] = bo
        if in_n is not None:
            details["in_n"] = int(in_n)
        if out_n is not None:
            details["out_n"] = int(out_n)
        if remaining is not None:
            details["remaining"] = int(remaining)
        if worker_n is not None:
            details["worker_n"] = int(worker_n)
        if elapsed_ms is not None:
            details["elapsed_ms"] = int(elapsed_ms)
        if exc is not None:
            details["exc_type"] = _exc_type_snake(exc)
        if index is not None:
            details["index"] = int(index)
        st = _stage_token(stage) if stage else ""
        if st and st != "unknown":
            details["item_stage"] = st
        eb.emit(
            "checkpoint",
            severity="boundary",
            trace_id=str(trace_id if trace_id is not None else ctx_trace or ""),
            job_id=str(job_id if job_id is not None else ctx_job or ""),
            cache_id=str(cache_id if cache_id is not None else ctx_cache or ""),
            owner_uid=str(owner_uid if owner_uid is not None else ctx_uid or ""),
            stage="translate",
            details=details,
            ok=bool(ok),
            code="checkpoint",
        )
    except Exception:  # noqa: BLE001
        log.warning("translate checkpoint emit failed", exc_info=True)


def _emit_handoff(
    *,
    from_stage: str,
    to_stage: str,
    section: str = "",
    in_n: int | None = None,
    out_n: int | None = None,
    job_id: str | None = None,
    cache_id: str | None = None,
    owner_uid: str | None = None,
    trace_id: str | None = None,
) -> str:
    """
    design/169g phase 2 — A→B handoff breadcrumb. Returns handoff_id (or "").
    Never raises.
    """
    hid = f"hf_{secrets.token_hex(6)}"
    try:
        from sentence_reading.llm import evidence_bus as eb

        ctx_job, ctx_cache, ctx_uid, ctx_trace = _evidence_ids()
        job_id = str(job_id if job_id is not None else ctx_job or "")
        cache_id = str(cache_id if cache_id is not None else ctx_cache or "")
        owner_uid = str(owner_uid if owner_uid is not None else ctx_uid or "")
        trace_id = str(trace_id if trace_id is not None else ctx_trace or "")
        details: dict[str, Any] = {
            "handoff_id": hid,
            "from_stage": _stage_token(from_stage),
            "to_stage": _stage_token(to_stage),
        }
        sec = _stage_token(section or getattr(_EVIDENCE_CTX, "section", "") or "")
        if sec != "unknown":
            details["section"] = sec
        if in_n is not None:
            details["in_n"] = int(in_n)
        if out_n is not None:
            details["out_n"] = int(out_n)
        eb.emit(
            "handoff",
            severity="boundary",
            trace_id=trace_id,
            job_id=job_id,
            cache_id=cache_id,
            owner_uid=owner_uid,
            stage="translate",
            details=details,
            ok=True,
            code="handoff",
        )
        return hid
    except Exception:  # noqa: BLE001
        log.warning("translate handoff emit failed", exc_info=True)
        return ""


def _google_batch_timed(
    texts: list[str],
    *,
    section: str = "",
) -> list[str | None]:
    """
    design/169e — wrap Google bulk translate with call_start/slow/fail.
    WHY: section batch can block for many minutes with zero item_done ticks.
    """
    pending_n = sum(1 for t in texts if str(t or "").strip())
    prev_sec = getattr(_EVIDENCE_CTX, "section", "")
    _EVIDENCE_CTX.section = str(section or "")[:64]
    _emit_translate_call(
        "translate_call_start",
        call_kind="google_batch",
        batch_n=pending_n,
        section=section,
    )
    t0 = time.monotonic()
    try:
        out = tg.translate_batch_en_to_ko(texts)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _emit_translate_call(
            "translate_call_fail",
            call_kind="google_batch",
            elapsed_ms=elapsed_ms,
            exc=exc,
            batch_n=pending_n,
            section=section,
        )
        _EVIDENCE_CTX.section = prev_sec
        raise
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if elapsed_ms >= _CALL_SLOW_MS:
        _emit_translate_call(
            "translate_call_slow",
            call_kind="google_batch",
            elapsed_ms=elapsed_ms,
            batch_n=pending_n,
            section=section,
        )
    _emit_translate_call(
        "translate_call_done",
        call_kind="google_batch",
        elapsed_ms=elapsed_ms,
        batch_n=pending_n,
        section=section,
    )
    _EVIDENCE_CTX.section = prev_sec
    return out


def _gemini_timed(call_kind: str, system: str, user: str) -> str | None:
    """Wrap Gemini generate with 169c/169g start/fail/slow/done evidence."""
    _emit_translate_call("translate_call_start", call_kind=call_kind)
    t0 = time.monotonic()
    try:
        out = tr._gemini_generate(system, user)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _emit_translate_call(
            "translate_call_fail",
            call_kind=call_kind,
            elapsed_ms=elapsed_ms,
            exc=exc,
        )
        raise
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if elapsed_ms >= _CALL_SLOW_MS:
        _emit_translate_call(
            "translate_call_slow",
            call_kind=call_kind,
            elapsed_ms=elapsed_ms,
        )
    _emit_translate_call(
        "translate_call_done",
        call_kind=call_kind,
        elapsed_ms=elapsed_ms,
    )
    return out


def needs_translate_backfill(
    sentences: list[Sentence],
    figures: list[Figure],
    digests: dict | None = None,
) -> bool:
    """
    보관본에 ingest 번역이 없거나 단계 미완이면 True (design/42·45).
    """
    plain_sents = [
        s for s in (sentences or []) if _plain(getattr(s, "text", "") or "")
    ]
    for s in plain_sents:
        ko = (getattr(s, "text_ko", None) or "").strip()
        stage = (getattr(s, "text_ko_stage", None) or "").strip().lower()
        if ko and tr.is_dirty_ko_output(ko):
            return True
        if ko and stage and stage not in _FINAL_STAGES:
            return True
        if not ko:
            return True
    for f in figures or []:
        cko = (getattr(f, "caption_ko", None) or "").strip()
        stage = (getattr(f, "caption_ko_stage", None) or "").strip().lower()
        if cko and tr.is_dirty_ko_output(cko):
            return True
        if cko and stage and stage not in _FINAL_STAGES:
            return True
        if _plain(getattr(f, "caption", "") or "") and not cko:
            return True

    if digests and any(
        isinstance(v, dict)
        and (str(v.get("en") or "").strip() or str(v.get("ko") or "").strip())
        for v in digests.values()
    ):
        n = len(plain_sents)
        if n == 0:
            return False
        final_ok = sum(
            1
            for s in plain_sents
            if (getattr(s, "text_ko", None) or "").strip()
            and (getattr(s, "text_ko_stage", None) or "").strip().lower()
            in _FINAL_STAGES
        )
        if final_ok / n >= 0.05:
            return False
        return True

    n = len(plain_sents)
    if n == 0:
        return False
    filled = sum(1 for s in plain_sents if (getattr(s, "text_ko", None) or "").strip())
    if filled / n >= 0.05:
        return False
    if any((getattr(f, "caption_ko", None) or "").strip() for f in (figures or [])):
        return False
    return True


_DIGEST_SYSTEM = """You summarize one academic paper section for a Korean researcher.
Return exactly two blocks:
EN: <2-4 English sentences: core claim and key terms>
KO: <2-4 Korean sentences: same content, natural academic Korean>
No other preamble. Keep formulas/symbols accurate.
"""

_HARMONIZE_SYSTEM = """You revise a Korean translation of one academic English sentence.
You are given the section's theme summary (EN+KO) and must make terminology and tone consistent with that theme.
Output Korean only — no quotes, no English echo, no preamble.
Do not invent facts; keep formulas and numbers.
"""


def _plain(text: str) -> str:
    """HTML/공백 정리 — 번역·digest 입력용. 빈 문자열이면 skip."""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _section_key(section: str | None) -> str:
    """빈/None section → body. UI 되새김질 키와 맞춤."""
    s = (section or "body").strip().lower() or "body"
    return s


def _parse_digest(raw: str) -> dict[str, str]:
    """
    EN:/KO: 블록 파싱.
    WHY: 모델이 형식을 살짝 깨도 관대하게 — 마커 없으면 전체를 KO로.
    """
    en, ko = "", ""
    if not raw:
        return {"en": "", "ko": ""}
    m_en = re.search(
        r"(?is)\bEN\s*:\s*(.*?)(?=\bKO\s*:|$)",
        raw,
    )
    m_ko = re.search(r"(?is)\bKO\s*:\s*(.*?)$", raw)
    if m_en:
        en = m_en.group(1).strip()
    if m_ko:
        ko = m_ko.group(1).strip()
    if not en and not ko:
        ko = raw.strip()
    return {"en": en, "ko": ko}


def _pipeline_staged(
    text: str,
    *,
    on_stage: Callable[[str, str], None] | None = None,
) -> str | None:
    """
    google bulk 1건 또는 draft → sense → polish (design/45 · design/153).
    캐시 hit 시 polish/google 한 번에 보고 종료.
    """
    plain = _plain(text)
    if not plain:
        return None
    if len(plain) > tr._MAX_CHARS:
        plain = plain[: tr._MAX_CHARS]

    if translate_backend() == "google" and tg.google_translate_available():
        t0 = time.monotonic()
        try:
            ko = tg.translate_one_en_to_ko(plain)
        except Exception as exc:  # noqa: BLE001
            _emit_translate_call("translate_call_fail", call_kind="google", exc=exc)
            raise
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if elapsed_ms >= _CALL_SLOW_MS:
            _emit_translate_call(
                "translate_call_slow",
                call_kind="google",
                elapsed_ms=elapsed_ms,
            )
        if ko:
            if on_stage:
                try:
                    on_stage(ko, "google")
                except Exception as exc:  # noqa: BLE001
                    log.warning("pipeline on_stage google failed: %s", exc)
            return ko

    key = tr._cache_key(f"pipeline:{tr._PIPELINE_VERSION}:", plain)
    hit = tr._cache_get(key)
    if hit is not None:
        if on_stage:
            try:
                on_stage(hit, "polish")
            except Exception as exc:  # noqa: BLE001
                log.warning("pipeline on_stage failed: %s", exc)
        return hit

    if not gemini_api_key():
        return None

    stages_done: list[str] = []
    draft = _gemini_timed("draft", tr._SYSTEM_DRAFT, f"Translate to Korean:\n\n{plain}")
    if not draft:
        return None
    stages_done.append("draft")
    current = draft
    if on_stage:
        try:
            on_stage(current, "draft")
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline on_stage draft failed: %s", exc)

    try:
        sense = _gemini_timed(
            "sense",
            tr._SYSTEM_SENSE,
            f"English source:\n{plain}\n\nKorean draft:\n{current}\n\nRevise for terminology.",
        )
        if sense:
            current = sense
            stages_done.append("sense")
            if on_stage:
                try:
                    on_stage(current, "sense")
                except Exception as exc:  # noqa: BLE001
                    log.warning("pipeline on_stage sense failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("translate sense failed: %s", exc)

    try:
        polish = _gemini_timed(
            "polish",
            tr._SYSTEM_POLISH,
            f"English source:\n{plain}\n\nKorean draft:\n{current}\n\nPolish for readability.",
        )
        if polish:
            current = polish
            stages_done.append("polish")
            if on_stage:
                try:
                    on_stage(current, "polish")
                except Exception as exc:  # noqa: BLE001
                    log.warning("pipeline on_stage polish failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("translate polish failed: %s", exc)

    if stages_done == ["draft", "sense", "polish"]:
        tr._cache_put(key, current)
    return current or None


def _pipeline_one(text: str) -> str | None:
    """기존 design/36 pipeline 1회. 실패·빈 입력 → None (호출측이 skip)."""
    return _pipeline_staged(text)


def _make_digest(section: str, english_lines: list[str]) -> dict[str, str]:
    """섹션 핵심 요지 (EN+KO). 키/문장 없으면 빈 digest."""
    if not gemini_api_key() or not english_lines:
        return {"en": "", "ko": ""}
    # WHY: 토큰 폭주 방지 — 섹션당 최대 40문장
    joined = "\n".join(f"- {t}" for t in english_lines[:40])
    user = (
        f"Section id: {section}\n"
        f"Sentences:\n{joined}\n\n"
        "Write EN: and KO: theme summaries."
    )
    try:
        raw = _gemini_timed("digest", _DIGEST_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("digest failed %s: %s", section, exc)
        return {"en": "", "ko": ""}
    return _parse_digest(raw or "")


def _harmonize(en: str, ko: str, digest: dict[str, str]) -> tuple[str, bool]:
    """
    요지 기준으로 draft KO 재감수.
    Returns (ko, accepted) — dirty 출력은 draft 유지, accepted=False.
    """
    if not gemini_api_key() or not ko:
        return ko, False
    theme = (
        f"EN theme: {digest.get('en') or '(none)'}\n"
        f"KO theme: {digest.get('ko') or '(none)'}"
    )
    user = (
        f"{theme}\n\nEnglish source:\n{en}\n\nKorean draft:\n{ko}\n\n"
        "Revise Korean for theme consistency."
    )
    try:
        raw = _gemini_timed("harmonize", _HARMONIZE_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("harmonize failed: %s", exc)
        return ko, False
    out = tr.sanitize_ko_output(raw or "")
    if tr.is_dirty_ko_output(out):
        log.warning("harmonize rejected dirty output")
        return ko, False
    final = out.strip() or ko
    if final == ko:
        return ko, False
    return final, True


def _estimate_progress_units(
    sentences: list[Sentence],
    figures: list[Figure],
    by_sec: dict[str, list[int]],
) -> int:
    """
    job percent 분모 — 실제 LLM 호출과 1:1은 아님.
    WHY: pipeline(문장) + digest(섹션) + harmonize(문장) + caption.
    """
    units = 0
    for idxs in by_sec.values():
        n_plain = sum(1 for i in idxs if _plain(sentences[i].text))
        if n_plain == 0:
            continue
        units += n_plain  # translate
        units += 1  # digest
        units += n_plain  # harmonize (요지 없으면 스킵해도 상한)
    n_cap = sum(1 for f in figures if _plain(f.caption))
    units += n_cap
    return max(units, 1)


def enrich_session_translations(
    sentences: list[Sentence],
    figures: list[Figure],
    *,
    on_progress: ProgressCb | None = None,
    on_item: ItemCb | None = None,
    workers: int | None = None,
    job_id: str = "",
    cache_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
) -> tuple[list[Sentence], list[Figure], dict[str, dict[str, str]], list[str]]:
    """
    섹션별 pipeline → digest → harmonize.
    on_progress: design/43 badge.
    on_item: design/45 — ("sentence"|"figure", index, ko, stage) 즉시 패치.
    workers: design/46 — 동시 작업 수 (None이면 env/기본).
    job_id/cache_id/owner_uid/trace_id: design/169c/g call evidence correlation.
    # INVARIANT: score 없음. 실패 시 해당 항목만 스킵.
    """
    _EVIDENCE_CTX.job_id = str(job_id or "")
    _EVIDENCE_CTX.cache_id = str(cache_id or "")
    _EVIDENCE_CTX.owner_uid = str(owner_uid or "")
    _EVIDENCE_CTX.trace_id = str(trace_id or "")
    try:
        return _enrich_session_translations_body(
            sentences,
            figures,
            on_progress=on_progress,
            on_item=on_item,
            workers=workers,
        )
    finally:
        _EVIDENCE_CTX.job_id = ""
        _EVIDENCE_CTX.cache_id = ""
        _EVIDENCE_CTX.owner_uid = ""
        _EVIDENCE_CTX.trace_id = ""


def _enrich_session_translations_body(
    sentences: list[Sentence],
    figures: list[Figure],
    *,
    on_progress: ProgressCb | None = None,
    on_item: ItemCb | None = None,
    workers: int | None = None,
) -> tuple[list[Sentence], list[Figure], dict[str, dict[str, str]], list[str]]:
    """Inner enrich (evidence ctx already set)."""
    warnings: list[str] = []
    use_google = translate_backend() == "google"
    gemini_post = (
        translate_backend() == "gemini" or translate_gemini_post()
    ) and bool(gemini_api_key())

    # design/169h H0 — snapshot for ThreadPool workers (threading.local not inherited)
    ev_job, ev_cache, ev_uid, ev_trace = _evidence_ids()

    if use_google:
        if not tg.google_translate_available() and not gemini_api_key():
            warnings.append("translate_skipped_no_backend")
            return sentences, figures, {}, warnings
        if translate_gemini_post() and not gemini_api_key():
            warnings.append("translate_post_skipped_no_gemini")
    elif not gemini_api_key():
        warnings.append("translate_skipped_no_gemini")
        return sentences, figures, {}, warnings

    n_workers = (
        max(1, min(_MAX_WORKERS, int(workers)))
        if workers is not None
        else translate_worker_count()
    )

    by_sec: dict[str, list[int]] = {}
    for i, s in enumerate(sentences):
        by_sec.setdefault(_section_key(s.section), []).append(i)

    total = _estimate_progress_units(sentences, figures, by_sec)
    done = 0
    lock = threading.Lock()

    def _tick(message: str) -> None:
        nonlocal done
        with lock:
            done = min(done + 1, total)
            frac = done / total
        if not on_progress:
            return
        t0 = time.monotonic()
        try:
            on_progress(message, frac)
        except Exception as exc:  # noqa: BLE001
            log.warning("translate on_progress failed: %s", exc)
            _emit_checkpoint(
                "on_progress_exit",
                blocked_on="on_progress_callback",
                ok=False,
                exc=exc,
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )
            return
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if elapsed_ms >= _CALLBACK_SLOW_MS:
            _emit_checkpoint(
                "on_progress_exit",
                blocked_on="on_progress_callback",
                elapsed_ms=elapsed_ms,
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )

    def _emit(kind: str, index: int, ko: str, stage: str) -> None:
        # design/169j — do not hold ko_map lock across on_item (cold I/O must not
        # serialize ThreadPool workers; on_item itself must stay hot-only).
        if not on_item or not ko:
            return
        t0 = time.monotonic()
        try:
            on_item(kind, index, ko, stage)
        except Exception as exc:  # noqa: BLE001
            log.warning("translate on_item failed: %s", exc)
            _emit_checkpoint(
                "on_item_exit",
                blocked_on="on_item_callback",
                ok=False,
                exc=exc,
                index=index,
                stage=stage,
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )
            return
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        # design/169h H2 — slow or first/every-5th sample
        if elapsed_ms >= _CALLBACK_SLOW_MS or should_sample_translate_item(index, stage):
            if elapsed_ms >= _CALLBACK_SLOW_MS or index == 0:
                _emit_checkpoint(
                    "on_item_exit",
                    blocked_on="on_item_callback",
                    elapsed_ms=elapsed_ms,
                    index=index,
                    stage=stage,
                    job_id=ev_job,
                    cache_id=ev_cache,
                    owner_uid=ev_uid,
                    trace_id=ev_trace,
                )

    ko_map: dict[int, str] = {}
    stage_map: dict[int, str] = {}
    digests: dict[str, dict[str, str]] = {}

    def _run_sentence_pipeline(i: int) -> tuple[int, str | None, str]:
        _bind_evidence_ctx(ev_job, ev_cache, ev_uid, ev_trace)
        last_stage = ""

        def _on_stage(ko: str, stage: str) -> None:
            nonlocal last_stage
            last_stage = stage
            with lock:
                ko_map[i] = ko
                stage_map[i] = stage
            _emit("sentence", i, ko, stage)

        ko = _pipeline_staged(
            _plain(sentences[i].text),
            on_stage=_on_stage,
        )
        if ko and i not in ko_map:
            with lock:
                ko_map[i] = ko
                stage_map[i] = last_stage or "polish"
            _emit("sentence", i, ko, last_stage or "polish")
        return i, ko, last_stage or stage_map.get(i, "")

    def _run_harmonize(i: int, digest: dict[str, str], *, section: str = "") -> int:
        _bind_evidence_ctx(ev_job, ev_cache, ev_uid, ev_trace, section=section)
        with lock:
            draft = ko_map.get(i) or ""
            prev_stage = stage_map.get(i, "")
        if not draft:
            return i
        ko, accepted = _harmonize(_plain(sentences[i].text), draft, digest)
        with lock:
            ko_map[i] = ko
            if accepted:
                stage_map[i] = "harmonize"
                _emit("sentence", i, ko, "harmonize")
            elif prev_stage:
                stage_map[i] = prev_stage
        return i

    _sec_queue = [
        (s, idxs)
        for s, idxs in by_sec.items()
        if any(_plain(sentences[i].text) for i in idxs)
    ]
    _use_google_path = bool(use_google and tg.google_translate_available())
    queue_len = len(_sec_queue)

    for _si, (sec, idxs) in enumerate(_sec_queue):
        label = _sec_label(sec)
        plain_idxs = [i for i in idxs if _plain(sentences[i].text)]
        n_plain = len(plain_idxs)
        if n_plain == 0:
            continue

        _bind_evidence_ctx(ev_job, ev_cache, ev_uid, ev_trace, section=sec)
        _emit_checkpoint(
            "section_enter",
            section=sec,
            blocked_on="section_enter",
            in_n=n_plain,
            out_n=_si,
            remaining=max(0, queue_len - _si - 1),
            worker_n=n_workers,
            job_id=ev_job,
            cache_id=ev_cache,
            owner_uid=ev_uid,
            trace_id=ev_trace,
        )

        finished = 0
        if _use_google_path:
            eng_for_batch = [_plain(sentences[i].text) for i in plain_idxs]
            ko_batch = _google_batch_timed(eng_for_batch, section=sec)
            for j, i in enumerate(plain_idxs):
                ko = ko_batch[j] if j < len(ko_batch) else None
                if ko:
                    with lock:
                        ko_map[i] = ko
                        stage_map[i] = "google"
                    _emit("sentence", i, ko, "google")
                finished += 1
                _tick(f"{label} 번역 {finished}/{n_plain}")
            ko_after = sum(1 for i in plain_idxs if (ko_map.get(i) or "").strip())
            if gemini_post:
                _emit_handoff(
                    from_stage="google_batch",
                    to_stage="gemini_digest",
                    section=sec,
                    in_n=n_plain,
                    out_n=ko_after,
                    job_id=ev_job,
                    cache_id=ev_cache,
                    owner_uid=ev_uid,
                    trace_id=ev_trace,
                )
        else:
            with ThreadPoolExecutor(max_workers=min(n_workers, n_plain)) as pool:
                futs = {pool.submit(_run_sentence_pipeline, i): i for i in plain_idxs}
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("parallel pipeline failed: %s", exc)
                        _emit_checkpoint(
                            "pool_task_fail",
                            section=sec,
                            ok=False,
                            exc=exc,
                            job_id=ev_job,
                            cache_id=ev_cache,
                            owner_uid=ev_uid,
                            trace_id=ev_trace,
                        )
                    finished += 1
                    _tick(f"{label} 번역 {finished}/{n_plain}")
            if gemini_post:
                _emit_handoff(
                    from_stage="gemini_pipeline",
                    to_stage="gemini_digest",
                    section=sec,
                    in_n=n_plain,
                    out_n=sum(1 for i in plain_idxs if (ko_map.get(i) or "").strip()),
                    job_id=ev_job,
                    cache_id=ev_cache,
                    owner_uid=ev_uid,
                    trace_id=ev_trace,
                )

        eng_lines = [_plain(sentences[i].text) for i in plain_idxs]
        if gemini_post:
            _tick(f"{label} 요지 정리")
            digest = _make_digest(sec, eng_lines)
            digests[sec] = digest

            if digest.get("en") or digest.get("ko"):
                harm_idxs = [i for i in plain_idxs if i in ko_map]
                n_harm = len(harm_idxs)
                if n_harm:
                    _emit_handoff(
                        from_stage="gemini_digest",
                        to_stage="gemini_harmonize",
                        section=sec,
                        in_n=n_harm,
                        job_id=ev_job,
                        cache_id=ev_cache,
                        owner_uid=ev_uid,
                        trace_id=ev_trace,
                    )
                    finished_h = 0
                    harm_workers = min(n_workers, n_harm)
                    _emit_checkpoint(
                        "harmonize_pool_start",
                        section=sec,
                        blocked_on="threadpool_join",
                        in_n=n_harm,
                        worker_n=harm_workers,
                        job_id=ev_job,
                        cache_id=ev_cache,
                        owner_uid=ev_uid,
                        trace_id=ev_trace,
                    )
                    with ThreadPoolExecutor(max_workers=harm_workers) as pool:
                        futs = {
                            pool.submit(
                                _run_harmonize, i, digest, section=sec
                            ): i
                            for i in harm_idxs
                        }
                        for fut in as_completed(futs):
                            try:
                                fut.result()
                            except Exception as exc:  # noqa: BLE001
                                log.warning("parallel harmonize failed: %s", exc)
                                _emit_checkpoint(
                                    "pool_task_fail",
                                    section=sec,
                                    ok=False,
                                    exc=exc,
                                    job_id=ev_job,
                                    cache_id=ev_cache,
                                    owner_uid=ev_uid,
                                    trace_id=ev_trace,
                                )
                            finished_h += 1
                            rem = n_harm - finished_h
                            if (
                                finished_h == 1
                                or finished_h % 5 == 0
                                or rem == 0
                            ):
                                _emit_checkpoint(
                                    "harmonize_pool_tick",
                                    section=sec,
                                    blocked_on="threadpool_join",
                                    in_n=n_harm,
                                    out_n=finished_h,
                                    remaining=rem,
                                    worker_n=harm_workers,
                                    job_id=ev_job,
                                    cache_id=ev_cache,
                                    owner_uid=ev_uid,
                                    trace_id=ev_trace,
                                )
                            _tick(f"{label} 재감수 {finished_h}/{n_harm}")
                    _emit_checkpoint(
                        "harmonize_pool_end",
                        section=sec,
                        in_n=n_harm,
                        out_n=finished_h,
                        worker_n=harm_workers,
                        job_id=ev_job,
                        cache_id=ev_cache,
                        owner_uid=ev_uid,
                        trace_id=ev_trace,
                    )
                    _emit_handoff(
                        from_stage="gemini_harmonize",
                        to_stage="section_done",
                        section=sec,
                        in_n=n_harm,
                        out_n=finished_h,
                        job_id=ev_job,
                        cache_id=ev_cache,
                        owner_uid=ev_uid,
                        trace_id=ev_trace,
                    )
                else:
                    _emit_handoff(
                        from_stage="gemini_digest",
                        to_stage="section_done",
                        section=sec,
                        in_n=n_plain,
                        out_n=0,
                        job_id=ev_job,
                        cache_id=ev_cache,
                        owner_uid=ev_uid,
                        trace_id=ev_trace,
                    )
            else:
                _emit_handoff(
                    from_stage="gemini_digest",
                    to_stage="section_done",
                    section=sec,
                    in_n=n_plain,
                    out_n=0,
                    job_id=ev_job,
                    cache_id=ev_cache,
                    owner_uid=ev_uid,
                    trace_id=ev_trace,
                )
        else:
            digests[sec] = {"en": "", "ko": ""}
            _emit_handoff(
                from_stage="google_batch" if _use_google_path else "gemini_pipeline",
                to_stage="section_done",
                section=sec,
                in_n=n_plain,
                out_n=sum(1 for i in plain_idxs if (ko_map.get(i) or "").strip()),
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )

        _emit_checkpoint(
            "section_exit",
            section=sec,
            in_n=n_plain,
            job_id=ev_job,
            cache_id=ev_cache,
            owner_uid=ev_uid,
            trace_id=ev_trace,
        )
        if _si + 1 < len(_sec_queue):
            nxt_sec = _sec_queue[_si + 1][0]
            _emit_handoff(
                from_stage="section_done",
                to_stage="google_batch" if _use_google_path else "gemini_pipeline",
                section=nxt_sec,
                in_n=n_plain,
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )
            _emit_checkpoint(
                "next_section_armed",
                section=nxt_sec,
                blocked_on="next_section_enter",
                in_n=n_plain,
                job_id=ev_job,
                cache_id=ev_cache,
                owner_uid=ev_uid,
                trace_id=ev_trace,
            )

    new_sentences = [
        replace(
            s,
            text_ko=ko_map.get(i) or getattr(s, "text_ko", "") or "",
            text_ko_stage=stage_map.get(i)
            or getattr(s, "text_ko_stage", "")
            or "",
        )
        for i, s in enumerate(sentences)
    ]

    body_digest = digests.get("body") or next(
        iter(digests.values()), {"en": "", "ko": ""}
    )

    cap_jobs: list[tuple[int, Figure, str]] = []
    for fi, fig in enumerate(figures):
        cap = _plain(fig.caption)
        if cap:
            cap_jobs.append((fi, fig, cap))

    cap_results: dict[int, tuple[str, str]] = {}
    n_cap = len(cap_jobs)

    def _run_caption(job: tuple[int, Figure, str]) -> tuple[int, str, str]:
        fi, _fig, cap = job
        _bind_evidence_ctx(ev_job, ev_cache, ev_uid, ev_trace, section="caption")
        cap_ko = ""
        cap_stage = ""

        def _on_cap(ko: str, stage: str) -> None:
            nonlocal cap_ko, cap_stage
            cap_ko = ko
            cap_stage = stage
            _emit("figure", fi, ko, stage)

        cap_ko = _pipeline_staged(cap, on_stage=_on_cap) or ""
        if cap_ko and (body_digest.get("en") or body_digest.get("ko")):
            harm_ko, accepted = _harmonize(cap, cap_ko, body_digest)
            cap_ko = harm_ko
            if accepted:
                cap_stage = "harmonize"
                _emit("figure", fi, cap_ko, "harmonize")
        elif cap_ko and not cap_stage:
            cap_stage = "polish"
        return fi, cap_ko, cap_stage

    if cap_jobs:
        _emit_handoff(
            from_stage="section_done" if _sec_queue else "translate_phase",
            to_stage="google_batch" if _use_google_path else "gemini_pipeline",
            section="caption",
            in_n=n_cap,
            job_id=ev_job,
            cache_id=ev_cache,
            owner_uid=ev_uid,
            trace_id=ev_trace,
        )
        finished_c = 0
        if use_google and tg.google_translate_available():
            cap_texts = [cap for _, _, cap in cap_jobs]
            ko_batch = _google_batch_timed(cap_texts, section="caption")
            for j, (fi, _fig, cap) in enumerate(cap_jobs):
                cap_ko = (ko_batch[j] if j < len(ko_batch) else None) or ""
                cap_stage = "google" if cap_ko else ""
                if cap_ko and gemini_post and (
                    body_digest.get("en") or body_digest.get("ko")
                ):
                    harm_ko, accepted = _harmonize(cap, cap_ko, body_digest)
                    cap_ko = harm_ko
                    if accepted:
                        cap_stage = "harmonize"
                if cap_ko:
                    _emit("figure", fi, cap_ko, cap_stage or "google")
                cap_results[fi] = (cap_ko, cap_stage)
                finished_c += 1
                _tick(f"캡션 {finished_c}/{n_cap}")
        else:
            with ThreadPoolExecutor(max_workers=min(n_workers, n_cap)) as pool:
                futs = {pool.submit(_run_caption, j): j[0] for j in cap_jobs}
                for fut in as_completed(futs):
                    try:
                        fi, cap_ko, cap_stage = fut.result()
                        cap_results[fi] = (cap_ko, cap_stage)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("parallel caption failed: %s", exc)
                    finished_c += 1
                    _tick(f"캡션 {finished_c}/{n_cap}")

    new_figures: list[Figure] = []
    for fi, fig in enumerate(figures):
        cap_ko, cap_stage = cap_results.get(fi, ("", ""))
        new_figures.append(
            replace(
                fig,
                caption_ko=cap_ko or getattr(fig, "caption_ko", "") or "",
                caption_ko_stage=cap_stage
                or getattr(fig, "caption_ko_stage", "")
                or "",
            )
        )

    if not any(s.text_ko for s in new_sentences) and not any(
        f.caption_ko for f in new_figures
    ):
        warnings.append("translate_empty")

    if on_progress and done < total:
        try:
            on_progress("번역 마무리", 1.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("translate on_progress final failed: %s", exc)

    return new_sentences, new_figures, digests, warnings


def digest_public(digests: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """API/캐시용 — 이상한 값도 str로 정규화."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(digests, dict):
        return out
    for k, v in digests.items():
        if not isinstance(v, dict):
            continue
        out[str(k)] = {
            "en": str(v.get("en") or ""),
            "ko": str(v.get("ko") or ""),
        }
    return out