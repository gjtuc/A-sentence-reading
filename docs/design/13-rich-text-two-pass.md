# 13 — 전역 훑기 + 첨자·위첨자·이탤릭 (rich text)

모듈: `llm/debone.py` · `llm/richtext.py` · UI `static/app.js`  
관련: [12-gemini-debone.md](12-gemini-debone.md) · PDF/DOCX extract는 **평문 유지** (레이아웃 첨자 정보는 없음).

## 배경

추출 텍스트는 `BaZr0.9Y0.1O3-δ`, `cm-1`처럼 **첨자·위첨자가 풀린 평문**이다.  
Gemini도 그 평문만 받는다. 다만 도메인 지식 + **논문 전역 맥락**이 있으면 복원·섹션 분류가 쉬워진다.

## 사용자가 정한 범위

| 항목 | 결정 |
|------|------|
| 복원 대상 | 아래첨자 · 위첨자 · 이탤릭(기호·변수) **모두** |
| 비용·시간 | 무시 가능 (등록 1회 비용) |
| 입력 | PDF · DOCX **동일** 파이프라인 (둘 다 extract → debone) |
| 순서 | 이 문서 설계 → **즉시 구현** |

## Q2 쉬운 설명 — “화면에 어떻게 그리나”

깨진 `H2O`를 고친 뒤, 앱이 글자를 **어떻게 저장·표시할지**다.

| 방식 | 예 | 장단 |
|------|-----|------|
| **유니코드만** | `H₂O`, `cm⁻¹` | 저장은 단순. 이탤릭·복잡한 식은 거의 못 함 |
| **작은 HTML** | `H<sub>2</sub>O`, `cm<sup>−1</sup>`, `<i>σ</i>` | 첨자·위첨자·이탤릭을 **한 체계**로 처리. UI는 허용 태그만 그림 |

**결정(권장·채택):** 문장 `text`에 **허용 태그만 있는 HTML 조각**을 저장한다.  
허용: `<sub>` `<sup>` `<i>` `<em>` (속성 없음). 서버에서 sanitize 후 저장·전송.  
평문 폴백(키 없음·debone 실패)은 기존처럼 태그 없는 문자열.

## Q3 쉬운 설명 — “1차 전역 / 2차 청크”

| 패스 | 하는 일 | 왜 |
|------|---------|-----|
| **1차 survey** | 논문 평문(가능하면 전체)을 **한 번** 훑어 요약 JSON | 섹션 지도 + “이 논문에서 쓰는 화학식·기호” 목록 |
| **2차 debone** | 지금처럼 청크마다 문장 청소·분류 | 각 청크에 1차 요약을 **같이 넣어** 맥락 유지 |

전체를 **한 번에** 문장까지 다 뽑지는 않는다 (긴 논문·누락 위험).  
“먼저 지도 만들기 → 지도 들고 구역별로 청소”가 목표다.

### 1차 JSON (계약)

```json
{
  "title_guess": "…",
  "section_order": ["title", "abstract", "introduction", "methods", "results", "discussion", "conclusion"],
  "section_notes": "Short map: where each section starts; odd headings.",
  "formulas": [
    {"raw": "BaZr0.9Y0.1O3-δ", "rich": "BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3−δ</sub>"}
  ],
  "symbols": [
    {"raw": "sigma", "rich": "<i>σ</i>", "note": "conductivity"}
  ]
}
```

입력이 매우 길면 모델 한도 안에서 전달 (우선 전체; 필요 시 head+목차성 샘플로 축소 — 구현 상수로 관리).

### 2차 청크 (기존 + 확장)

- 시스템/유저 프롬프트에 **PAPER CONTEXT** (1차 JSON 요약) 주입.
- 각 문장 `text`는 **rich HTML 조각** (의미는 유지, 가시만 제거).
- `formulas`/`symbols`에 있으면 **그 표기를 우선** 일관 적용.
- 섹션 태그는 기존과 동일.

## 진행률 (ingest job)

| 단계 | percent 대략 | message 예 |
|------|----------------|------------|
| extract | ~5–20 | 파일 읽는 중 |
| survey | ~22–28 | 논문 훑는 중 |
| debone chunks | ~28–92 | 다듬는 중 k/n |
| save | ~95 | 거의 끝 |

`on_progress(done, total)` 에서 survey를 1단위로 포함: `total = chunk_count + 1`.

## 보안

- Gemini 출력도 **신뢰하지 않음**.
- `richtext.sanitize_sentence_html(s)`: 허용 태그 외 제거, 속성·스크립트 불가.
- 길이·태그 비율 이상 시 태그를 벗긴 평문으로 폴백.

## UI

- `#sentenceText`: `textContent` → **sanitize된 HTML**을 `innerHTML` (서버 sanitize 전제; 클라에서 한 번 더 strip 가능).
- CSS: `sub`/`sup` 크기·baseline, `i`/`em` 이탤릭.
- 탭 제목·`document.title`용 문자열은 **태그 제거한 plain**.

## 캐시

- 새 ingest만 rich text. 옛 캐시 plain은 그대로 표시 가능 (태그 없으면 동일).
- 캐시 키/해시 변경 없음 (파일 bytes 기준). 재등록 시 새 파이프라인 적용.

## 실패

| 상황 | 동작 |
|------|------|
| survey 실패 | 빈 context로 2차만 진행 + warning `survey_failed` |
| 2차가 첨자 HTML 생략 | **용어집 강제 치환** (`typography.apply_glossary`)으로 보정 |
| 2차 일부 실패 | 기존 partial_debone |
| 키 없음 | split 폴백, plain |
| 옛 캐시 (`pipeline_version` ≠ `rich-v2`) | 캐시 무시하고 다시 다듬음 |

## 과학 기호 정규화 (`normalize_scientific_glyphs`)

PDF ToUnicode lookalike → 표준 문자 (HTML `<sup>` 대신 **올바른 유니코드**):

| 깨진 예 | 교정 |
|---------|------|
| `◦C` `∘C` `˚C` `ºC` | `°C` |
| `90◦` `0.02◦` (각도) | `90°` `0.02°` |
| soft hyphen (`\u00ad`) | 제거 |
| `μM`/`µM` 혼용 (단위) | `µM` (MICRO SIGN) |
| `+/-` | `±` |
| `2 x 10` (숫자 사이) | `2 × 10` |

문장·**그림 캡션** 모두 적용.  
더 위험한 예(검색): `µ`→`m`으로 잘못 매핑되어 **µM이 mM이 됨** ([poppler-science](https://github.com/lanl/poppler-science)) — 자동 복원은 오탐 위험 커 survey/Gemini에 의존.

## 합격 기준

1. 제목/본문에 `BaZr…O3-δ`류가 **아래첨자로 보임** (대표 화학식 논문).
2. `cm-1` / `10-3` 류가 **위첨자로 보임** (해당 문맥).
3. 변수·그리스 문자가 **이탤릭**으로 보임 (과도한 문장 전체 이탤릭 없음).
4. PDF·DOCX ingest 모두 동일 rich 경로.
5. XSS: `<script>` 등이 문장에 남아 UI에 실행되지 않음.
