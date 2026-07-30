# 57 — 되새김질 흰 십자

모듈: `static/styles.css` · 받침 [17](17-rumination-revisions.md) · [56](56-section-review-keys.md)  
표시만 · `app.js`는 힌트 문구·`body.is-section-review` 토글(기존) 사용

## 무엇을

되새김질 시트 위에서 **흰 십자 커서**(노트 시트와 동일 SVG)를 쓰고,  
키보드로 고른 세그먼트에는 **흰 + 마커**를 붙여 “지금 여기”를 보이게 한다.

| 포함 | 미포함 (후속) |
|------|----------------|
| `body.is-section-review` 시트 흰 십자 | 헤더 `⋯` 정리 |
| FS에서도 검정 십자보다 되새김질 규칙 우선 | Guide 위치 |
| 편집 textarea = 흰 I · 버튼 = pointer | |
| `.is-flow-focus::before` 흰 + | |

## UX

- 마우스를 시트 위에 올리면 흰 십자
- `←`/`→` 로 고른 구간에 작은 흰 +
- 편집 중에는 + 숨김 · textarea는 흰 I-beam

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- `sentence_index` / store 변경
- 커서 SVG 자산 파일을 따로 두기 (기존 data-URL 패턴 유지)

## 불변

- 표시만 — 인덱스·노트 append 경로 불변
- `openSectionReview` / `closeSectionReview` 의 `is-section-review` 클래스에 의존

## 버전

웹 **0.2.65** · status `section_review_crosshair: true`
