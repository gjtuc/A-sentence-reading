"""
무엇을: PDF/DOCX raw 텍스트 → (survey) → Gemini 가시 제거 + rich 첨자 → 문장.
왜: 단순 분할은 저자·인용·각주 번호를 본문으로 남긴다. 청크만으로는 섹션·화학식 맥락이 약하다.
다음에: 스트리밍 진행률, 캐시, 모델 선택 UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sentence_reading.llm.env import gemini_api_key, gemini_model
from sentence_reading.llm.richtext import plain_text, sanitize_sentence_html
from sentence_reading.llm.typography import PIPELINE_VERSION, apply_glossary
from sentence_reading.models import Sentence

_CHUNK_CHARS = 5000
_MAX_CHUNK_RETRIES = 3
# WHY: design/13 — survey에 넣을 평문 상한 (모델 한도·지연 여유)
_SURVEY_MAX_CHARS = 120_000
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

_SURVEY_SYSTEM = """You survey one academic paper's extracted plain text.
PDF/DOCX extraction often flattens subscripts (BaZr0.9Y0.1O3-δ), superscripts (cm-1, 10-3),
and italics (variables, Greek letters). Build a compact map for a later cleaning pass.

Output JSON only, no markdown fences.
Do not invent chemistry that is not suggested by the text; prefer items that appear repeatedly.
"""

_SURVEY_USER = """Survey this paper text and return JSON:
{{
  "title_guess": "plain title if visible",
  "section_order": ["title","abstract","introduction","methods","results","discussion","conclusion"],
  "section_notes": "Short map of where sections are and odd headings.",
  "formulas": [
    {{"raw": "flattened form as in text", "rich": "same with <sub> <sup> only"}}
  ],
  "symbols": [
    {{"raw": "as in text", "rich": "<i>σ</i> or similar", "note": "optional"}}
  ]
}}
Use only tags <sub> <sup> <i> <em> in rich fields. Keep formulas/symbols lists short (max ~40 each).

PAPER TEXT:
---
{text}
---
"""

_SYSTEM = """You clean academic PDF/DOCX text for a one-sentence-at-a-time reader.
Remove "fish bones" (noise), keep only readable prose sentences.

You receive PAPER CONTEXT from a prior full-paper survey (section map + formula/symbol glossary).
Use it for section tagging and for restoring typography consistently.

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

TYPOGRAPHY (critical for science):
- Restore subscripts with <sub>…</sub> (e.g. H<sub>2</sub>O, BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3−δ</sub>)
- Restore superscripts with <sup>…</sup> (e.g. cm<sup>−1</sup>, 10<sup>−3</sup>)
- Italicize variables / Greek symbols with <i>…</i> (e.g. <i>σ</i>, <i>T</i>) — not whole sentences
- Prefer glossary rich forms from PAPER CONTEXT when the same raw token appears
- Allowed tags ONLY: <sub> <sup> <i> <em> — no attributes, no other HTML
- Do not wrap entire sentences in <i>

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

