"""
무엇을: PDF/DOCX raw 텍스트 → (survey) → Gemini 가시 제거 + rich 첨자 → 문장.
왜: 단순 분할은 저자·인용·각주 번호를 본문으로 남긴다. 청크만으로는 섹션·화학식 맥락이 약하다.
다음에: 스트리밍 진행률, 캐시, 모델 선택 UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import threading

from sentence_reading.cite_refs import (
    repair_dollar_cite_artifacts,
    split_off_bibliography_lines,
)
from sentence_reading.llm.term_dict import build_term_dict
from sentence_reading.llm.debone_quality import (
    ChunkStat,
    apply_grounding_flags,
    build_ingest_quality,
    chunk_kind,
    chunk_text_delivered,
    chunk_under_yielded,
    drop_back_matter_sentences,
    fallback_split_chunk,
    pairs_chars,
    pin_rescue_worth_keeping,
    prose_chars,
    quality_to_warnings,
)
from sentence_reading.llm.env import gemini_api_key, gemini_model
from sentence_reading.llm.richtext import plain_text, sanitize_sentence_html
from sentence_reading.llm.typography import PIPELINE_VERSION, apply_glossary
from sentence_reading.models import Sentence
from sentence_reading.pdf.box_marks import place_sentences_in_boxes

_CHUNK_CHARS = 5000
_MAX_CHUNK_RETRIES = 3
# WHY: design/13 — survey에 넣을 평문 상한 (모델 한도·지연 여유)
_SURVEY_MAX_CHARS = 120_000
# WHY: design/12 — section is a label for the header/nav, not a sort key.
# design/322 removed the rank table: reading order is the paper's own order.
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
    "supplementary": "supplementary",
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
    {{"raw": "flattened form as in text", "rich": "same with <sub> <sup> only",
      "spoken": "how a chemist reads it aloud, or \"\" if unsure"}}
  ],
  "symbols": [
    {{"raw": "as in text", "rich": "<i>σ</i> or similar", "note": "optional"}}
  ]
}}
Use only tags <sub> <sup> <i> <em> in rich fields — never LaTeX ($…$).
Do NOT put bracket citations ([1], [8, 9]) in formulas or symbols.
Keep formulas/symbols lists short (max ~40 each).

For `spoken`, give the name a chemist would say out loud for that exact formula:
CoFe2O4 → "cobalt ferrite", Al2O3 → "alumina", BrO3- → "bromate". If this paper's
authors use their own short name for a doped composition, give that
(Ba0.5Sr0.5Co0.8Fe0.2O3-δ → "BSCF"). Every element in the formula must be accounted
for by the name — a name that leaves one out will be discarded. Leave `spoken` empty
rather than guess.

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
- Journal/citation fragments that are NOT part of a prose sentence (e.g. orphan "Soc. 2022, 144, 4186-4195")
- Lone citation markers / footnote numbers that are the ENTIRE line (e.g. a line that is only "1.", "9-12", "4,5")
- Page headers/footers, received/accepted dates, copyright lines
- References / bibliography list entries (the References section itself)
- Figure/table captions that are not prose (optional: skip short "Fig. N. ..." lines)
- Incomplete fragments that are only initials or truncated author lists

KEEP citation markers that are ATTACHED to prose sentences:
- Bracket citations like [12], [1-3], [1,2] at the end of or inside a sentence — keep them in the sentence text
- Never use LaTeX $n for citations; keep bracket cites like [8, 9] only
- Do NOT invent citations; only preserve ones present in the source chunk

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

EMPTY OUTPUT RULE (critical):
- Return {"sentences":[]} ONLY when this chunk contains NO readable prose
  (References list only, author block only, page numbers only).
- If the chunk contains experimental/results/conclusion prose, you MUST output those sentences.
- Never fabricate content not present in CHUNK. When in doubt, quote the source with minimal typography fixes.

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
    warnings: list[str] = field(default_factory=list)
    chunks_ok: int = 0
    chunks_total: int = 0
    ingest_quality: dict | None = None
    title_guess: str = ""
    # design/343 — this paper's verified `printed -> spoken` compound names.
    speak_terms: dict[str, str] = field(default_factory=dict)


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
    # design/343 — names that passed the element-accounting gate, and the printed
    # forms whose proposed name was refused.
    speak_terms: dict[str, str] = field(default_factory=dict)
    terms_refused: list[str] = field(default_factory=list)

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


def _split_keeping_sentences(body: str, size: int) -> list[str]:
    """Cut at a sentence end, never mid-sentence (design/349).

    Two paths used to do this and only one of them looked for a boundary. The pinned
    path — the one live takes, since the reading-order service always marks sections —
    cut at exactly `size`. A sentence straddling the cut then reached the model as a
    fragment at the end of one chunk and another fragment at the start of the next, and
    both were dropped as fragments. Every genuine loss left after design/347 sat at 88
    to 99% of its chunk, and one pair sat on both sides of the same cut.
    """
    body = (body or "").strip()
    if not body:
        return []
    out: list[str] = []
    start, n = 0, len(body)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = body[start:end]
            br = max(
                window.rfind("\n\n"),
                window.rfind(". "),
                window.rfind(".\n"),
                window.rfind("? "),
                window.rfind("! "),
            )
            if br > size // 3:
                end = start + br + (2 if window[br : br + 2] == "\n\n" else 1)
        piece = body[start:end].strip()
        start = end
        if piece:
            out.append(piece)
    return out


def chunk_raw_text(text: str, size: int = _CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if "<<<ASR_SECTION " in text:
        from sentence_reading.pdf.section_flow import section_mark

        parts = re.split(r"(?=<<<ASR_SECTION [a-z][a-z0-9_]*>>>)", text)
        chunks: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            pinned = re.match(r"<<<ASR_SECTION ([a-z][a-z0-9_]*)>>>", part)
            key = pinned.group(1) if pinned else ""
            body = re.sub(r"^<<<ASR_SECTION [a-z][a-z0-9_]*>>>\s*", "", part).strip()
            if not body:
                continue
            if len(body) <= size:
                chunks.append(f"{section_mark(key)}\n{body}" if key else body)
                continue
            for piece in _split_keeping_sentences(body, size):
                chunks.append(f"{section_mark(key)}\n{piece}" if key else piece)
        return [c for c in chunks if c]
    if len(text) <= size:
        return [text]

    return _split_keeping_sentences(text, size)


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


# design/106 — hard cap so quality/debone cannot block ingest forever.
_GEMINI_TEXT_TIMEOUT_S = 90.0


def _call_gemini(system: str, user: str, *, timeout_s: float | None = None) -> str:
    import concurrent.futures

    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")

    limit = float(_GEMINI_TEXT_TIMEOUT_S if timeout_s is None else timeout_s)

    def _run() -> str:
        from google import genai
        from google.genai import types

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
        try:
            from sentence_reading.llm.usage_meter import record_gemini_response

            record_gemini_response(f"{system}\n{user}", response)
        except Exception:  # noqa: BLE001
            pass
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run)
        try:
            return fut.result(timeout=limit)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(f"Gemini text timed out after {limit:.0f}s") from exc


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
            spoken = str(row.get("spoken") or "").strip()
            if raw and rich:
                row_out = {"raw": raw[:200], "rich": rich[:400]}
                # design/343 — the name is kept for the gate to judge later, not
                # trusted here.
                if spoken:
                    row_out["spoken"] = spoken[:120]
                ctx.formulas.append(row_out)
    # design/343 — judge the proposed names once, here, so nothing downstream has to
    # decide whether to trust them.
    ctx.speak_terms, ctx.terms_refused = build_term_dict(ctx.formulas)
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


# Long Gemini chunk can exceed client hang (180s). Re-fire on_progress while waiting
# so ingest job message/GCS stay alive (Turn2 hang at debone 8/14).
_DEBONE_HEARTBEAT_S = 25.0


@contextmanager
def _debone_chunk_heartbeat(
    on_progress: Callable[[int, int], None] | None,
    *,
    done: int,
    total: int,
    interval_s: float = _DEBONE_HEARTBEAT_S,
) -> Iterator[None]:
    """While a chunk Gemini call blocks, re-emit the same done/total as a liveness tick."""
    if on_progress is None or interval_s <= 0:
        yield
        return
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_s):
            try:
                on_progress(done, total)
            except Exception:  # noqa: BLE001
                break

    thr = threading.Thread(
        target=_loop,
        name=f"debone-hb-{done}",
        daemon=True,
    )
    thr.start()
    try:
        yield
    finally:
        stop.set()
        thr.join(timeout=1.0)


def _process_chunk_with_guard(
    chunk: str,
    idx: int,
    total: int,
    context_block: str,
    ctx: PaperContext,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    progress_done: int | None = None,
    progress_total: int | None = None,
) -> tuple[list[tuple[str, str]], ChunkStat]:
    """Gemini debone + substantive-empty guard + split fallback (design/167)."""
    kind = chunk_kind(chunk)
    pinned = None
    work = chunk
    bib_dropped = 0
    pin_rejected = False
    if "<<<ASR_SECTION " in chunk:
        from sentence_reading.pdf.section_flow import pinned_section, strip_section_mark

        pinned = pinned_section(chunk)
        work = strip_section_mark(chunk)
        kind = chunk_kind(work)

    # design/335 — the pin decided deletion on its own. When the run starts too
    # early it swallows body prose, so keep the lines that are not reference
    # entries and drop only the ones that are.
    # design/336 — the same duty applies to `chunk_kind`'s own verdict. It reads a
    # heading in the first 800 characters and `REFERENCES_HEAD_RE` also matches
    # `Acknowledgements`, so one chunk holding acknowledgements, references and an
    # appendix used to be emptied whole with `ok=True` and nothing counted.
    verdict = "pin" if pinned == "references" else ("kind" if kind == "references" else "")
    if verdict:
        whole = work
        kept, bib_dropped = split_off_bibliography_lines(whole)
        if pin_rescue_worth_keeping(kept, whole):
            work = kept
            if verdict == "pin":
                pinned = "body"
            pin_rejected = True
            kind = chunk_kind(work)
        else:
            # An honored verdict keeps the label, so it reads as a deliberate drop
            # rather than an empty chunk that failed.
            bib_dropped = prose_chars(whole)
            work = ""
            kind = "references"
    stat = ChunkStat(
        index=idx,
        chars_in=len(chunk),
        sentences_out=0,
        ok=False,
        kind=kind,
        bib_chars_dropped=bib_dropped,
        references_pin_rejected=pin_rejected,
        references_verdict=verdict,
    )
    # design/263 — bibliography chunks must not become practice sentences.
    if kind == "references":
        stat.ok = True
        return [], stat
    pairs: list[tuple[str, str]] | None = None
    hb_done = progress_done if progress_done is not None else (1 + idx)
    hb_total = progress_total if progress_total is not None else (total + 1)
    try:
        with _debone_chunk_heartbeat(
            on_progress, done=hb_done, total=hb_total
        ):
            pairs = _process_one_chunk(work, idx, total, context_block)
            if not pairs and kind == "substantive":
                pairs = _process_one_chunk(work, idx, total, context_block)
                if not pairs:
                    pairs = fallback_split_chunk(work, ctx, idx, total)
                    stat.fallback = "split"
            elif pairs is None:
                pairs = []
            elif kind == "substantive" and chunk_under_yielded(work, pairs):
                # design/334 — handing back a fraction of the prose is a failure
                # too. design/167 only caught a chunk that returned nothing, so a
                # chunk giving 10% of its sentences reported ok and the rest of
                # the section was gone with no warning.
                stat.low_yield = True
                retry = _process_one_chunk(work, idx, total, context_block)
                if retry and not chunk_under_yielded(work, retry):
                    pairs = retry
                else:
                    best = retry if pairs_chars(retry) > pairs_chars(pairs) else pairs
                    split = fallback_split_chunk(work, ctx, idx, total)
                    # Only take the splitter when it actually returns more.
                    if pairs_chars(split) > pairs_chars(best):
                        pairs = split
                        stat.fallback = "split"
                    else:
                        pairs = best
        if pinned:
            pairs = [] if pinned == "references" else [(text, pinned) for text, _sec in (pairs or [])]
    except Exception:  # noqa: BLE001
        pairs = fallback_split_chunk(work, ctx, idx, total)
        if pinned:
            pairs = [] if pinned == "references" else [(text, pinned) for text, _sec in (pairs or [])]
        stat.fallback = "split"

    stat.sentences_out = len(pairs or [])
    stat.chars_out = pairs_chars(pairs)
    # design/345 — per-chunk text delivery is *reported*, not gated. The threshold a
    # gate would need has to come from an in-run measurement, and the first attempt
    # compared stored sentences against a fresh extraction, which measures the
    # extractor's own variation instead of the pipeline's loss.
    stat.text_coverage, _missing = chunk_text_delivered(work, pairs)
    stat.ok = stat.sentences_out > 0 or kind in ("references", "sparse")
    return pairs or [], stat


def _assemble_sentences(collected: list[tuple[str, str]]) -> list[Sentence]:
    """design/322 — keep the paper's own order.

    `collected` already arrives in chunk order, which is source order on both
    the pinned (Azure section marks) and unpinned paths, and the front-matter
    retry writes back at the same index rather than appending. Ranking by
    section therefore reordered the paper for no gain: a journal that prints
    Methods after Discussion was shown Methods before Results, `methods` and
    `experimental` share a rank so their chunks interleaved, and any heading
    that fell through to `body` was moved after the conclusion. Only one
    sentence is on screen, so none of that is visible to the reader.

    The title card still leads, matching `title_replay.align_title_sentences`.
    """
    # Only the first title-labelled item in source order is the title card.
    # design/325 — everything before the first recognised heading is pinned
    # `title`, so on a paper whose headings do not parse that run holds the
    # abstract, introduction and results. Dropping it deleted 79% of a real
    # 4-page paper. The rest keep their text under a neutral label, and they
    # keep their own position rather than being hoisted with the title.
    title_seen = False
    decorated: list[tuple[int, int, str, str]] = []
    for i, (text, section) in enumerate(collected):
        sec = section
        rank = 1
        if sec == "title":
            if title_seen:
                sec = "body"
            else:
                title_seen = True
                rank = 0
        decorated.append((rank, i, text, sec))
    decorated.sort(key=lambda t: (t[0], t[1]))

    sentences: list[Sentence] = []
    for _, _, text, section in decorated:
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


def _apply_glossary_sentences(
    sentences: list[Sentence], ctx: PaperContext
) -> list[Sentence]:
    if not (ctx.formulas or ctx.symbols):
        return sentences
    return [
        Sentence(
            id=s.id,
            text=apply_glossary(s.text, formulas=ctx.formulas, symbols=ctx.symbols),
            section=s.section,
            start_char=s.start_char,
            end_char=s.end_char,
            text_ko=s.text_ko,
            text_ko_stage=s.text_ko_stage,
            quality_flags=s.quality_flags,
        )
        for s in sentences
    ]


def _collect_from_results(
    results: list[list[tuple[str, str]] | None],
) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []
    for pairs in results:
        if pairs is None:
            continue
        collected.extend(pairs)
    return collected


def debone_sentences(
    raw_text: str,
    on_progress: Callable[[int, int], None] | None = None,
    box_marks: list | None = None,
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
    chunk_stats: list[ChunkStat] = []
    failed: list[int] = []
    last_err: str | None = None

    for i, chunk in enumerate(chunks):
        if on_progress is not None:
            on_progress(1 + i, progress_total)
        try:
            pairs, stat = _process_chunk_with_guard(
                chunk,
                i,
                n_chunks,
                context_block,
                ctx,
                on_progress=on_progress,
                progress_done=1 + i,
                progress_total=progress_total,
            )
            results[i] = pairs
            chunk_stats.append(stat)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            failed.append(i)
            try:
                pairs = fallback_split_chunk(chunk, ctx, i, n_chunks)
                results[i] = pairs
                chunk_stats.append(
                    ChunkStat(
                        index=i,
                        chars_in=len(chunk),
                        sentences_out=len(pairs),
                        ok=bool(pairs),
                        kind=chunk_kind(chunk),
                        fallback="split",
                    )
                )
            except Exception:  # noqa: BLE001
                results[i] = None
                chunk_stats.append(
                    ChunkStat(
                        index=i,
                        chars_in=len(chunk),
                        sentences_out=0,
                        ok=False,
                        kind=chunk_kind(chunk),
                    )
                )

    if on_progress is not None:
        on_progress(progress_total, progress_total)

    collected = _collect_from_results(results)

    if not collected:
        return DeboneResult(
            ok=False,
            warning=last_err or "gemini_no_sentences",
            warnings=[last_err or "gemini_no_sentences"],
            chunks_ok=sum(1 for s in chunk_stats if s.ok),
            chunks_total=n_chunks,
        )

    sentences = _assemble_sentences(collected)
    sentences = _apply_glossary_sentences(sentences, ctx)

    # 앞부분(제목·초록·서론)이 통째로 사라졌으면 앞 절반 청크 강제 재시도
    if _missing_front_matter(sentences, raw_text):
        retry_upto = max(1, (n_chunks + 1) // 2)
        for i in range(retry_upto):
            try:
                pairs, stat = _process_chunk_with_guard(
                    chunks[i],
                    i,
                    n_chunks,
                    context_block,
                    ctx,
                    on_progress=on_progress,
                    progress_done=1 + i,
                    progress_total=progress_total,
                )
                results[i] = pairs
                if i < len(chunk_stats):
                    chunk_stats[i] = stat
                else:
                    chunk_stats.append(stat)
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
        collected = _collect_from_results(results)
        sentences = _apply_glossary_sentences(_assemble_sentences(collected), ctx)

    sentences = [
        Sentence(
            id=s.id,
            text=repair_dollar_cite_artifacts(s.text),
            section=s.section,
            start_char=s.start_char,
            end_char=s.end_char,
            text_ko=s.text_ko,
            text_ko_stage=s.text_ko_stage,
            quality_flags=s.quality_flags,
        )
        for s in sentences
    ]
    # design/352 — give each sentence the position of the box it came from, found by the
    # box's own opening sentence rather than by searching the paper for six of the
    # sentence's words. Measured over ten papers: 359 of 368 markers located (97.6%),
    # 342 of them to within 5%, five papers at 100%. A marker that is not
    # found leaves its sentences with the box before it, its neighbour in reading order,
    # so precision drops and nothing breaks.
    sentences, mark_census = place_sentences_in_boxes(sentences, box_marks or [])
    if mark_census.marked:
        warnings.extend(
            f"{k}:{v}" for k, v in mark_census.to_dict().items() if k != "box_n" and v
        )

    # design/340 — the journal's apparatus is not the paper. `strip_back_matter`
    # already removed exactly this from the coverage denominator, so leaving it in
    # the sentence stream made the metric and the product disagree about what
    # practice text is.
    sentences, back_matter_n = drop_back_matter_sentences(sentences)

    sentences, ungrounded_ids = apply_grounding_flags(sentences, raw_text)

    if not sentences:
        return DeboneResult(
            ok=False,
            warning=last_err or "gemini_no_sentences",
            warnings=[last_err or "gemini_no_sentences"],
            chunks_ok=sum(1 for s in chunk_stats if s.ok),
            chunks_total=n_chunks,
        )

    missing_front = _missing_front_matter(sentences, raw_text)
    iq = build_ingest_quality(
        raw_text=raw_text,
        sentences=sentences,
        chunk_stats=chunk_stats,
        ungrounded_ids=ungrounded_ids,
        partial_debone_failed=failed,
        back_matter_dropped=back_matter_n,
    )
    # design/343 — a name the gate threw out is a name the reader would have heard.
    if ctx.terms_refused:
        warnings.append(f"speak_terms_refused:{len(ctx.terms_refused)}")
    if ctx.speak_terms:
        warnings.append(f"speak_terms:{len(ctx.speak_terms)}")
    warn_list = quality_to_warnings(
        iq,
        survey_warnings=warnings,
        missing_front_matter=missing_front,
    )
    warning_str = ";".join(warn_list) if warn_list else None

    return DeboneResult(
        sentences=sentences,
        ok=True,
        warning=warning_str,
        warnings=warn_list,
        chunks_ok=iq.chunks_ok,
        chunks_total=n_chunks,
        ingest_quality=iq.to_dict(),
        title_guess=ctx.title_guess,
        speak_terms=dict(ctx.speak_terms),
    )
