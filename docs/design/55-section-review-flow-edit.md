# 55 — 되새김질 flow 콕 집어 수정

모듈: `static/app.js` · `styles.css` · 받침 [17](17-rumination-revisions.md) · [51](51-section-review-flow.md)

## 무엇을

이어 보기 박스에서 **한 문장 메모 구간만** 클릭해 인라인 수정하고,  
`appendTextRevision`으로 그 문장 노트에 저장한다.  
문장 화면으로 나가지 않아도 된다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 세그먼트 클릭 · textarea · 저장/취소 | 흰 십자 커서 |
| 닫기 시 편집 중이면 저장 | 문장 박스와 동일 키 조작 전체 |
| `sentence_index` 불변 | 헤더 `⋯` · Guide |
| 빈 세그먼트는 저장 후 flow에서 생략 | |

## UX

1. flow에 문장별 블록 (구분·hover)
2. 클릭/Enter → 그 블록만 편집
3. 저장 → append-only · flow 다시 그림
4. 다른 블록 클릭 → 이전 것 저장 후 새 블록 편집

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 스키마 변경 (기존 notes_revisions)
- 자동으로 그 문장으로 점프 (명시적 “문장으로”는 후속 가능)

## 불변

- 편집은 인덱스 불변 (`stopPropagation`)
- 동일 본문 저장은 no-op

## 버전

웹 **0.2.63** · status `section_review_flow_edit: true`