_USER_TMPL = """Clean the following PDF/DOCX text chunk (chunk {idx}/{total}).
Use PAPER CONTEXT for section placement and formula/symbol typography.
Each sentence "text" may include <sub> <sup> <i> <em> only.
Return as many prose sentences as this chunk contains.
Return JSON:
{{
  "sentences": [
    {{"text": "...", "section": "title"|"abstract"|"introduction"|"methods"|"experimental"|"results"|"discussion"|"conclusion"|"body"}}
  ]
}}

PAPER CONTEXT:
{context}

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


@dataclass
class PaperContext:
    """1차 survey 요약 — 2차 청크에 주입 (docs/design/13)."""

    title_guess: str = ""
    section_order: list[str] = field(default_factory=list)
    section_notes: str = ""
    formulas: list[dict[str, str]] = field(default_factory=list)
    symbols: list[dict[str, str]] = field(default_factory=list)
    ok: bool = False
    warning: str | None = None

    def to_prompt_block(self) -> str:
        if not self.ok and not self.section_notes and not self.formulas:
            return "(no survey context — infer carefully from the chunk alone)"
        payload = {
            "title_guess": self.title_guess,
            "section_order": self.section_order,
            "section_notes": self.section_notes,
            "formulas": self.formulas[:40],
            "symbols": self.symbols[:40],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


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
        rich = sanitize_sentence_html(str(row.get("text") or ""))
        section = _normalize_section(str(row.get("section") or "body"))
        plain = plain_text(rich)
        if not plain or section == "skip":
            continue
        if len(plain) < 12 and re.fullmatch(r"[\d\-–,.\s]+", plain):
            continue
        out.append((rich, section))
    return out


def _survey_slice(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if len(text) <= _SURVEY_MAX_CHARS:
        return text
    # WHY: 앞(제목·초록·서론) + 뒤(결론) 우선
    head = _SURVEY_MAX_CHARS * 4 // 5
    tail = _SURVEY_MAX_CHARS - head
    return text[:head] + "\n\n[...middle omitted...]\n\n" + text[-tail:]


def _parse_survey(payload: dict) -> PaperContext:
    ctx = PaperContext(ok=True)
    if not isinstance(payload, dict):
        return PaperContext(ok=False, warning="survey_bad_json")
    ctx.title_guess = str(payload.get("title_guess") or "").strip()[:500]
    order = payload.get("section_order")
    if isinstance(order, list):
        ctx.section_order = [str(x).strip().lower() for x in order if str(x).strip()][:20]
    ctx.section_notes = str(payload.get("section_notes") or "").strip()[:2000]
    formulas = payload.get("formulas")
    if isinstance(formulas, list):
        for row in formulas[:40]:
            if not isinstance(row, dict):
                continue
            raw = str(row.get("raw") or "").strip()
            rich = sanitize_sentence_html(str(row.get("rich") or ""))
            if raw and rich:
                ctx.formulas.append({"raw": raw[:200], "rich": rich[:400]})
    symbols = payload.get("symbols")
    if isinstance(symbols, list):
        for row in symbols[:40]:
            if not isinstance(row, dict):
                continue
            raw = str(row.get("raw") or "").strip()
            rich = sanitize_sentence_html(str(row.get("rich") or ""))
            note = str(row.get("note") or "").strip()[:120]
            if raw and rich:
                item = {"raw": raw[:120], "rich": rich[:200]}
                if note:
                    item["note"] = note
                ctx.symbols.append(item)
    return ctx


def survey_paper(raw_text: str) -> PaperContext:
    """논문 평문 1회 훑기 — 섹션 지도 + 화학식/기호 용어집."""
    import time

    if not gemini_api_key():
        return PaperContext(ok=False, warning="gemini_key_missing")
    slice_text = _survey_slice(raw_text)
    if not slice_text:
        return PaperContext(ok=False, warning="empty_text")
    user = _SURVEY_USER.format(text=slice_text)
    last_err: Exception | None = None
    for attempt in range(_MAX_CHUNK_RETRIES):
        try:
            raw = _call_gemini(_SURVEY_SYSTEM, user)
            payload = _extract_json(raw)
            return _parse_survey(payload)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.6 * (attempt + 1))
    return PaperContext(
        ok=False,
        warning=f"survey_failed:{last_err}" if last_err else "survey_failed",
    )


def _process_one_chunk(
    chunk: str,
    idx: int,
    total: int,
    context_block: str,
) -> list[tuple[str, str]]:
    """청크 1개 — 재시도 + 잘린 JSON 회수."""
    import time

    user = _USER_TMPL.format(
        idx=idx + 1,
        total=total,
        chunk=chunk,
        context=context_block,
    )
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
    Gemini로 raw 텍스트를 정제해 Sentence 리스트를 만든다.
    1) survey (전역) 2) 청크 debone.
    on_progress(done, total) — survey를 1단위로 포함 (total = chunks + 1).
    """
    if not gemini_api_key():
        return DeboneResult(ok=False, warning="gemini_key_missing")

    chunks = chunk_raw_text(raw_text)
    if not chunks:
        return DeboneResult(ok=False, warning="empty_text")

    n_chunks = len(chunks)
    # WHY: design/13 — survey = 진행 1단위
    progress_total = n_chunks + 1
    warnings: list[str] = []

    if on_progress is not None:
        on_progress(0, progress_total)
    ctx = survey_paper(raw_text)
    if not ctx.ok:
        warnings.append(ctx.warning or "survey_failed")
    context_block = ctx.to_prompt_block()
    if on_progress is not None:
        on_progress(1, progress_total)

    results: list[list[tuple[str, str]] | None] = [None] * n_chunks
    failed: list[int] = []
    last_err: str | None = None

    for i, chunk in enumerate(chunks):
        if on_progress is not None:
            on_progress(1 + i, progress_total)
        try:
            results[i] = _process_one_chunk(chunk, i, n_chunks, context_block)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            failed.append(i)

    # 실패한 앞쪽 청크 한 번 더 (Discussion만 남는 사고 방지)
    for i in list(failed):
        try:
            results[i] = _process_one_chunk(chunks[i], i, n_chunks, context_block)
            failed.remove(i)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

    if on_progress is not None:
        on_progress(progress_total, progress_total)

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
            chunks_total=n_chunks,
        )

    sentences = _assemble_sentences(collected)

    # WHY: 청크가 첨자 HTML을 빼먹어도 survey 용어집으로 보정
    if ctx.formulas or ctx.symbols:
        sentences = [
            Sentence(
                id=s.id,
                text=apply_glossary(
                    s.text, formulas=ctx.formulas, symbols=ctx.symbols
                ),
                section=s.section,
                start_char=s.start_char,
                end_char=s.end_char,
            )
            for s in sentences
        ]

    # 앞부분(제목·초록·서론)이 통째로 사라졌으면 앞 절반 청크 강제 재시도
    if _missing_front_matter(sentences, raw_text):
        retry_upto = max(1, (n_chunks + 1) // 2)
        for i in range(retry_upto):
            try:
                results[i] = _process_one_chunk(chunks[i], i, n_chunks, context_block)
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
        if ctx.formulas or ctx.symbols:
            sentences = [
                Sentence(
                    id=s.id,
                    text=apply_glossary(
                        s.text, formulas=ctx.formulas, symbols=ctx.symbols
                    ),
                    section=s.section,
                    start_char=s.start_char,
                    end_char=s.end_char,
                )
                for s in sentences
            ]

    if not sentences:
        return DeboneResult(
            ok=False,
            warning=last_err or "gemini_no_sentences",
            chunks_ok=chunks_ok,
            chunks_total=n_chunks,
        )

    warning = None
    if failed or chunks_ok < n_chunks:
        warning = f"partial_debone:{chunks_ok}/{n_chunks}" + (
            f":{last_err}" if last_err else ""
        )
    if _missing_front_matter(sentences, raw_text):
        warning = (warning + ";" if warning else "") + "missing_front_matter"
    if warnings:
        warning = (warning + ";" if warning else "") + ";".join(warnings)

    return DeboneResult(
        sentences=sentences,
        ok=True,
        warning=warning,
        chunks_ok=chunks_ok,
        chunks_total=n_chunks,
    )
