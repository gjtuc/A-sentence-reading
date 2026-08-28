# 153 — Google bulk 번역 + 선택 Gemini 후처리

모듈: `llm/translate_google.py` · `llm/translate.py` · `llm/translate_section.py` · env  
받침: [35](35-translate-simple.md) · [36](36-translate-pipeline.md) · [40](40-ingest-section-translate.md)

## 무엇인가

ingest·API 번역의 **1차 bulk**를 **Google Cloud Translation API**로 수행하고,  
품질·섹션 통일은 **선택적 Gemini 후처리**만 남긴다.

| 단계 | 엔진 | 기본 |
|------|------|------|
| 문장/캡션 1차 번역 | Google Translate v3 batch | ON (`ASR_TRANSLATE_BACKEND=google`) |
| sense / polish (API pipeline) | Gemini | `ASR_TRANSLATE_GEMINI_POST=1` |
| 섹션 digest + harmonize (ingest) | Gemini | `ASR_TRANSLATE_GEMINI_POST=1` |

`text_ko_stage`: `google` · `harmonize` · (legacy) `polish` 등 — `google`도 최종 단계.

## 환경변수

| 변수 | 기본 | 의미 |
|------|------|------|
| `ASR_TRANSLATE_BACKEND` | `google` | `google` \| `gemini`(legacy 전부 Gemini) |
| `ASR_TRANSLATE_GEMINI_POST` | `1` | Google 1차 후 digest/harmonize·sense/polish |
| `GOOGLE_CLOUD_PROJECT` | (ADC) | Translation parent project |

자격: TTS와 동일 — `GOOGLE_APPLICATION_CREDENTIALS` 또는 Cloud Run ADC.

## ingest 흐름 (google backend)

1. 섹션 문장 **batch** Google Translate (최대 128/요청)
2. (post ON) 섹션 digest — Gemini
3. (post ON) 문장별 harmonize — Gemini
4. 캡션 batch Google → (post ON) harmonize

Gemini·Google 둘 다 없으면 `translate_skipped_no_backend`.  
Google만 있고 post OFF면 `translate_post_skipped_no_gemini` 경고 후 Google 결과만 저장.

## API

`POST /api/translate` — `translate_available()` 게이트 (Google 또는 Gemini).  
`simple`: Google 1회. `pipeline`: Google + (post ON) sense/polish.

`/api/status`: `translate_backend` · `translate_google` · `translate_gemini_post`.

## 비목표

- 용어집(glossary) — 후속
- Flutter 설정 UI (서버 env만)
- Live Enable / IPS

## 불변

- INVARIANT: 읽기 인덱스·TTS 영문 유지
- INVARIANT: live 읽기 중 `/api/translate` 폴백 없음 (design/42)

## Version

**0.3.78**

Do not paste emails, cookies, or tokens into chat/PR.
