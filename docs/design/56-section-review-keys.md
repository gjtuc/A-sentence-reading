# 56 — 되새김질 키보드 (문장 박스 감각)

모듈: `static/app.js` · `styles.css` · 받침 [17](17-rumination-revisions.md) · [51](51-section-review-flow.md) · [55](55-section-review-flow-edit.md)

## 무엇을

되새김질 시트가 열려 있을 때, 문장 박스와 **비슷한 키 감각**으로  
구간을 이동·수정·닫기 한다. 읽기 인덱스(`sentence_index` / `figure_index`)는 바꾸지 않는다.

| 키 | 동작 |
|----|------|
| `←` / `→` | flow 세그먼트 포커스 이동 |
| `Enter` / `Space` | 포커스 세그먼트 편집 (없으면 「계속 읽기」) |
| `Esc` | 편집 중이면 취소 · 아니면 시트 닫기 |
| `Tab` | 세그먼트·계속 읽기 순환 (논문 탭 전환 안 함) |
| `F` · `1–9` · `↑`/`↓` | 시트 열려 있는 동안 차단 (인덱스 보호) |

| 포함 | 미포함 (후속) |
|------|----------------|
| `handleSectionReviewKeys` · `is-flow-focus` | 헤더 `⋯` · Guide |
| Esc 2단 (취소 → 닫기) | 헤더 `⋯` · Guide |
| 열릴 때 첫 세그먼트 포커스 | |

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 노트 오버레이 키 동작 변경
- append 스키마 변경

## 불변

- 되새김질 키는 문장/그림 인덱스를 변경하지 않음
- `advanceSentence` 는 시트 열림 시 이미 early-return

## 버전

웹 **0.2.64** · status `section_review_keys: true`
