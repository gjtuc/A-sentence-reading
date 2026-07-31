# 60 — 패널 단축키 안내 줄 (기본 숨김)

모듈: `static/index.html` · `styles.css` · `app.js` · Guide dialog ([59](59-guide-header.md))

## 무엇을

문장·그림 패널 아래 **항상 보이던** `.hint` 긴 단축키 줄을 **기본 숨김**.  
안내는 **Guide**가 담당하고, Guide 안 체크「화면에도 단축키 안내 줄 보이기」로만 다시 켠다.

| 기본 | 옵션 on |
|------|---------|
| `sentenceHint` / `figureHint` `hidden` | 패널 아래 기존 문구 표시 |
| Guide에 단축키 목록 | 동일 + 화면에도 줄 |

| 포함 | 미포함 |
|------|--------|
| `panel-chrome-hint` · `showPanelHints` pref | 노트/되새김/veil hint 변경 |
| Guide 체크박스 | 단축키 **동작** 변경 |
| 구 `asr.guide.v1` (nestInMore만) 호환 | Live Enable / IPS |

## Pref (`asr.guide.v1`)

```json
{ "nestInMore": false, "showPanelHints": false }
```

EDGE: 손상 JSON · 키 없음 · 구형 `{nestInMore}`만 → `showPanelHints: false`  
EDGE: 구형 boolean → nestInMore만 반영 · hints 숨김

## UX

- 첫 방문: 화면이 덜 붐빔 · Guide로 안내
- 원하면 Guide에서 체크 → 즉시 줄 표시 · 저장
- Fig./각주 **칩** (`fig-ref-hints` 등)은 그대로 (단축키 크롬과 별개)

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 문장·그림 인덱스 변경
- 단축키 바인딩 변경

## 버전

웹 **0.2.77** · status `panel_hints_optional: true`
