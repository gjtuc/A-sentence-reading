# 53 — 되새김질 on/off (옵션)

모듈: `static/app.js` · `index.html` · `styles.css` · 받침 [17](17-rumination-revisions.md)

## 무엇을

섹션 경계에서 자동으로 뜨는 **되새김질**을 사용자가 끌 수 있게 한다.  
원하지 않는 사람은 구간이 바뀌어도 리뷰 시트 없이 읽기만 계속한다.

| 포함 | 미포함 (후속) |
|------|----------------|
| 헤더「되새김」토글 · `aria-pressed` | 일시정지 후 그 문장만 재듣기/재녹음 |
| localStorage `asr.sectionReview.v1` (±uid) | flow 안 콕 텍스트 수정 |
| off 시 자동 오픈 차단 · `openSectionReview` no-op | 헤더 `⋯` 정리 · Guide |
| off 시 열린 시트 즉시 닫기 | |

## UX

- **기본 켜짐** — 기존 사용자 흐름 유지 (번역 기본 꺼짐과 반대)
- 켜짐: 앞으로 문장 이동으로 섹션이 바뀔 때 직전 구간 되새김질
- 꺼짐: 같은 경계에서도 시트 없음 · 노트/TTS 경로는 평소처럼
- 버튼 title로 현재 상태 안내

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 서버 prefs 동기화 (클라이언트 localStorage만)
- append-only 노트 스키마 변경

## 불변

- prefs는 `sentence_index` / `figure_index`를 바꾸지 않음
- off여도 노트·voice 데이터는 유지 (표시·자동 오픈만 끔)

## 버전

웹 **0.2.61** · status `section_review_optional: true`
