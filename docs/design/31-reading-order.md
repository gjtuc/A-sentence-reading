# 31 — 다단 reading order

모듈: `pdf/reading_order.py` · `extract_text_by_page` · `vision_ocr.recover_pdf_text`

## 무엇을

2단 PDF에서 **왼쪽 열 위→아래 → 오른쪽 열 위→아래** 순으로 본문을 맞춘다.

| 단계 | |
|------|--|
| 1 | PyMuPDF blocks 기하 재정렬 (무료) |
| 2 | 다단으로 판정된 페이지 → Gemini vision 강제 (읽는 순서 재확인) |

비용 제한 없음 (운영자 결정). 로컬 Layout ML 가중치는 **넣지 않음**.

## 비목표

- Detectron / LayoutParser
- DOCX 다단
- 음절·품사 색 (하지 않음)

## 파이프라인

`rich-v5` → **`rich-v6`** (그림 클립 zoom 8 · 0.2.41)

## 버전

0.2.32
