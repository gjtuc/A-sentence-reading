# 51 — 되새김질 이어 보기 (한 박스)

모듈: `static/app.js` · `styles.css` · 받침 [17](17-rumination-revisions.md)

## 무엇을

섹션 경계 되새김질에서, 문장별 **조각 카드** 대신  
그 구간 최신 노트 본문을 **하나의 큰 텍스트 박스에 등장 순으로 이어 붙여** 보여 준다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 연속 flow 박스 · 문장 세그먼트 | 헤더 `⋯` · Guide |
| 번역 digest 상단 유지 (40) | |
| ▶ 목소리 → **0.2.60** 이어 듣기 ([52](52-section-review-voice-seq.md)) | |
| 콕 수정 → **0.2.63** ([55](55-section-review-flow-edit.md)) | |
| 키보드 → **0.2.64** ([56](56-section-review-keys.md)) | |
| 흰 십자 → **0.2.65** ([57](57-section-review-crosshair.md)) | |
| 빈 노트는 flow에서 생략 | |

## UX

- 힌트: “아래는 이 구간 기록을 이어서 본 것입니다…”
- `(아직 기록 없음)` 카드 나열 없음 → 전부 비면 한 줄 안내만
- 「계속 읽기」 유지

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- AI 채점
- append-only 스키마 변경 (표시만)

## 불변

- 문장↔그림 인덱스 독립 — 목소리 재생은 인덱스 불변
- 리뷰가 인덱스를 바꾸는 것은 **사용자가 문장을 고른 경우만** (콕 수정은 인덱스 불변 · [55](55-section-review-flow-edit.md))

## 버전

웹 **0.2.59** · status `section_review_flow: true`

## Version pin

Web/mobile **0.3.3** (invite redeem E2E · access session clear — see [67-access-gate.md](67-access-gate.md)).
