"""Run internal title pick and optional Azure first-page title.

Writes UTF-8 JSON only. Does not print paper text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.pdf.section_flow import norm_role  # noqa: E402
from sentence_reading.title_replay import (  # noqa: E402
    azure_page_title,
    docx_core_title,
    docx_paragraph_text,
    pdf_info_title,
    pdf_styled_title,
    pick_session_title,
)

FOLDERS = (
    Path(r"C:\Users\user\Desktop\새 폴더") / "박사님이 읽으라고 한 논문",
    Path(r"C:\Users\user\Desktop\새 폴더") / "은규 논문",
    Path(r"C:\Users\user\Desktop\새 폴더") / "차완 논문",
    Path(r"C:\Users\user\Desktop\새 폴더") / "차헌 논문",
)


def _paper_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def _page_text(path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        if doc.page_count < 1:
            return ""
        return doc[0].get_text("text") or ""
    finally:
        doc.close()


def _render(path: Path, dest: Path) -> None:
    import pymupdf

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(path)
    try:
        if doc.page_count < 1:
            return
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.15, 1.15), alpha=False)
        pix.save(str(dest))
    finally:
        doc.close()


def azure_title(path: Path) -> tuple[str, str]:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    from sentence_reading.llm.env import (
        azure_document_intelligence_endpoint,
        azure_document_intelligence_key,
    )
    from sentence_reading.pdf.azure_layout import _timeout_s

    endpoint = azure_document_intelligence_endpoint() or ""
    key = azure_document_intelligence_key() or ""
    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    with path.open("rb") as handle:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=handle,
            pages="1",
        )
        result = poller.result(timeout=_timeout_s())
    titles: list[str] = []
    headings: list[str] = []
    for para in getattr(result, "paragraphs", None) or []:
        regions = getattr(para, "bounding_regions", None) or []
        page = 1
        if regions:
            page = int(getattr(regions[0], "page_number", None) or 1)
        if page != 1:
            continue
        role = norm_role(getattr(para, "role", None))
        content = re_space(str(getattr(para, "content", None) or ""))
        if not content:
            continue
        if role in {"title", "documenttitle"}:
            titles.append(content)
        elif role in {"sectionheading"} and len(headings) < 3:
            headings.append(content)
    return re_space(" ".join(titles)), re_space(" | ".join(headings[:2]))


def re_space(text: str) -> str:
    return " ".join((text or "").split())


def one(path: Path, folder: str, out_pages: Path, use_azure: bool) -> dict:
    kind = path.suffix.lower().lstrip(".")
    info = ""
    styled = ""
    head = ""
    azure = ""
    azure_head = ""
    azure_err = ""
    if kind == "pdf":
        info = pdf_info_title(path)
        styled = pdf_styled_title(path)
        head = _page_text(path)
        page_img = out_pages / f"{_paper_id(path)}.jpg"
        try:
            _render(path, page_img)
        except Exception as exc:
            page_img = Path("")
            azure_err = type(exc).__name__
        if use_azure:
            try:
                azure, azure_head = azure_title(path)
            except Exception as exc:
                azure_err = type(exc).__name__
    else:
        info = docx_core_title(path)
        head = docx_paragraph_text(path)
        page_img = Path("")
        if use_azure:
            try:
                azure = azure_page_title(path)
            except Exception as exc:
                azure_err = type(exc).__name__
    picked, source = pick_session_title(
        info_title=info,
        filename=path.name,
        text=head,
        styled_title=styled,
        azure_title=azure,
    )
    return {
        "id": _paper_id(path),
        "folder": folder,
        "name": path.name,
        "kind": kind,
        "internal": picked,
        "source": source,
        "info": info,
        "styled": styled,
        "azure": azure,
        "azure_heading": azure_head,
        "azure_err": azure_err,
        "page": str(page_img) if str(page_img) else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--azure", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rows: list[dict] = []
    pages = args.out.parent / "pages"
    n = 0
    for folder in FOLDERS:
        if not folder.is_dir():
            continue
        files = sorted(
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in {".pdf", ".docx"}
        )
        for path in files:
            if args.limit and n >= args.limit:
                break
            rows.append(one(path, folder.name, pages, args.azure))
            n += 1
            args.out.write_text(
                json.dumps({"n": n, "rows": rows}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"progress {n}", flush=True)
        if args.limit and n >= args.limit:
            break
    print(f"done {n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
