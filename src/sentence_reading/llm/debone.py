"""
무엇을: PDF raw 텍스트 → Gemini로 ‘가시 제거’ → Title/Abstract/Body 문장.
왜: 단순 분할은 저자·인용·각주 번호를 본문으로 남긴다.
다음에: 스트리밍 진행률, 캐시, 모델 선택 UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sentence_reading.llm.env import gemini_api_key, gemini_model
from sentence_reading.models import Sentence

_CHUNK_CHARS = 5000
_MAX_CHUNK_RETRIES = 3
# WHY: UI에 Title / Abstract / Introduction / Results … 표시 (docs/design/12)
_SECTION_ORDER = {
    "title": 0,
    "abstract": 1,
    "introduction": 2,
    "methods": 3,
    "experimental": 3,
    "results": 4,
    "discussion": 5,
    "conclusion": 6,
    "body": 7,
}

_SECTION_ALIASES = {
    "intro": "introduction",
    "introduction": "introduction",
    "method": "methods",
    "methods": "methods",
    "experimental": "experimental",
    "experiment": "experimental",
    "result": "results",
    "results": "results",
    "discuss": "discussion",
    "discussion": "discussion",
    "conclusions": "conclusion",
    "conclusion": "conclusion",
    "summary": "conclusion",
    "title": "title",
    "abstract": "abstract",
    "body": "body",
}

_SYSTEM = """You clean academic PDF text for a one-sentence-at-a-time reader.
Remove "fish bones" (noise), keep only readable prose sentences.

DROP entirely (do not output):
- Author names, affiliations, emails, ORCID, corresponding-author lines
- Journal/citation fragments (e.g. "Soc. 2022, 144, 4186-4195", "J. Am. Chem.")
- Lone citation markers / footnote numbers (e.g. "1.", "9-12", "4,5")
- Page headers/footers, received/accepted dates, copyright lines
- References / bibliography list entries
- Figure/table captions that are not prose (optional: skip short "Fig. N. ..." lines)
- Incomplete fragments that are only initials or truncated author lists

KEEP and classify each sentence with ONE section tag:
- title: paper title only (one clean line if possible)
- abstract: abstract prose only
- introduction: Introduction / Background section
- methods: Methods / Experimental / Materials and methods
- experimental: same as methods if labeled Experimental
- results: Results / Results and discussion (results parts)
- discussion: Discussion (if separate from results)
- conclusion: Conclusion / Conclusions / Summary
- body: only if section is unclear but it is still main-text prose

CRITICAL:
- Extract ALL readable prose in THIS chunk (title/abstract/intro/methods/results/…).
- Do NOT skip early sections. An empty sentences array is ONLY for References/author-only chunks.
- Prefer completeness over brevity for scientific body text.

Rules:
- Output JSON only, no markdown fences.
- Preserve scientific meaning; do not invent facts.
- Split into proper English sentences ending with . ? !
- Do NOT put author lists or citation fragments in any section.
"""

_USER_TMPL = """Clean the following PDF text chunk (chunk {idx}/{total}).
Return as many prose sentences as this chunk contains.
Return JSON:
{{
  "sentences": [
    {{"text": "...", "section": "title"|"abstract"|"introduction"|"methods"|"experimental"|"results"|"discussion"|"conclusion"|"body"}}
  ]
}}

