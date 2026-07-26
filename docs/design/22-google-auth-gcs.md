# 22 — Google 로그인 · UID별 GCS 칸

모듈: `llm/auth_google.py` · `gcs_sync.personal_object_name` · `/api/auth/*` · 헤더 로그인 UI

## 무엇을

Google 계정으로 로그인하면 **같은 UID 칸**의 개인 흔적(노트·목소리·논문 보관)을  
PC·(나중에) 모바일에서 공유한다. UI·루프는 전원 동일.

## 환경

| var | 의미 |
|-----|------|
| `ASR_GOOGLE_CLIENT_ID` | GIS OAuth 클라이언트 ID (있으면 로그인 UI on) |
| `ASR_AUTH_SECRET` | 세션 쿠키 서명 (없으면 개발용 기본값) |
| `ASR_GCS_*` · `GOOGLE_APPLICATION_CREDENTIALS` | 기존과 동일 (서버 SA) |

## 경로

| 종류 | 로그인 시 | 레거시(클라이언트 ID 없음) |
|------|-----------|---------------------------|
| 노트 store | `{prefix}/users/{uid}/notes/store_v2.json` | `{prefix}/notes/store_v2.json` |
| voice blob | `{prefix}/users/{uid}/voice/{sha}.bin` | `{prefix}/voice/…` |
| papers | `{prefix}/users/{uid}/papers/…` | `{prefix}/papers/…` |
| TTS 캐시 | `{prefix}/tts_cache/…` (공유, 유저 칸 밖) | 동일 |

## API

- `GET /api/auth/status` — `auth_enabled` · `client_id` · `user`
- `POST /api/auth/google` `{ credential }` → httpOnly `asr_session` 쿠키
- `POST /api/auth/logout`
- 노트/voice GCS: auth on + 미로그인 → `needs_auth` (로컬 읽기는 계속)

## 로컬 브라우저

- 노트: `asr.notes.v2` → 로그인 시 `asr.notes.v2.u.{uid}`
- 진행: `asr.progress.v1` → `asr.progress.v1.u.{uid}`

## 설정 (1회)

1. Google Cloud Console → OAuth 클라이언트(웹)  
2. 승인된 JavaScript 원본: `http://127.0.0.1:8770` (배포 시 그 origin)  
3. `gc_automation.env` 에 `ASR_GOOGLE_CLIENT_ID=…`  
4. (권장) `ASR_AUTH_SECRET=` 긴 랜덤 문자열  

## 버전

0.2.18
