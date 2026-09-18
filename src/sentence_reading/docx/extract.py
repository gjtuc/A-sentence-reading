"""
무엇을: .docx → 원문 텍스트 + 임베디드 그림(+캡션).
왜: supplementary 가 Word 인 경우가 많아 PDF와 같은 읽기 흐름을 맞춘다.
한계: 레이아웃 좌표가 없어 Fig 캡션은 ‘이미지 직후 문단’ 휴리스틱.
     옛 .doc 은 미지원 (docx 로 저장 필요).
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from sentence_reading.models import Figure

_MIN_BYTES = 200
# WHY: SI 는 Fig. S1 / Table S1 형식인 경우가 많음
_FIG_CAPTION_START = re.compile(
    r"^\s*((?:Fig(?:ure)?|Scheme)\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)
_TABLE_CAPTION_START = re.compile(
    r"^\s*(Table\.?\s*S?\d+[a-z]?)\b",
    re.IGNORECASE,
)
_SI_BANNER = re.compile(
    r"^(?:supporting information|supplementary information(?:\s+for)?|"
    r"supplementary materials?|references?)\.?$",
    re.IGNORECASE,
)
_SI_CONTACT = re.compile(
    r"^(?:corresponding authors?|e-?mail|email)\b",
    re.IGNORECASE,
)


def drop_si_banners(parts: list[str]) -> list[str]:
    """Drop SI title/contact lines. Keep figure captions and body prose."""
    cleaned = [(raw, re.sub(r"\s+", " ", raw or "").strip()) for raw in parts]
    cleaned = [(raw, text) for raw, text in cleaned if text]
    has_banner = any(_SI_BANNER.match(text) or _SI_CONTACT.match(text) for _raw, text in cleaned)
    out: list[str] = []
    seen_body = False
    for raw, text in cleaned:
        if _SI_BANNER.match(text) or _SI_CONTACT.match(text):
            continue
        if _is_si_body(text):
            seen_body = True
        elif not seen_body and has_banner and _looks_like_author_line(text):
            continue
        out.append(raw)
    return out


def _is_si_body(text: str) -> bool:
    if _FIG_CAPTION_START.match(text) or _TABLE_CAPTION_START.match(text):
        return True
    return len(text) > 60 and bool(re.search(r"[.!?]$", text))


def _looks_like_author_line(text: str) -> bool:
    if len(text) > 220 or _FIG_CAPTION_START.match(text) or _TABLE_CAPTION_START.match(text):
        return False
    if re.search(r"[.!?]\s+[A-Z]", text):
        return False
    words = re.findall(r"[A-Za-z]{4,}", text)
    return bool(re.search(r"\d", text)) and len(words) <= 12


def _normalize_caption(text: str) -> str:
    """design/131 — same ceiling as pdf.extract (full caption; no ellipsis)."""
    from sentence_reading.pdf.extract import _normalize_caption as _pdf_norm

    return _pdf_norm(text)


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


_CAPTION_STUB = re.compile(
    r"^(?:Fig(?:ure)?|Scheme|Table)\.?\s*S?\d+[a-z]?\.?$",
    re.IGNORECASE,
)


def _is_caption_paragraph(text: str) -> bool:
    piece = re.sub(r"\s+", " ", text or "").strip()
    return bool(_FIG_CAPTION_START.match(piece) or _TABLE_CAPTION_START.match(piece))


def _is_caption_stub(text: str) -> bool:
    return bool(_CAPTION_STUB.match(re.sub(r"\s+", " ", text or "").strip()))


def drop_caption_paragraphs(parts: list[str]) -> list[str]:
    """Caption lines belong under the figure, not in the practice text.

    A lone 'Fig. S1.' takes the next paragraph with it. A mention such as
    'as shown in Fig. S1.' does not start a caption and stays.
    """
    cleaned = [(raw, re.sub(r"\s+", " ", raw or "").strip()) for raw in parts]
    cleaned = [(raw, text) for raw, text in cleaned if text]
    out: list[str] = []
    i = 0
    while i < len(cleaned):
        raw, text = cleaned[i]
        if _is_caption_paragraph(text):
            i += 1
            if (
                _is_caption_stub(text)
                and i < len(cleaned)
                and not _is_caption_paragraph(cleaned[i][1])
            ):
                i += 1
            continue
        out.append(raw)
        i += 1
    return out


def _mime_for_image(blob: bytes, content_type: str | None) -> tuple[str, str]:
    ct = (content_type or "").lower()
    if "png" in ct or blob.startswith(b"\x89PNG"):
        return "image/png", "png"
    if "jpeg" in ct or "jpg" in ct or blob[:2] == b"\xff\xd8":
        return "image/jpeg", "jpg"
    if "gif" in ct or blob.startswith(b"GIF8"):
        return "image/gif", "gif"
    if "webp" in ct or blob[:4] == b"RIFF":
        return "image/webp", "webp"
    if (
        "tiff" in ct
        or "tif" in ct
        or blob[:4] in (b"II*\x00", b"MM\x00*")
    ):
        return "image/tiff", "tiff"
    if "emf" in ct or "wmf" in ct:
        return "", ""  # 래스터 아님 — 스킵
    return "", ""


def _to_browser_image(blob: bytes, mime: str) -> tuple[bytes, str] | None:
    """
    브라우저 <img> 용으로 맞춤. TIFF 등은 PNG 로 변환.
    """
    if mime in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        return blob, mime
    if mime == "image/tiff":
        try:
            from io import BytesIO

            from PIL import Image

            im = Image.open(BytesIO(blob))
            im.load()
            # WHY: 투명 배경 + 검정 글씨 → 다크 UI에서 안 보임. 흰 바탕에 합성
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            out = BytesIO()
            im.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
        except Exception:
            return None
    return None


def _iter_block_items(document):
    """본문 순서대로 paragraph / table."""
    from docx.document import Document as DocumentClass
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parent = document
    if not isinstance(document, DocumentClass):
        return
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _paragraph_text(paragraph) -> str:
    return re.sub(r"\s+", " ", (paragraph.text or "").strip())


_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _image_rel_id(el) -> str | None:
    """DrawingML a:blip uses r:embed; Word VML v:imagedata uses r:id."""
    from docx.oxml.ns import qn

    tag = str(el.tag).rsplit("}", 1)[-1]
    if tag == "blip":
        return el.get(qn("r:embed")) or el.get(_REL_NS + "embed")
    if tag == "imagedata":
        return el.get(qn("r:id")) or el.get(_REL_NS + "id")
    return None


def _blob_from_rel(document, rel_id: str) -> tuple[bytes, str] | None:
    try:
        rel = document.part.rels[rel_id]
        part = rel.target_part
    except (KeyError, AttributeError):
        return None
    blob = getattr(part, "blob", None)
    if not blob or len(blob) < _MIN_BYTES:
        return None
    mime, _ext = _mime_for_image(blob, getattr(part, "content_type", None))
    if not mime:
        return None
    return _to_browser_image(blob, mime)


def _paragraph_image_blobs(paragraph, document) -> list[tuple[bytes, str]]:
    """문단 안 인라인 이미지 → (bytes, mime). Blip and VML imagedata."""
    out: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    for el in paragraph._element.iter():
        rel_id = _image_rel_id(el)
        if not rel_id or rel_id in seen:
            continue
        seen.add(rel_id)
        converted = _blob_from_rel(document, rel_id)
        if converted:
            out.append(converted)
    return out


def table_is_grid(table) -> bool:
    """design/327 — a cell grid is not prose.

    `extract_text` used to append every table's cell text, so a 49-row table
    arrived as one practice `sentence` of pipe-separated numbers while the same
    table was also rendered into its own slot PNG. The reader met the table
    twice: once as a picture, once as an unspeakable blob.

    A one-column or one-row table is often just a text box holding a paragraph,
    so that still counts as prose. Two or more columns *and* two or more rows is
    a grid and belongs to the slot only.
    """
    try:
        rows = table.rows
        if len(rows) < 2:
            return False
        cols = max((len(r.cells) for r in rows), default=0)
        return cols >= 2
    except Exception:  # noqa: BLE001
        return False


def _table_plain(table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [re.sub(r"\s+", " ", (c.text or "").strip()) for c in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _table_as_png_data_url(caption: str, plain: str) -> str:
    """
    Word 표를 흰 바탕 PNG 로.
    WHY: SVG data-URL 은 #색상 인코딩이 깨져 흰 배경에서 글자가 안 보임.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    lines = (plain or "").splitlines()[:45]
    cap = (caption or "").strip()
    width = 1100
    pad_x = 28
    line_h = 22
    cap_h = 28
    # caption wrap estimate
    cap_lines = max(1, (len(cap) + 94) // 95) if cap else 0
    height = max(140, 24 + cap_lines * cap_h + 12 + line_h * max(len(lines), 1) + 28)

    im = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    try:
        font_cap = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17)
        font_body = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)
    except OSError:
        font_cap = ImageFont.load_default()
        font_body = font_cap

    y = 18
    if cap:
        max_chars = 95
        for i in range(0, len(cap), max_chars):
            part = cap[i : i + max_chars]
            draw.text((pad_x, y), part, fill=(20, 20, 20), font=font_cap)
            y += cap_h
            if i // max_chars >= 2:
                break
        y += 8

    for line in lines:
        text = line if len(line) <= 120 else line[:117] + "…"
        draw.text((pad_x, y), text, fill=(25, 25, 25), font=font_body)
        y += line_h

    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return _png_data_url(buf.getvalue())


