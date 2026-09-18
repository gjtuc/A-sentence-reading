"""Title-path tokens for replay. Never return paper text."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_SI_BANNER = re.compile(
    r"^(?:supporting information|supplementary information(?:\s+for)?|"
    r"supplementary materials?)\.?$",
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
# Publisher file ids and page ranges, not article titles.
_MANUSCRIPT_ID = re.compile(
    r"^(?:[a-z]{0,4}\d[a-z0-9]*)(?:\s+\d+\.\.\d+)?$",
    re.IGNORECASE,
)
_FILEISH = re.compile(r"\.(?:dvi|tex|fm)$", re.IGNORECASE)
_PAGE_RANGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s+\d+\.\.\d+$")
_PII = re.compile(r"^PII:\s*\S", re.IGNORECASE)
_JOURNAL_CITE = re.compile(
    r"\s*\((?:[A-Z][A-Za-z]*\.?\s+){1,5}\d+/\d{4}\)\s*$"
)
_URL_CHROME = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)
_FILE_ID = re.compile(
    r"(?:[-_]sup(?:[-_]|\d)|[-_]si[-_]\d|suppmat|[-_]mmc\d)",
    re.IGNORECASE,
)
_SI_PREFIX = re.compile(
    r"^(?:supporting information(?:\s+for)?|supplementary information(?:\s+for)?|"
    r"supplementary materials?(?:\s+for)?|supporting online material(?:\s+for)?|"
    r"electronic supplementary(?:\s+material)?(?:\s*\(esi\))?(?:\s+for)?)\s*",
    re.IGNORECASE,
)
_CAPTION = re.compile(
    r"^(?:fig(?:ure)?|table|scheme|chart)\.?\s",
    re.IGNORECASE,
)
_CHROME_LINE = re.compile(
    r"^(?:journal of\b.*|applied catalysis\b.*|chemical engineering journal|"
    r"catalysis science\s*(?:&|and)\s*technology|chem\.?\s*soc\.?\s*rev|"
    r"sustainable energy\s*(?:&|and)\s*fuels|international journal of hydrogen energy|"
    r"advanced (?:materials|energy materials)|nature catalysis|ceramics international|"
    r"carbon trends|scientific reports|contents lists available.*|"
    r"research article|view article online|review article|article info|"
    r"green chemical engineering\s*[\u2014\u2013\-]\s*article|"
    r"introduction|abstract|keywords?)$",
    re.IGNORECASE,
)


def normalize_title_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = text.replace("\u00ad", "")
    return re.sub(r"\s+", " ", text).strip()


def strip_si_banner(raw: str) -> str:
    text = normalize_title_text(raw)
    stripped = _SI_PREFIX.sub("", text).strip(" .")
    return stripped


def polish_title(raw: str) -> str:
    """Drop a journal-issue citation and a short kicker that repeats in the title."""
    text = strip_si_banner(raw)
    text = _JOURNAL_CITE.sub("", text).strip(" .")
    if ":" not in text:
        return text
    head, tail = text.split(":", 1)
    head_s, tail_s = head.strip(), tail.strip()
    if (
        1 <= len(head_s.split()) <= 4
        and head_s
        and head_s.lower() in tail_s.lower()
        and len(tail_s) >= 12
    ):
        return tail_s
    return text


def is_title_chrome(raw: str) -> bool:
    text = normalize_title_text(raw)
    text = re.sub(r"^[^A-Za-z]+", "", text).strip()
    if not text:
        return True
    if _SI_BANNER.match(text) or _CHROME_LINE.match(text) or _CHROME_TITLE.search(text):
        return True
    if _URL_CHROME.match(text):
        return True
    if _AFFIL_TITLE.search(text):
        return True
    if re.fullmatch(r"research|review|article|open access", text, flags=re.IGNORECASE):
        return True
    return False


def title_class(raw: str) -> str:
    """empty | si_banner | code_like | text. Counts/tokens only."""
    text = normalize_title_text(raw)
    if not text:
        return "empty"
    if _SI_BANNER.match(text) or (
        _SI_PREFIX.match(text) and not strip_si_banner(text)
    ):
        return "si_banner"
    if (
        _ELSEVIER_STEM.match(text)
        or _MANUSCRIPT_ID.match(text)
        or _FILEISH.search(text)
        or (" " not in text and _FILE_ID.search(text))
        or _PAGE_RANGE_ID.match(text)
        or _PII.match(text)
    ):
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


_TITLE_STYLE = re.compile(r"^(?:title|htitle|heading\s*1)$", re.IGNORECASE)


def title_from_docx_paragraphs(paragraphs) -> str:
    """Paragraph whose Word style is Title. Empty if the file has no title style."""
    for para in paragraphs or []:
        style = getattr(para, "style", None)
        name = str(getattr(style, "name", "") or "").strip()
        if not _TITLE_STYLE.match(name):
            continue
        piece = polish_title(getattr(para, "text", "") or "")
        if title_usable(piece):
            return piece
    return ""


def docx_styled_title(path: Path) -> str:
    """Word Title/htitle style. Empty on failure. Caller must not print it."""
    try:
        from docx import Document
    except ImportError:
        return ""
    try:
        doc = Document(str(path))
    except (OSError, ValueError):
        return ""
    return title_from_docx_paragraphs(doc.paragraphs)


def docx_paragraph_text(path: Path) -> str:
    """Raw paragraphs, including the SI banner title-pick needs.

    extract_text drops that banner, so session title must not use it alone.
    """
    try:
        from docx import Document
    except ImportError:
        return ""
    try:
        doc = Document(str(path))
    except (OSError, ValueError):
        return ""
    parts = [(p.text or "").strip() for p in doc.paragraphs]
    return "\n\n".join(part for part in parts if part)


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
            return normalize_title_text(str(meta.get("title") or ""))
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
    text = polish_title(raw)
    if title_class(text) != "text":
        return False
    if len(text) < 12 or len(text) > 350:
        return False
    if is_title_chrome(text) or looks_like_author_dump(text):
        return False
    return True


def head_title_text(text: str) -> str:
    """First usable paragraph. An SI banner and captions are skipped, not used."""
    for block in re.split(r"\n\s*\n", text or ""):
        piece = re.sub(r"\s+", " ", block).strip()
        if not piece or title_class(piece) == "si_banner" or _CAPTION.match(piece):
            continue
        if title_usable(piece):
            return piece
    return ""


def join_largest_title_lines(lines: list[tuple[float, str]]) -> str:
    """Join wrapped title lines at the largest font that is not journal chrome."""
    sizes: list[float] = []
    for size, raw in lines:
        piece = strip_si_banner(raw)
        if not piece or is_title_chrome(piece) or looks_like_author_dump(piece):
            continue
        if title_class(piece) != "text" or len(piece) < 8:
            continue
        sizes.append(float(size))
    if not sizes:
        return ""
    for top in sorted(set(sizes), reverse=True):
        parts: list[str] = []
        pending: list[str] = []
        started = False
        for size, raw in lines:
            piece = strip_si_banner(raw)
            delta = abs(float(size) - top)
            tight = delta <= 0.6
            loose = delta <= max(1.1, top * 0.08)
            usable_piece = (
                bool(piece)
                and not is_title_chrome(piece)
                and not looks_like_author_dump(piece)
                and title_class(piece) == "text"
            )
            if tight and usable_piece and not started and len(piece) < 8:
                pending.append(piece)
                continue
            if tight and usable_piece:
                if not started:
                    parts.extend(pending)
                    pending = []
                parts.append(piece)
                started = True
                continue
            if started and loose and usable_piece and len(piece) >= 8:
                parts.append(piece)
                continue
            pending = []
            if started:
                break
        joined = polish_title(" ".join(parts))
        if title_usable(joined):
            return joined
    return ""


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


def _soffice_exe() -> Path | None:
    import shutil

    found = shutil.which("soffice") or shutil.which("soffice.com")
    if found:
        return Path(found)
    for candidate in (
        Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
        Path("/usr/bin/soffice"),
    ):
        if candidate.is_file():
            return candidate
    return None


def docx_page_pdf(path: Path) -> Path | None:
    """Convert a docx to PDF so Azure can read page 1. None if LibreOffice is absent."""
    import subprocess
    import tempfile

    soffice = _soffice_exe()
    if soffice is None or path.suffix.lower() != ".docx":
        return None
    dest = Path(tempfile.mkdtemp(prefix="asr-docx-"))
    profile = dest / "profile"
    profile.mkdir()
    uri = "file:///" + str(profile).replace("\\", "/")
    try:
        subprocess.run(
            [
                str(soffice),
                f"-env:UserInstallation={uri}",
                "--headless",
                "--norestore",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(dest),
                str(path),
            ],
            check=False,
            timeout=90,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    pdfs = sorted(dest.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def azure_page_title(path: Path) -> str:
    """Azure prebuilt-layout title role on page 1. Empty if Azure is unavailable."""
    from sentence_reading.llm.env import azure_document_intelligence_available

    if not azure_document_intelligence_available():
        return ""
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    from sentence_reading.llm.env import (
        azure_document_intelligence_endpoint,
        azure_document_intelligence_key,
    )
    from sentence_reading.pdf.azure_layout import _timeout_s

    endpoint = azure_document_intelligence_endpoint() or ""
    key = azure_document_intelligence_key() or ""
    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )
    target = path
    if path.suffix.lower() == ".docx":
        converted = docx_page_pdf(path)
        if converted is None:
            return ""
        target = converted
    with target.open("rb") as handle:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=handle,
            pages="1",
        )
        result = poller.result(timeout=_timeout_s())
    return title_from_azure_paragraphs(getattr(result, "paragraphs", None) or [])


def _para_box(para) -> tuple[int, float, float]:
    regions = getattr(para, "bounding_regions", None) or []
    page = 1
    y0 = 0.0
    y1 = 0.0
    if regions:
        page = int(getattr(regions[0], "page_number", None) or 1)
        poly = list(getattr(regions[0], "polygon", None) or [])
        ys = [float(y) for y in poly[1::2]]
        if ys:
            y0, y1 = min(ys), max(ys)
    return page, y0, y1


def _same_title_keep_document(azure: str, other: str) -> bool:
    """True when Azure is a wrapped-line prefix or a symbol-poorer copy of other."""
    az = normalize_title_text(azure)
    piece = polish_title(other)
    if not az or not title_usable(piece):
        return False
    if piece.lower().startswith(az.lower()) and len(piece) >= len(az) + 12:
        return True
    az_letters = re.sub(r"[^a-z]", "", az.lower())
    other_letters = re.sub(r"[^a-z]", "", piece.lower())
    common = 0
    for left, right in zip(az_letters, other_letters):
        if left != right:
            break
        common += 1
    if common < 40:
        return False
    extra = sum(1 for ch in piece if ord(ch) > 127)
    az_extra = sum(1 for ch in az if ord(ch) > 127)
    return extra > az_extra


def title_from_azure_paragraphs(paragraphs) -> str:
    """Join page-1 Azure title lines, including a same-size wrapped continuation."""
    from sentence_reading.pdf.section_flow import norm_role

    rows: list[tuple[str, str, float, float]] = []
    for para in paragraphs:
        page, y0, y1 = _para_box(para)
        if page not in {0, 1}:
            continue
        role = norm_role(getattr(para, "role", None))
        piece = strip_si_banner(str(getattr(para, "content", None) or ""))
        if not piece or is_title_chrome(piece) or looks_like_author_dump(piece):
            continue
        rows.append((role, piece, y0, y1 - y0))
    parts = [piece for role, piece, _, _ in rows if role in {"title", "documenttitle"}]
    if not parts:
        return ""
    title_rows = [(y0, height) for role, _, y0, height in rows if role in {"title", "documenttitle"}]
    last_y0, last_h = title_rows[-1]
    last_bottom = last_y0 + last_h
    for role, piece, y0, height in rows:
        if role != "sectionheading" or y0 < last_bottom - 0.05:
            continue
        if last_h and abs(height - last_h) > max(0.04, last_h * 0.25):
            continue
        if y0 - last_bottom > 1.2:
            continue
        if not title_usable(piece):
            continue
        parts.append(piece)
        break
    joined = polish_title(" ".join(parts))
    return joined if title_usable(joined) else ""


def pick_session_title(
    *,
    info_title: str = "",
    filename: str = "",
    text: str = "",
    sentences: list | None = None,
    title_guess: str = "",
    styled_title: str = "",
    azure_title: str = "",
) -> tuple[str, str]:
    """Paper title for session.title. Azure title role beats metadata chrome."""
    azure_piece = polish_title(azure_title)
    head = head_title_text(text)
    if title_usable(azure_piece):
        for candidate, source in (
            (styled_title, "styled"),
            (head, "head"),
            (info_title, "info"),
        ):
            if _same_title_keep_document(azure_piece, candidate):
                return polish_title(candidate), source
    for candidate, source in (
        (azure_piece, "azure"),
        (info_title, "info"),
        (styled_title, "styled"),
        (head, "head"),
        (title_guess, "title_guess"),
    ):
        piece = polish_title(candidate)
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

    Card token is absent | kept | replaced | skipped_unusable. Never returns
    paper text.

    WHY skipped_unusable: an unusable picked title (a publisher file id such as
    `1-s2.0-S...-mmc1`) means the card is never compared, so front matter chrome
    survives in it. Reporting that as `kept` claimed the card already matched.
    """
    from sentence_reading.models import Sentence

    picked = re.sub(r"\s+", " ", (picked_title or "").strip())
    has_title = any(
        str(getattr(row, "section", "") or "") == "title" for row in sentences or []
    )
    if not title_usable(picked):
        return list(sentences or []), (
            "skipped_unusable" if has_title else "absent"
        )
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
