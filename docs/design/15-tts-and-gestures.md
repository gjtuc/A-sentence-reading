# 15 — Cloud TTS + layout gesture trim

모듈: `llm/tts.py` · `api/app.py` (`/api/tts`, `/api/tts/voices`) · `static/app.js`  
자격: `GOOGLE_APPLICATION_CREDENTIALS` → 서비스 계정 JSON (`gc_automation.env`)

## 제품 정의

- 문장 클릭 → 현재 문장만 Cloud Text-to-Speech (화면 하이라이트 없음)
- API는 `spoken_text_for_tts` 로 정규화 후 합성 — `<sub>`/`<sup>` 풀어 읽기, `Title:` 접두·기호 발음화, **원소 기호→이름** (`Ni`→nickel) ([tts_speak.py](../src/sentence_reading/llm/tts_speak.py))
- 다시 클릭 → **처음부터 다시**
- `←/→` 문장 이동 · 탭 전환 시 재생 중지
- 헤더 **TTS** → 모드 · 목소리 · 속도 (`localStorage` `asr.tts.v2`)

## 랜덤 모드 (익숙도 + 속도)

고정 모드가 아니면 재생마다 **속도 대역**과 **locale 가중**으로 보이스를 고른다.

| 모드 | 속도 대역 | locale 가중 (대략) |
|------|-----------|-------------------|
| `random_normal` | 0.7–1.3 | en-US 0.8 · en-GB 0.2 |
| `random_hard` | 1.0–1.6 | en-US 0.4 · en-GB 0.3 · en-AU 0.3 |
| `random_very_hard` | 1.3–1.9 | en-US 0.2 · en-GB 0.2 · en-AU 0.25 · en-IN 0.35 |

- curated 보이스: Neural2만 (`en-US` / `en-GB` / `en-AU` / `en-IN`). locale 고른 뒤 그 locale 안에서는 균등.
- **UI에 배속·가중치·지역 숫자를 노출하지 않는다** (예측하면 난이도가 깎임). 힌트는 “재생마다 목소리와 속도가 바뀝니다.”만.

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
