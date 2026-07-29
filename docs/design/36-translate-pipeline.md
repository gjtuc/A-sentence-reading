# 36 — 영→한 다단계 번역 (초안 → 감수 → 윤문)

모듈: `llm/translate.py` (pipeline) · `POST /api/translate` · prefs `mode`  
받침: [35-translate-simple.md](35-translate-simple.md)

## 무엇을

「번역」이 켜져 있으면 기본으로 **3단계** Gemini 호출 후 최종 한국어만 문장 아래에 보여 준다.

| 단계 | 역할 | 입력 |
|------|------|------|
| `draft` | 초안 번역 | 영어 원문 |
| `sense` | 학술·용어·기호 감수 | 영어 + draft |
| `polish` | 읽기 쉬운 윤문 | 영어 + sense |

UI는 **최종 `ko`만** 표시 (중간 단계 펼침 UI는 이번 비목표).

## 비목표 (이번)

- 중간 초안을 UI에 펼쳐 보기
- 용어집 DB·사용자 사전
- 한→영 · 다른 언어
- AI 채점·점수
- Live Enable / IPS (Trading Gate — ASR 밖)
- TTS에 번역문 섞기
- STT · Flutter

## Prefs

`asr.translate.v1` / `asr.translate.v1.{uid}`:

```json
{ "enabled": false, "mode": "pipeline" }
```

| `mode` | 동작 |
|--------|------|
| `pipeline` (기본) | draft → sense → polish |
| `simple` | 0.2.43 단일 호출 (호환·절약) |

헤더 토글은 계속 **on/off만**. `mode`는 API·prefs로 전달 (UI에 모드 선택기는 이번 생략 — 기본 pipeline).

## API

`POST /api/translate`  
Body: `{ "text": "<plain english>", "mode": "pipeline" | "simple" }`  
`mode` 생략 시 **`pipeline`**.

성공:

```json
{
  "ok": true,
  "ko": "...",
  "source_lang": "en",
  "target_lang": "ko",
  "mode": "pipeline",
  "cached": false,
  "stages_done": ["draft", "sense", "polish"]
}
```

실패(호출 전): `empty` · `too_long` · `gemini_unavailable` · `invalid_text` · `invalid_mode`

**Fail-soft:** pipeline 중 후속 단계가 비거나 예외면 **직전 단계 `ko`로 성공 반환**하고 `stages_done`에 성공한 단계만 넣는다. 초안조차 실패하면 `translate_failed`.

캐시 키: `simple:` / `pipeline:v1:` + sha256(plain) — 모드 혼선 방지.

## UI

- 기존 「번역」·`.sentence-ko` 유지
- 요청 시 `mode: "pipeline"` (prefs)
- 로딩 문구: 「번역 중…」(단계 나열 안 함 — 지연만 조금 김)

## 불변

- INVARIANT: 번역 on/off는 읽기 인덱스를 바꾸지 않음 (기본 off)
- INVARIANT: AI 채점 없음
- INVARIANT: 단순 경로(`mode=simple`)는 35와 동일 계약 유지

## 버전

0.2.44
