# 49 — 각주 표시 정리 (문장 박스 · 전체화면 칩)

모듈: `cite_refs` · `static/app.js` · `styles.css` · 받침 [41](41-cite-ref-open.md)

## 무엇을

1. **문장 텍스트 박스** — 본문에서 `[n]` / `<sup>n</sup>` 각주 마커를 **표시하지 않음**.  
   칩·패널·원문 열기는 원문 문장으로 계속 파싱 (위치는 한 문장 UI에서 중요하지 않음).
2. **전체화면 문장 확대** — 마우스가 문장 패널 **밖**이면 각주 칩·패널도 Fig 칩처럼 숨김.  
   hover 시에만 Fig·각주 칩이 같이 보임.

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 되새김질 · 헤더 `⋯` · 한글 줄바꿈 (후속 UX)
- References TTS

## 불변

- 문장↔그림 인덱스 독립
- 칩은 힌트만 · 강제 점프 없음
- 캐시/세션 원문 `text` 는 각주 유지 (표시 층만 strip)

## 버전

웹 **0.2.57** · status `cite_display_clean: true`
