# 52 — 되새김질 목소리 이어 듣기

모듈: `static/app.js` · `styles.css` · 받침 [17](17-rumination-revisions.md) · [51](51-section-review-flow.md)

## 무엇을

섹션 되새김질에서, 문장별 **▶ 1 · ▶ 2** 나열 대신  
그 구간 최신 목소리를 **등장 순으로 한 번에 이어 재생**한다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 「▶ 이어 듣기」 / 「■ 중지 (i/n)」 | flow 안 **콕 집어 수정** |
| 없는·빈 blob 건너뛰기 | 텍스트 박스와 동일 키 조작 · 흰 십자 |
| 리뷰 닫기·재클릭 시 시퀀스 중단 | 헤더 `⋯` · 가이드 |
| `sentence_index` 불변 | AI 채점 |

## UX

- 목소리 바: 라벨「목소리」+ 단일 시퀀스 버튼
- 재생 중 토글 → 중지 후 「▶ 이어 듣기」복귀
- 힌트: “▶ 이어 듣기로 목소리를 순서대로 재생합니다…”

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- append-only 노트/voice 스키마 변경 (재생만)
- TTS(엔진) 시퀀스와 혼용 — 사용자 목소리 IndexedDB/GCS만

## 불변

- 문장↔그림 인덱스 독립 — 이어 듣기도 인덱스 불변 (`stopPropagation`)
- `stopVoicePlayback({ keepSequence })` — 클립 전환 시에만 큐 유지

## 버전

웹 **0.2.60** · status `section_review_voice_seq: true`
