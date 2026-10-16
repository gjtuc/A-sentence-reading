# 407 — The web app logs in with Google and Kakao (step 2b of the web version)

## Problem

The live server has no SMTP settings (`email_smtp_configured: false`), so the email
link of design/405 answers "이메일 발송 설정이 없어 링크를 보낼 수 없습니다". Google and
Kakao work on the phone, but only through a Custom Tab that ends in an Android deep
link (`com.gjtuc.sentence-reading://...`). A browser cannot follow that link.

## What changed

- **Same tab, back to /app/.** On the web, the Google and Kakao buttons send the page
  itself to the provider (`launchUrl(..., webOnlyWindowName: '_self')`). No Custom Tab,
  no native Google sign-in. When the provider is done, the browser lands on
  `/app/?auth=logged_in` with the `asr_session` cookie, and bootstrap reads it through
  `/api/auth/status` as in design/405.
- **Google.** `/api/auth/google/mobile/start?land=app` renders the same GIS page. With
  `land=app` it posts `mobile: '0'` (no session token in the JSON; the response sets the
  cookie) and goes to `/app/?auth=logged_in` (or `linked`) instead of the deep link.
- **Kakao.** `/api/auth/kakao/start?land=app` puts `ld: 1` into the signed OAuth state.
  The callback sends web results to `/app/?auth=...` and web errors to
  `/app/?auth_error=...`; without it the old `/` targets stay. `land` takes only `app`.
- **Phone unchanged.** Off the web, `googleMobileStartUrl` / `kakaoStartUrl` (with
  `mobile=1`) and the deep links are as before.
- **Tests on the web branch.** `AuthController.debugForceWebLogin` drives the web branch
  on the VM. `click\03_web_build.bat` now runs `mobile/test/web_*_test.dart` before it
  builds, through the memory light.

## Email

Email links still need `ASR_SMTP_HOST` and `ASR_SMTP_FROM` (plus credentials) on Cloud
Run. That is a settings change, not code.

## Tests

`tests/test_design_407_web_oauth_land.py`, `mobile/test/web_oauth_same_tab_test.dart`
