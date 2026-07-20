# 02 — PDF extract

모듈: `pdf/extract.py`  
의존: PyMuPDF (`fitz`) — M2/M3에서 `pyproject.toml`에 추가.

## 입력·출력

```
extract_text(pdf_path) -> str
extract_figures(pdf_path, out_dir) -> list[Figure]
```

- `out_dir`: `data/extracted/{session_id}/figures/`
- 그림 파일명: `{id}.png` (통일 PNG)

## 텍스트 (§M2)

### 알고리즘 (1차)

1. `doc = fitz.open(pdf_path)`
2. 페이지 순서대로 `page.get_text("text")` 연결, 페이지 사이에 `\n\n`
3. 연속 공백 정리: 줄바꿈이 hyphenation(`-\n`)이면 연결, 그 외 `\n` → 공백
4. 반환 문자열

### 다단 (two-column)

1차는 **무시** (단순 get_text).  
`warnings`에 `reading_order_unverified` 추가.  
개선은 M5 이후 (`blocks` + x좌표 정렬 실험).

### 실패

| 상황 | 동작 |
|------|------|
| 암호 PDF | `encrypted_pdf` 에러, ingest 실패 |
| 텍스트 길이 < 50 | `warnings: sparse_text` — 스캔본 가능, 문장 0이어도 세션 생성 가능 |
| 열기 실패 | `invalid_pdf` |

OCR: **1차 범위 밖.**

## 그림 (§M3)

### 1차 전략: embedded images

페이지마다 `page.get_images(full=True)`:

1. xref로 추출 → PNG로 저장
2. 너무 작은 것 필터:
   - `min(width, height) < 40` px → drop (`tiny_image`)
   - `byte_size < 2_000` → drop
3. 너무 큰 것: 긴 변 > 2400px 이면 긴 변 1600으로 리사이즈 후 저장
4. 동일 xref 중복이면 한 번만

### caption

- **그림:** 이미지 bbox **아래 ~110pt** 안 `Fig`/`Figure`/`Scheme` 시작 블록.
- **표:** `page.find_tables()` 로 표 bbox를 잡고, **위 ~90pt** 안 `Table N` 캡션과 합쳐 페이지 클립 PNG로 캐러셀에 넣는다.

(Gemini가 아니라 **PDF 좌표**로 짝 맞춤.)

매칭 실패 시 그림은 `caption=""`, 표는 `Table (p.N)` 플레이스홀더.

### raster fallback (1차 안 함)

embedded가 0개이고 텍스트는 있을 때 — “페이지를 그림으로” 넣는 기능은 **M5 이후**.  
1차는 figures=[] + warning `no_embedded_figures`.

### compound figures

`Fig 1a/1b` 분해 **안 함.** 통짜 한 장으로 둔다. warning 없음(정상).

## 성능·한도

- 페이지 > 80 → warning `long_document`, 그래도 처리
- 파일 > 50MB → ingest 거부 ([10](10-security-limits.md))
- 추출 타임아웃: 120s (서버에서) → `extract_timeout`

## 테스트 픽스처 (권장)

`tests/fixtures/pdfs/` (git에 작은 합성 PDF만; 큰 논문은 로컬 only):

- `tiny_text_only.pdf` — 문장 3개, 그림 0
- `tiny_with_image.pdf` — 임베디드 PNG 1개

생성 스크립트는 M2에서 `scripts/make_fixtures.py`로.
