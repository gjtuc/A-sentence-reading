# 02 — PDF extract

모듈: `pdf/extract.py`  
의존: PyMuPDF (`fitz`) — M2/M3에서 `pyproject.toml`에 추가.

## 입력·출력

```
extract_text(pdf_path) -> str
extract_text_by_page(pdf_path) -> list[str]
join_page_texts(pages) -> str
render_page_png(pdf_path, page_index, dpi=150, max_side_px=1600) -> bytes
extract_figures(pdf_path, out_dir) -> list[Figure]
```

- `out_dir`: `data/extracted/{session_id}/figures/`
- 그림 파일명: `{id}.png` (통일 PNG)

## 텍스트 (§M2)

### 알고리즘 (1차)

1. `doc = fitz.open(pdf_path)`
2. 페이지 순서대로 `page.get_text("text")` (페이지별 리스트 또는 `\n\n` join)
3. 연속 공백 정리: 줄바꿈이 hyphenation(`-\n`)이면 연결, 그 외 `\n` → 공백
4. 반환 문자열 / 페이지 리스트

### 다단 (two-column)

1. 블록 bbox 로 좌·우 군집 → 좌열 위→아래 후 우열 ([31-reading-order.md](31-reading-order.md)).
2. 다단 페이지는 vision OCR 후보에 **강제 합류** (순서 재확인).
3. 로컬 Layout ML 없음.

### 실패

| 상황 | 동작 |
|------|------|
| 암호 PDF | `encrypted_pdf` 에러, ingest 실패 |
| 텍스트 길이 &lt; 50 (alnum) | 규칙 게이트 → `full_vision` (Gemini 키 있을 때) |
| 열기 실패 | `invalid_pdf` |

### OCR / vision

스캔·손상 페이지: **적응형 Gemini vision** — [14-vision-ocr-router.md](14-vision-ocr-router.md).  
Tesseract 로컬 OCR은 쓰지 않음.

## 그림 (§M3)

### 페이지 클립 래스터 (캡션 포함 PNG)

임베디드 추출 후 **표시용**은 그림+캡션(또는 표+캡션) 영역을 `page.get_pixmap` 으로 자른다.

| 상수 | 값 | 의미 |
|------|-----|------|
| `_FIGURE_CLIP_ZOOM` | **8.0** (0.2.41 · 이전 2.0) | 같은 clip을 더 촘촘히 찍음 (~576 dpi). **잘리는 범위는 불변** |
| `_FIGURE_CLIP_MAX_SIDE_PX` | 6400 | 전면 그림 8× 시 긴 변 상한 (OOM). 영역은 유지·해상도만 캡 |

`pipeline_version` → **`rich-v11` (0.3.41 · caption word-join · [127](127-caption-word-join.md); 이전 rich-v10 · [126](126-soft-caption-labels.md))** (0.3.6 · caption-number figure order · [92](92-figure-caption-order.md); 이전 rich-v7 compound off).

### 전략: caption-first (design/125) + embedded attach

캡션(Fig/Scheme/Table + 번호; 구두점 또는 제목형 이어짐 · [126](126-soft-caption-labels.md))을 먼저 모은 뒤 근처 임베드에 붙인다. 임베드가 없으면 캡션 위 페이지 클립(벡터/드로잉).

### (이전) embedded images

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

**0.2.52+ 비활성** ([44-compound-off.md](44-compound-off.md)). extract 는 통짜만.  
모듈·설명은 [29-compound-figures.md](29-compound-figures.md). `pipeline_version` → **rich-v7**.

## 성능·한도

- 페이지 > 80 → warning `long_document`, 그래도 처리
- 파일 > 50MB → ingest 거부 ([10](10-security-limits.md))
- 추출 타임아웃: 120s (서버에서) → `extract_timeout`

## 테스트 픽스처 (권장)

`tests/fixtures/pdfs/` (git에 작은 합성 PDF만; 큰 논문은 로컬 only):

- `tiny_text_only.pdf` — 문장 3개, 그림 0
- `tiny_with_image.pdf` — 임베디드 PNG 1개

생성 스크립트는 M2에서 `scripts/make_fixtures.py`로.