CHUNK:
---
{chunk}
---
"""


@dataclass
class DeboneResult:
    sentences: list[Sentence] = field(default_factory=list)
    ok: bool = False
    warning: str | None = None
    chunks_ok: int = 0
    chunks_total: int = 0


def chunk_raw_text(text: str, size: int = _CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # prefer break at paragraph / sentence
            window = text[start:end]
            br = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("? "))
            if br > size // 3:
                end = start + br + (2 if window[br : br + 2] == "\n\n" else 1)
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            # WHY: 출력이 잘리면 전체 JSON 파싱 실패 → 완성된 객체만 회수
            recovered = _recover_sentence_objects(text)
            if recovered:
                return {"sentences": recovered}
            raise


def _recover_sentence_objects(text: str) -> list[dict]:
    """잘린 JSON에서 {text, section} 객체만 정규식으로 회수."""
    out: list[dict] = []
    pat = re.compile(
        r'\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"section"\s*:\s*"([A-Za-z_]+)"\s*\}'
        r'|'
        r'\{\s*"section"\s*:\s*"([A-Za-z_]+)"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"\s*\}'
    )
    for m in pat.finditer(text or ""):
        if m.group(1) is not None:
            raw_text, section = m.group(1), m.group(2)
        else:
            section, raw_text = m.group(3), m.group(4)
        try:
            decoded = json.loads(f'"{raw_text}"')
        except json.JSONDecodeError:
            decoded = raw_text.encode("utf-8").decode("unicode_escape", errors="ignore")
        decoded = (decoded or "").strip()
        if decoded:
            out.append({"text": decoded, "section": section})
    return out


def _call_gemini(system: str, user: str) -> str:
    from google import genai
    from google.genai import types

    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=gemini_model(),
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.15,
            max_output_tokens=16384,
            response_mime_type="application/json",
        ),
    )
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            t = getattr(part, "text", None) or ""
            if t:
                parts.append(t)
    out = "".join(parts).strip()
    if not out:
        raise RuntimeError("Gemini empty response")
    return out


def _normalize_section(raw: str) -> str:
    key = (raw or "body").strip().lower()
    return _SECTION_ALIASES.get(key, "body")


def _parse_chunk_sentences(payload: dict) -> list[tuple[str, str]]:
    rows = payload.get("sentences") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        section = _normalize_section(str(row.get("section") or "body"))
        if not text or section == "skip":
            continue
        if len(text) < 12 and re.fullmatch(r"[\d\-–,.\s]+", text):
            continue
        out.append((text, section))
    return out


def _process_one_chunk(chunk: str, idx: int, total: int) -> list[tuple[str, str]]:
    """청크 1개 — 재시도 + 잘린 JSON 회수."""
    import time

    user = _USER_TMPL.format(idx=idx + 1, total=total, chunk=chunk)
    last_err: Exception | None = None
    for attempt in range(_MAX_CHUNK_RETRIES):
        try:
            raw = _call_gemini(_SYSTEM, user)
            # 빈 배열도 성공(레퍼런스 청크)
            if raw.strip() in ("{}", "[]", '{"sentences":[]}', '{"sentences": []}'):
                return []
            payload = _extract_json(raw)
            return _parse_chunk_sentences(payload)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.6 * (attempt + 1))
    assert last_err is not None
    raise last_err


def _assemble_sentences(collected: list[tuple[str, str]]) -> list[Sentence]:
    decorated: list[tuple[int, int, str, str]] = []
    for i, (text, section) in enumerate(collected):
        order = _SECTION_ORDER.get(section, _SECTION_ORDER["body"])
        decorated.append((order, i, text, section))
    decorated.sort(key=lambda t: (t[0], t[1]))

    title_seen = False
    sentences: list[Sentence] = []
    for _, _, text, section in decorated:
        if section == "title":
            if title_seen:
                continue
            title_seen = True
        sentences.append(
            Sentence(
                id=f"sent_{len(sentences):06d}",
                text=text,
                section=section,
            )
        )
        if len(sentences) >= 5000:
            break
    return sentences


def _missing_front_matter(sentences: list[Sentence], raw_text: str) -> bool:
    """원문에 Abstract/Introduction 이 있는데 결과에 앞부분이 없으면 True."""
    secs = {s.section for s in sentences}
    has_front = bool(secs & {"title", "abstract", "introduction"})
    if has_front:
        return False
    head = (raw_text or "")[:12000]
    return bool(re.search(r"\bAbstract\b|\bIntroduction\b", head, flags=re.IGNORECASE))


def debone_sentences(
    raw_text: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> DeboneResult:
    """
    Gemini로 raw PDF 텍스트를 정제해 Sentence 리스트를 만든다.
    on_progress(done_chunks, total_chunks) — 각 청크 시작 시·전부 끝날 때 호출.
    """
    if not gemini_api_key():
        return DeboneResult(ok=False, warning="gemini_key_missing")

    chunks = chunk_raw_text(raw_text)
    if not chunks:
        return DeboneResult(ok=False, warning="empty_text")

    total = len(chunks)
    results: list[list[tuple[str, str]] | None] = [None] * total
    failed: list[int] = []
    last_err: str | None = None

    for i, chunk in enumerate(chunks):
        if on_progress is not None:
            on_progress(i, total)
        try:
            results[i] = _process_one_chunk(chunk, i, total)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            failed.append(i)

    # 실패한 앞쪽 청크 한 번 더 (Discussion만 남는 사고 방지)
    for i in list(failed):
        try:
            results[i] = _process_one_chunk(chunks[i], i, total)
            failed.remove(i)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

    if on_progress is not None:
        on_progress(total, total)

    collected: list[tuple[str, str]] = []
    chunks_ok = 0
    for i, pairs in enumerate(results):
        if pairs is None:
            continue
        chunks_ok += 1
        collected.extend(pairs)

    if not collected:
        return DeboneResult(
            ok=False,
            warning=last_err or "gemini_no_sentences",
            chunks_ok=chunks_ok,
            chunks_total=total,
        )

    sentences = _assemble_sentences(collected)

    # 앞부분(제목·초록·서론)이 통째로 사라졌으면 앞 절반 청크 강제 재시도
    if _missing_front_matter(sentences, raw_text):
        retry_upto = max(1, (total + 1) // 2)
        for i in range(retry_upto):
            try:
                results[i] = _process_one_chunk(chunks[i], i, total)
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
        collected = []
        chunks_ok = 0
        for pairs in results:
            if pairs is None:
                continue
            chunks_ok += 1
            collected.extend(pairs)
        sentences = _assemble_sentences(collected)

    if not sentences:
        return DeboneResult(
            ok=False,
            warning=last_err or "gemini_no_sentences",
            chunks_ok=chunks_ok,
            chunks_total=total,
        )

    warning = None
    if failed or chunks_ok < total:
        warning = f"partial_debone:{chunks_ok}/{total}" + (
            f":{last_err}" if last_err else ""
        )
    if _missing_front_matter(sentences, raw_text):
        warning = (warning + ";" if warning else "") + "missing_front_matter"

    return DeboneResult(
        sentences=sentences,
        ok=True,
        warning=warning,
        chunks_ok=chunks_ok,
        chunks_total=total,
    )
