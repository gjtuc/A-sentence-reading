# 35 — 영→한 단순 번역 + 표시 on/off

모듈: `llm/translate.py` · `POST /api/translate` · 헤더 「번역」 · `asr.translate.v1`

## 무엇을

현재 문장을 **영어 → 한국어**로 단순 번역해 문장 아래에 보여 준다.  
표시 여부는 **옵션**(기본 off). 다단계(팀 시뮬)는 **다음 설계**에서 이 API/캐시 위에 올린다.

## 비목표 (이번)

- 다단계 PM/감수/윤문 (후속 · 필수이나 이번 턴 아님)
- 한→영 · 다른 언어
- AI 채점·점수
- Live Enable / IPS (Trading Gate — ASR 밖)
- 번역을 TTS에 섞기 (영문 TTS 유지)

## Prefs (계정별에 가깝게)

| 상태 | 저장 |
|------|------|
| 비로그인 | `localStorage` `asr.translate.v1` → `{ enabled: bool }` |
| 로그인 | `asr.translate.v1.{uid}` — **같은 브라우저에서 계정별** |

(기기 간 서버 prefs는 다단계 턴에서 검토)

기본: `enabled: false`

## API

`POST /api/translate`  
Body: `{ "text": "<plain english>" }`  
성공: `{ ok: true, ko: "...", source_lang: "en", target_lang: "ko" }`  
실패: `empty` · `too_long` (>4000) · `gemini_unavailable` · `translate_failed`

- Gemini Flash · temperature 낮음 · **한 문장만** 번역
- 사용량 계측 (`record_gemini_response`)
- 프로세스 내 텍스트 해시 캐시 (동일 문장 반복 절약)

## UI

- 헤더 **번역** 토글 (`aria-pressed`)
- on이면 문장 아래 `.sentence-ko` 에 한국어 (로딩/오류 메시지)
- 상태 문구(문장 없음 등)는 번역 안 함
- 문장 클릭 TTS는 영문 프레임만 (ko는 프레임 밖 또는 TTS 대상 제외)

## 불변

- INVARIANT: 번역 on/off는 **읽기 루프를 강제하지 않음** (기본 off)
- INVARIANT: AI가 “이해했는지” 채점하지 않음

## 버전

0.2.43
