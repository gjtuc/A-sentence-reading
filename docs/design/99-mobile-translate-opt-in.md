# 99 — Mobile translate opt-in (Settings gate)

Modules: Settings toggle · `TranslateController` · ingest/open `?translate=` · reader KO display  
받침: 쉐도잉 옵트인 패턴 [79](79-shadowing-opt-in.md) · ingest-only 번역 [42](42-translate-ingest-only.md) · 표시 토글 [35](35-translate-simple.md)

## 무엇인가

모바일 **설정**에서 번역(영→한 사전 계산)을 켜고 끈다.

| 설정 | 문서 생성(ingest) | 보관본 열기(open) | 읽기 UI |
|------|-------------------|-------------------|---------|
| **OFF** (기본) | Gemini 번역 스킵 | 백필 스킵 | KO 숨김 |
| **ON** | 번역 실행 | KO 없으면 백필 | KO 표시 |

웹은 query **생략 시 기존처럼 번역**(호환). 앱만 명시 `translate=0|1`.

## 비목표

- 웹 Guide 표시 토글(`asr.translate.v1`)을 서버 게이트로 바꾸기 (후속)
- 서버 킬스위치 (번역은 Gemini 가용 시 기존과 동일)
- Live Enable / IPS

## API

| 경로 | query |
|------|-------|
| `POST /api/ingest` · `…/complete` | `translate=0` → 스킵 · `=1` → 실행 · **없음 → 실행(웹)** |
| `POST /api/cache/papers/{id}/open` | 동일 |

Job meta: `want_translate` (ingest 백그라운드).

## Mobile

- prefs `asr.translate.v1.{uid}` · 기본 **OFF** · 로그아웃 시 clear
- Settings SwitchListTile「번역 사용」
- ingest/open에 플래그 전달
- ON으로 바꾼 뒤 열린 문서가 있으면 재-open → 백필

## Version

**0.3.13** · status + pubspec

## Device / pytest

- unit: prefs parse · settings 문자열 · `?translate=0` 스킵 경로
- 실기: OFF 업로드 → KO 없음 · ON 후 같은 문서 열기 → 번역 진행

Do not paste emails, cookies, or tokens into chat/PR.
