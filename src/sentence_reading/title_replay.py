"""Title-path tokens for replay. Never return paper text."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_SI_BANNER = re.compile(
    r"^(?:supporting|supplementary)\s+information\.?$",
    re.IGNORECASE,
)
# Do not replace this assignment when adding a sibling regex (design/297).
_ELSEVIER_STEM = re.compile(r"^1-s2\.0-S\d", re.IGNORECASE)
_CHROME_TITLE = re.compile(
    r"\b(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t|article\s+info|keywords)\b",
    re.IGNORECASE,
)
_AFFIL_TITLE = re.compile(
    r"^(?:key laboratory|school of|department of|university of|"
    r"corresponding author|email\s*:)",
    re.IGNORECASE,
)


def title_class(raw: str) -> str:
    """empty | si_banner | code_like | text. Counts/tokens only."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return "empty"
    if _SI_BANNER.match(text):
        return "si_banner"
    if _ELSEVIER_STEM.match(text):
        return "code_like"
    digits = sum(c.isdigit() for c in text)
    if " " not in text and digits > len(text) * 0.35:
        return "code_like"
    return "text"


def session_title_source(sentences: list) -> str:
    """Ingest uses a section=title card, otherwise the filename stem."""
    for row in sentences:
        section = str(getattr(row, "section", "") or "")
        piece = str(getattr(row, "text", "") or "").strip()
        if section == "title" and piece:
            return "section_title"
    return "filename_stem"


