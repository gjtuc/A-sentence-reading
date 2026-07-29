# 41 — 본문 각주 → References → DOI/Crossref 원문

모듈: `cite_refs.py` · `llm` Crossref 조회 · UI 칩·패널  
받침: [28](28-fig-ref-jump.md) (그림 점프와 같은 “힌트만” UX)

## 무엇을

본문 문장에 `[12]` 같은 **문헌 각주**가 있으면:

1. 해당 **References 항목**을 문장 옆/아래 패널에 보여 준다.
2. **원문 열기** 버튼: 우선 DOI → 없으면 Crossref `query.bibliographic` → 보조로 Google Scholar.
3. (후속) 출판사 홈 검색창은 DOI 실패 시 보조 링크만.

Fig. 칩과 같이 **강제 점프 없음** — 클릭해야만 패널·원문.

## 비목표 (이번)

- Flutter
- Live Enable / IPS (Trading Gate — ASR 밖)
- 출판사별 검색 URL 완벽 매핑
- 본문 `(Author, 2020)` 이름-연도 전체 파서 (MVP는 숫자 각주 위주)
- References를 TTS로 읽기

## 데이터

ingest 시 원문에서 bibliography 추출 → `PaperSession.references`:

```json
[{ "n": 12, "text": "B. Liu, … ChemElectroChem 2018, 5, 785.", "doi": "" }]
```

문장 텍스트의 `[12]`, `[1-3]`, `<sup>12</sup>`(숫자만)와 `n` 매칭.

## API

| Method | Path | |
|--------|------|--|
| POST | `/api/cite/resolve` | `{ text }` → `{ ok, url, doi?, source }` |

`source`: `doi_in_text` | `crossref` | `scholar_fallback`

## UI

- `#citeRefHints` — `[12]` 칩 (문장 인덱스 불변)
- `#citeRefPanel` — 문헌 전문 + **원문 열기**
- debone: **문장 안에 붙은** `[n]` 은 유지. 단독 각주 줄·References 목록은 계속 제거(목록은 별도 추출).

## 불변

- INVARIANT: 칩/패널은 `sentence_index`·`figure_index`를 바꾸지 않음
- INVARIANT: AI 채점 없음
- INVARIANT: TTS는 영문 본문

## 버전

0.2.49
