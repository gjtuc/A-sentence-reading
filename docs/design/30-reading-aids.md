# 30 — 읽기 보조: 음절 · (품사 색은 다음)

모듈: `reading_aids.py` · `POST /api/reading/aids` · 헤더 「음절」토글

## 무엇을 (이번 턴)

영문 문장 표시에 Immersive Reader식 **음절 경계 `·`** 를 넣는다.

| | |
|--|--|
| 켜짐 | `examination` → `ex·am·i·na·tion` (표시만) |
| TTS | **원문** 유지 — 점으로 읽지 않음 |
| rich HTML | `<sub>` 등 태그는 유지 · 텍스트 노드만 분할 |
| 저장 | `localStorage` `asr.readingAids.v1` `{ syllables: bool }` |

## 비목표 (다음 턴+)

- 품사 색 (명사/동사 …)
- Azure Immersive SDK
- 단어 단위 TTS 하이라이트 (제품 비목표와 동일)

## 엔진

`pyphen` + `en_US` 사전. 실패·짧은 단어는 그대로.

## API

`POST /api/reading/aids`  
`{ "text": "<html or plain>", "syllables": true }` → `{ ok, text }`

## UI

헤더 **음절** 토글 (TTS 옆). 문장 확대 FS에서도 동일.

## 버전

0.2.30
