# 23 — Google · 카카오 · 이메일 · 계정 연결

모듈: `auth_accounts.py` · `auth_kakao.py` · `auth_google.py` · `/api/auth/*` · 로그인 다이얼로그

## 무엇을

로그인 수단은 여러 개, **창고(GCS `users/{uid}`)** 는 하나.  
같은 사람이 Google·카카오·이메일을 **계정 연결**로 묶을 수 있다.

## 모델

- 내부/창고 `uid` (Google 첫 로그인은 subject 재사용 — 0.2.18 호환)
- `data/auth/accounts.json` (+ GCS `{prefix}/auth/accounts.json`)
  - `users[uid].providers = { google, kakao, email }`
  - `by_provider["google:…"] = uid`

## 환경

| var | 의미 |
|-----|------|
| `ASR_GOOGLE_CLIENT_ID` | Google GIS |
| `ASR_KAKAO_REST_API_KEY` | 카카오 REST 키 |
| `ASR_KAKAO_CLIENT_SECRET` | (선택) 카카오 client secret |
| `ASR_EMAIL_AUTH` | 기본 `1` · `0` 이면 이메일 off |
| `ASR_AUTH_SECRET` | 세션·OAuth state 서명 |

카카오 Redirect URI 예: `http://127.0.0.1:8770/api/auth/kakao/callback`

## API

| | |
|--|--|
| `POST /api/auth/google` | login · `mode=link` |
| `GET /api/auth/kakao/start?mode=` | login \| link → 카카오 |
| `GET /api/auth/kakao/callback` | 코드 교환 → 쿠키 |
| `POST /api/auth/email/register\|login\|link` | 이메일 |
| `POST /api/auth/unlink` | `{ provider }` (마지막 수단 불가) |

## UI

헤더 **로그인** → 카카오 / 구글 / 이메일 스택.  
로그인 후 **계정** → 연결·해제.

## 버전

0.2.19