def _open_raster(blob: bytes):
    from io import BytesIO

    from PIL import Image

    try:
        im = Image.open(BytesIO(blob))
        im.load()
        return im.convert("RGB")
    except (OSError, ValueError):
        return None


def _wrap_caption(text: str, width: int, font, draw) -> list[str]:
    words = re.sub(r"\s+", " ", text or "").strip().split(" ")
    if not words or words == [""]:
        return []
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = word if not cur else f"{cur} {word}"
        if draw.textlength(trial, font=font) <= width and len(trial) < 180:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
    if cur:
        lines.append(cur)
    return lines[:8]


def compose_panel_png(
    rows: list[list[tuple[bytes, str]]],
    caption: str,
    *,
    caption_above: bool = False,
) -> bytes:
    """One figure: same-paragraph images in a row, rows stacked, caption outside."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    gap = 10
    max_w = 1400
    opened_rows: list[list] = []
    for row in rows:
        opened = [im for blob, _mime in row if (im := _open_raster(blob)) is not None]
        if opened:
            opened_rows.append(opened)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()

    row_images: list = []
    for opened in opened_rows:
        target_h = min(max(im.height for im in opened), 720)
        scaled = []
        for im in opened:
            if im.height <= 0:
                continue
            w = max(1, int(im.width * target_h / im.height))
            scaled.append(im.resize((w, target_h), Image.Resampling.LANCZOS))
        if not scaled:
            continue
        total_w = sum(im.width for im in scaled) + gap * (len(scaled) - 1)
        if total_w > max_w:
            scale = max_w / total_w
            scaled = [
                im.resize(
                    (max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                for im in scaled
            ]
            total_w = sum(im.width for im in scaled) + gap * (len(scaled) - 1)
        row_h = max(im.height for im in scaled)
        row_im = Image.new("RGB", (max(total_w, 1), row_h), (255, 255, 255))
        x = 0
        for im in scaled:
            row_im.paste(im, (x, (row_h - im.height) // 2))
            x += im.width + gap
        row_images.append(row_im)

    body_w = max((im.width for im in row_images), default=1100)
    body_h = (
        sum(im.height for im in row_images) + gap * max(len(row_images) - 1, 0)
        if row_images
        else 0
    )
    probe = ImageDraw.Draw(Image.new("RGB", (max(body_w, 8), 8)))
    cap_lines = _wrap_caption(caption, max(body_w - 36, 200), font, probe)
    cap_h = (16 + 28 * len(cap_lines)) if cap_lines else 0
    canvas_h = body_h + cap_h
    if canvas_h < 8:
        canvas_h = cap_h or 8
    canvas = Image.new("RGB", (max(body_w, 8), canvas_h), (255, 255, 255))
    body_y = cap_h if caption_above else 0
    y = body_y
    for im in row_images:
        canvas.paste(im, (0, y))
        y += im.height + gap
    if cap_lines:
        draw = ImageDraw.Draw(canvas)
        text_y = 8 if caption_above else body_h + 8
        for line in cap_lines:
            draw.text((18, text_y), line, fill=(20, 20, 20), font=font)
            text_y += 28
    buf = BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def extract_text(path: Path) -> str:
    """문단·표를 문서 순으로 이어 붙인 원문."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    parts: list[str] = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            t = _paragraph_text(block)
            if t:
                parts.append(t)
        elif isinstance(block, Table):
            # design/327 — a grid goes to its slot PNG, never to the sentences.
            if table_is_grid(block):
                continue
            plain = _table_plain(block)
            if plain.strip():
                parts.append(plain)
    had_parts = bool(parts)
    parts = drop_caption_paragraphs(drop_si_banners(parts))
    text = "\n\n".join(parts).strip()
    if not text and not had_parts:
        # 필터가 본문을 비운 뒤에는 원문 문단을 다시 붙이지 않는다.
        text = "\n\n".join(
            _paragraph_text(p) for p in doc.paragraphs if _paragraph_text(p)
        ).strip()
    return text


