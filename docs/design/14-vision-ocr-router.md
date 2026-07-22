# 14 — Vision OCR router (적응형)

모듈: `llm/extract_quality.py` · `llm/vision_ocr.py` · `pdf/extract.py` (`extract_text_by_page`, `render_page_png`)  
관련: [02-pdf-extract.md](02-pdf-extract.md) · [12-gemini-debone.md](12-gemini-debone.md)  
파이프라인: `PIPELINE_VERSION = rich-v3`

## 목표

PyMuPDF `get_text`가 비거나 순서가 틀린 PDF(스캔·심한 다단)에서  
**필요 페이지에만** Gemini vision으로 plain text를 복구한 뒤, 기존 survey/debone으로 넘긴다.

DOCX는 대상 아님 (텍스트 extract → debone 유지).

## 흐름

1. `extract_text_by_page` → 페이지 리스트
2. 제목 캐시 조회 (기존)
3. **규칙 게이트** (`heuristic_gate`)
   - 전체 alnum &lt; 50 → `full_vision`
   - 빈 페이지 비율 ≥ 45% → `full_vision`
   - 그 외 → Gemini **품질맵** (텍스트만, 이미지 없음)
4. 품질맵 verdict
   - `text_ok` → vision 생략
   - `repair_pages` + `bad_pages` → 해당 페이지만 PNG → vision
   - `full_vision` → 전 페이지 (최대 40)
5. 페이지 텍스트 병합 → 기존 `debone_sentences`
6. vision 사용 후 캐시 재조회 (스캔 재오픈 시 제목 히트)

실패 시: 원본 get_text로 debone 계속 + `warnings` (ingest 전체 실패 없음).

## 품질맵 JSON

```json
{
  "verdict": "text_ok" | "repair_pages" | "full_vision",
  "bad_pages": [0, 3],
  "notes": "short reason"
}
```

판정은 **오타율이 아니라** 결손·스캔 냄새·유창하지만 순서 의.  
불확실하면 `text_ok` (과잉 vision 방지).

## Vision OCR

- 렌더: `render_page_png` (기본 150dpi, 긴 변 ≤ 1600px)
- 출력: **plain text만** (HTML 아님 — rich는 debone)
- 한도: 페이지 인덱스 최대 40 (`vision_page_cap`)

## warnings 예

| 코드 | 의미 |
|------|------|
| `vision_ocr_used` | vision 경로 사용 |
| `vision_pages:3,7` | 복구한 0-based 페이지 |
| `vision_failed` / `vision_failed:k/n` | vision 실패 |
| `vision_page_cap` | 40페이지 상한 |
| `quality_map_failed:…` | 품질맵 실패 → text_ok 폴백 |

## 진행률 (ingest)

| stage | percent 대략 |
|-------|----------------|
| extract | 5–10 |
| quality | 12–20 |
| vision | 20–40 |
| figures / debone | 42–92 |
| save | 95 |

## status

`GET /api/status` → `vision_ocr: true|false` (키 존재, debone과 동일 조건).

## 비범위

- Tesseract 로컬 OCR
- DOCX vision
- 다단 ML 전면 재정렬 (의심 페이지만 vision 우회)
