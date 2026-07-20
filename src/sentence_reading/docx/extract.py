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


def _normalize_caption(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:900]


def _png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


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


def _paragraph_image_blobs(paragraph, document) -> list[tuple[bytes, str]]:
    """문단 안 인라인 이미지 → (bytes, mime)."""
    from docx.oxml.ns import qn

    out: list[tuple[bytes, str]] = []
    # WHY: findall+ns 는 환경에 따라 비어 있음 — iter 로 blip 탐색
    for el in paragraph._element.iter():
        if not str(el.tag).endswith("}blip"):
            continue
        r_embed = el.get(qn("r:embed")) or el.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        )
        if not r_embed:
            continue
        try:
            rel = document.part.rels[r_embed]
            part = rel.target_part
        except (KeyError, AttributeError):
            continue
        blob = getattr(part, "blob", None)
        if not blob or len(blob) < _MIN_BYTES:
            continue
        content_type = getattr(part, "content_type", None)
        mime, _ext = _mime_for_image(blob, content_type)
        if not mime:
            continue
        converted = _to_browser_image(blob, mime)
        if not converted:
            continue
        out.append(converted)
    return out


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
            plain = _table_plain(block)
            if plain.strip():
                parts.append(plain)
    text = "\n\n".join(parts).strip()
    if not text:
        # 헤더/푸터만 있는 경우 등 — 전체 문단 폴백
        text = "\n\n".join(
            _paragraph_text(p) for p in doc.paragraphs if _paragraph_text(p)
        ).strip()
    return text


def extract_figures(path: Path) -> list[Figure]:
    """
    임베디드 이미지 + (직후) Fig/Scheme 캡션.
    Table 캡션이 있는 표는 SVG 요약으로 캐러셀에 넣음.
    캡션 없는 이미지는 PDF와 같이 제외.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    figures: list[Figure] = []
    pending_images: list[tuple[bytes, str]] = []
    pending_table_caption = ""
    fig_i = 0

    def flush_images_without_caption() -> None:
        nonlocal pending_images
        pending_images = []

    def emit_image(blob: bytes, mime: str, caption: str) -> None:
        nonlocal fig_i
        fig_i += 1
        if mime == "image/png":
            src = _png_data_url(blob)
        else:
            src = f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")
        figures.append(
            Figure(
                id=f"fig-{fig_i:04d}",
                image_src=src,
                caption=caption,
                page_index=None,
            )
        )

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            imgs = _paragraph_image_blobs(block, doc)

            if pending_images and text and _FIG_CAPTION_START.match(text):
                cap = _normalize_caption(text)
                for blob, mime in pending_images:
                    emit_image(blob, mime, cap)
                pending_images = []
                continue

            if pending_images and text:
                # 캡션이 아닌 본문이 오면 캡션 없는 이미지 폐기
                flush_images_without_caption()

            if text and _TABLE_CAPTION_START.match(text):
                pending_table_caption = _normalize_caption(text)
            elif text and not imgs:
                pending_table_caption = ""

            if imgs:
                # 같은 문단에 캡션 텍스트가 같이 있는 경우
                if text and _FIG_CAPTION_START.match(text):
                    cap = _normalize_caption(text)
                    for blob, mime in imgs:
                        emit_image(blob, mime, cap)
                else:
                    pending_images.extend(imgs)

        elif isinstance(block, Table):
            if pending_images:
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

    # 문서 끝 — 캡션 없는 pending 폐기
    flush_images_without_caption()
    return figures[:200]