def figure_source_census(path: Path) -> dict[str, int]:
    """design/294 — why extract_figures returned empty (counts only).

    Word SI often stores rasters as VML v:imagedata, not DrawingML a:blip.
    extract_figures reads both. vml_unseen_n is imagedata whose relationship
    did not resolve to a raster (still missed), not the raw imagedata count.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    blip_n = 0
    imagedata_n = 0
    caption_n = 0
    unresolved_vml = 0
    for el in doc.element.body.iter():
        tag = str(el.tag).rsplit("}", 1)[-1]
        if tag == "blip":
            blip_n += 1
        elif tag == "imagedata":
            imagedata_n += 1
            rid = _image_rel_id(el)
            if not rid or _blob_from_rel(doc, rid) is None:
                unresolved_vml += 1
    grid_n = 0
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            if text and (
                _FIG_CAPTION_START.match(text) or _TABLE_CAPTION_START.match(text)
            ):
                caption_n += 1
        elif isinstance(block, Table):
            # design/327 — grids kept out of the sentence stream. Counted so the
            # skip is visible rather than a silent drop (design/321).
            if table_is_grid(block):
                grid_n += 1
    return {
        "blip_n": blip_n,
        "imagedata_n": imagedata_n,
        "caption_n": caption_n,
        "vml_unseen_n": unresolved_vml,
        "table_grid_n": grid_n,
    }


def stamp_docx_slot_keys(figures: list[Figure], *, supplementary: bool) -> list[Figure]:
    """Caption Fig. S1 / Table S1 → fig:s1 / table:s1. Empty slot stays empty."""
    from sentence_reading.fig_refs import caption_key
    from sentence_reading.pdf.slot_plan import slot_key_from_caption_key

    out: list[Figure] = []
    for fig in figures:
        if (fig.slot_key or "").strip():
            out.append(fig)
            continue
        ckey = caption_key(fig.caption or "")
        sk = (
            slot_key_from_caption_key(ckey, supplementary=supplementary)
            if ckey
            else None
        )
        if not sk:
            out.append(fig)
            continue
        out.append(
            Figure(
                id=fig.id,
                image_src=fig.image_src,
                caption=fig.caption,
                page_index=fig.page_index,
                caption_ko=fig.caption_ko,
                caption_ko_stage=fig.caption_ko_stage,
                slot_key=sk,
            )
        )
    return out


def extract_figures(path: Path, *, doc_role: str = "main") -> list[Figure]:
    """
    임베디드 이미지 (DrawingML blip + VML imagedata) + (직후) Fig/Scheme 캡션.
    Table 캡션이 있는 표는 SVG 요약으로 캐러셀에 넣음.
    캡션 없는 이미지는 PDF와 같이 제외.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    figures: list[Figure] = []
    pending_rows: list[list[tuple[bytes, str]]] = []
    pending_table_caption = ""
    fig_i = 0
    blocks = list(_iter_block_items(doc))

    def flush_images_without_caption() -> None:
        nonlocal pending_rows
        pending_rows = []

    def emit_group(rows: list[list[tuple[bytes, str]]], caption: str) -> None:
        nonlocal fig_i
        if not rows:
            return
        fig_i += 1
        png = compose_panel_png(rows, caption, caption_above=False)
        figures.append(
            Figure(
                id=f"fig-{fig_i:04d}",
                image_src=_png_data_url(png),
                caption=caption,
                page_index=None,
            )
        )

    def caption_with_stub_body(index: int, text: str) -> tuple[str, int]:
        cap = _normalize_caption(text)
        if not _is_caption_stub(text):
            return cap, index
        j = index + 1
        while j < len(blocks) and isinstance(blocks[j], Paragraph):
            nxt = _paragraph_text(blocks[j])
            if not nxt:
                j += 1
                continue
            if _paragraph_image_blobs(blocks[j], doc) or _is_caption_paragraph(nxt):
                break
            piece = re.sub(r"\s+", " ", nxt).strip()
            return _normalize_caption(f"{text.rstrip()} {piece}"), j
        return cap, index

    i = 0
    while i < len(blocks):
        block = blocks[i]
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            imgs = _paragraph_image_blobs(block, doc)

            if pending_rows and text and _FIG_CAPTION_START.match(text):
                cap, i = caption_with_stub_body(i, text)
                emit_group(pending_rows, cap)
                pending_rows = []
                i += 1
                continue

            if pending_rows and text:
                flush_images_without_caption()

            if text and _TABLE_CAPTION_START.match(text):
                pending_table_caption, i = caption_with_stub_body(i, text)
            elif text and not imgs:
                pending_table_caption = ""

            if imgs:
                if text and _FIG_CAPTION_START.match(text):
                    cap, i = caption_with_stub_body(i, text)
                    emit_group([imgs], cap)
                else:
                    pending_rows.append(imgs)
        elif isinstance(block, Table):
            if pending_rows:
                flush_images_without_caption()
            plain = _table_plain(block)
            if pending_table_caption and plain.strip():
                fig_i += 1
                figures.append(
                    Figure(
                        id=f"fig-{fig_i:04d}",
                        image_src=_table_as_png_data_url(pending_table_caption, plain),
                        caption=pending_table_caption,
                        page_index=None,
                    )
                )
            pending_table_caption = ""
        i += 1

    flush_images_without_caption()
    supplementary = (doc_role or "").strip().lower() in ("supplementary", "si", "supp")
    return stamp_docx_slot_keys(figures[:200], supplementary=supplementary)
