# 15 — Cloud TTS + layout gesture trim

모듈: `llm/tts.py` · `api/app.py` (`/api/tts`, `/api/tts/voices`) · `static/app.js`  
자격: `GOOGLE_APPLICATION_CREDENTIALS` → 서비스 계정 JSON (`gc_automation.env`)

## 제품 결정

- 문장 클릭 → 현재 문장만 Cloud Text-to-Speech (화면 하이라이트 없음)
- API는 `spoken_text_for_tts` 로 정규화 후 합성 — `<sub>`/`<sup>` 풀어 읽기, `Title:` 접두·기호 발음화 ([tts_speak.py](../src/sentence_reading/llm/tts_speak.py))
- 다시 클릭 → **처음부터 다시**
- `←/→` 문장 이동 · 탭 전환 시 재생 중지
- 헤더 **TTS** → 목소리 · 속도 (`localStorage` `asr.tts.v1`)

## 제거한 상호작용

- 스플리터/스트립 **드래그로 접기·펴기**
- 문장 박스 클릭으로 **확대/접기**
- 그림 클릭의 **중간 78% 단계** (기본 ↔ 전체화면만; 크롭용)

## 유지

- 그림 **전체화면** (`↓` 또는 그림 클릭) + **드래그 크롭**
- `Shift+←/→` 그림, `F` 브라우저 전체화면

## API

| Method | Path | 동작 |
|--------|------|------|
| GET | `/api/tts/voices` | 추천 보이스 · rate 범위 |
| POST | `/api/tts` | `{ text, voice?, speaking_rate? }` → `audio/mpeg` |

`GET /api/status` → `tts: true|false`