def docx_core_title(path: Path) -> str:
    """dc:title only. Caller must classify it and not print it."""
    try:
        with zipfile.ZipFile(path) as zf:
            if "docProps/core.xml" not in zf.namelist():
                return ""
            root = ET.fromstring(zf.read("docProps/core.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return ""
    for el in root.iter():
        if str(el.tag).rsplit("}", 1)[-1].lower() != "title":
            continue
        piece = (el.text or "").strip()
        if piece:
            return piece
    return ""


def pdf_info_title(path: Path) -> str:
    """PDF Info.Title. Caller must classify it and not print it."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # type: ignore
        doc = pymupdf.open(path)
        try:
            meta = doc.metadata or {}
            return str(meta.get("title") or "").strip()
        finally:
            doc.close()


def looks_like_author_dump(raw: str) -> bool:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if len(text) < 16 or len(text) > 420:
        return False
    commas = text.count(",")
    stars = text.count("*")
    if stars >= 1 and commas >= 2:
        return True
    if commas >= 3 and not re.search(
        r"\b(of|for|with|from|over|via|using|toward|towards)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def title_usable(raw: str) -> bool:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if title_class(text) != "text":
        return False
    if len(text) < 12 or len(text) > 350:
        return False
    if _CHROME_TITLE.search(text) or _AFFIL_TITLE.search(text):
        return False
    if looks_like_author_dump(text):
        return False
    return True


def head_title_text(text: str) -> str:
    """Paragraph after an SI banner. Empty if none."""
    seen_banner = False
    for block in re.split(r"\n\s*\n", text or ""):
        piece = re.sub(r"\s+", " ", block).strip()
        if not piece:
            continue
        if title_class(piece) == "si_banner":
            seen_banner = True
            continue
        if seen_banner and title_usable(piece):
            return piece
    return ""


def join_largest_title_lines(lines: list[tuple[float, str]]) -> str:
    """Join the first run of lines at the largest usable font size."""
    ranked: list[tuple[float, str]] = []
    for size, raw in lines:
        piece = re.sub(r"\s+", " ", raw or "").strip()
        if not piece or looks_like_author_dump(piece):
            continue
        if title_class(piece) == "si_banner" or _CHROME_TITLE.search(piece):
            continue
        if len(piece) < 8:
            continue
        ranked.append((float(size), piece))
    if not ranked:
        return ""
    top = max(size for size, _ in ranked)
    parts: list[str] = []
    started = False
    for size, raw in lines:
        piece = re.sub(r"\s+", " ", raw or "").strip()
        if abs(float(size) - top) <= 0.45 and piece and not looks_like_author_dump(piece):
            if title_class(piece) == "si_banner" or _CHROME_TITLE.search(piece):
                if started:
                    break
                continue
            parts.append(piece)
            started = True
            continue
        if started:
            break
    joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return joined if title_usable(joined) else ""


def pdf_styled_title(path: Path) -> str:
    """First-page largest font run. Empty on failure. Caller must not print it."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # type: ignore
        doc = pymupdf.open(path)
        try:
            if doc.page_count < 1:
                return ""
            page = doc[0]
            lines: list[tuple[float, str]] = []
            for block in page.get_text("dict").get("blocks") or []:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines") or []:
                    spans = line.get("spans") or []
                    piece = "".join(str(s.get("text") or "") for s in spans).strip()
                    if not piece:
                        continue
                    size = max((float(s.get("size") or 0) for s in spans), default=0.0)
                    lines.append((size, piece))
            return join_largest_title_lines(lines)
        finally:
            doc.close()


def pick_session_title(
    *,
    info_title: str = "",
    filename: str = "",
    text: str = "",
    sentences: list | None = None,
    title_guess: str = "",
    styled_title: str = "",
) -> tuple[str, str]:
    """Paper title for session.title. Metadata and head beat a bad section=title card."""
    for candidate, source in (
        (info_title, "info"),
        (styled_title, "styled"),
        (head_title_text(text), "head"),
        (title_guess, "title_guess"),
    ):
        piece = re.sub(r"\s+", " ", (candidate or "").strip())
        if title_usable(piece):
            return piece, source
    for row in sentences or []:
        section = str(getattr(row, "section", "") or "")
        piece = re.sub(r"\s+", " ", str(getattr(row, "text", "") or "").strip())
        if section == "title" and title_usable(piece):
            return piece, "section_title"
    stem = Path(filename).stem
    if title_usable(stem):
        return stem, "stem"
    return stem or "Untitled", "stem_fallback"


def align_title_sentences(sentences: list, picked_title: str) -> tuple[list, str]:
    """Make the Title card match the picked title. Drop a chrome card's translation.

    Card token is absent | kept | replaced. Never returns paper text.
    """
    from sentence_reading.models import Sentence

    picked = re.sub(r"\s+", " ", (picked_title or "").strip())
    has_title = any(
        str(getattr(row, "section", "") or "") == "title" for row in sentences or []
    )
    if not title_usable(picked):
        return list(sentences or []), ("kept" if has_title else "absent")
    out: list = []
    card = "absent"
    kept_one = False
    for row in sentences or []:
        section = str(getattr(row, "section", "") or "")
        text = re.sub(r"\s+", " ", str(getattr(row, "text", "") or "").strip())
        if section != "title":
            out.append(row)
            continue
        if kept_one:
            card = "replaced"
            continue
        kept_one = True
        if text == picked:
            card = "kept"
            out.append(row)
            continue
        card = "replaced"
        out.append(
            Sentence(
                id=str(getattr(row, "id", "") or "sent_title"),
                text=picked,
                section="title",
                start_char=getattr(row, "start_char", None),
                end_char=getattr(row, "end_char", None),
                text_ko="",
                text_ko_stage="",
                quality_flags=tuple(getattr(row, "quality_flags", ()) or ()),
            )
        )
    return out, card


def head_title_after_banner(text: str) -> int:
    return 1 if head_title_text(text) else 0


def title_replay_fields(
    *,
    info_title: str,
    filename: str,
    text: str,
    sentences: list,
    title_guess: str = "",
    styled_title: str = "",
) -> dict[str, int | str]:
    info_kind = title_class(info_title)
    stem = Path(filename).stem
    stem_kind = title_class(stem)
    source = session_title_source(sentences)
    picked, picked_source = pick_session_title(
        info_title=info_title,
        filename=filename,
        text=text,
        sentences=sentences,
        title_guess=title_guess,
        styled_title=styled_title,
    )
    verdicts: list[str] = []
    if info_kind == "empty":
        verdicts.append("info_title_empty")
    elif info_kind == "si_banner":
        verdicts.append("info_title_si_banner")
    elif info_kind == "text":
        verdicts.append("info_title_present")
    if source == "filename_stem":
        verdicts.append("session_title_is_stem")
    if stem_kind == "code_like":
        verdicts.append("stem_code_like")
    return {
        "info_title_class": info_kind,
        "info_title_char_n": len((info_title or "").strip()),
        "stem_class": stem_kind,
        "session_title_source": source,
        "head_title_after_banner": head_title_after_banner(text),
        "picked_title_source": picked_source,
        "picked_title_class": title_class(picked),
        "picked_title_char_n": len(picked),
        "title_verdict": verdicts[0] if verdicts else "none",
    }
