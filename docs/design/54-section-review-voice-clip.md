# 54 — 되새김질 일시 정지 → 이 문장만 다시 듣기/재녹음

모듈: `static/app.js` · `styles.css` · 받침 [17](17-rumination-revisions.md) · [52](52-section-review-voice-seq.md)

## 무엇을

이어 듣기 중 **일시 정지**하면, 지금 듣던 문장만 골라  
**다시 듣기** · **다시 녹음**할 수 있게 한다.  
문장 화면으로 나갔다 돌아오지 않아도 된다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 재생 중 클릭 = ⏸ 일시 정지 | flow 안 콕 텍스트 수정 |
| 「이 문장만 듣기」·「이 문장만 녹음」·「끝내기」 | 헤더 `⋯` · Guide |
| 「▶ 계속」으로 시퀀스 재개 | AI 채점 |
| append-only voice · `sentence_index` 불변 | |

## UX

1. ▶ 이어 듣기 → 버튼이 `⏸ 일시정지 (i/n)`
2. 클릭 → 일시 정지 + 클립 액션 표시 · 버튼 `▶ 계속 (i/n)`
3. 이 문장만 듣기 / 녹음 / 끝내기
4. 계속: 같은 위치 재개, 또는 클립만 듣기 끝난 뒤 다음 문장부터

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 노트 스키마 변경 (기존 `appendVoiceRevision`)
- 되새김질 off(53)와 무관 — off면 시트 자체가 안 뜸

## 불변

- 클립 액션은 `stopPropagation` · 인덱스 불변
- 재녹음은 해당 `sentenceId`에만 append

## 버전

웹 **0.2.62** · status `section_review_voice_clip_actions: true`
