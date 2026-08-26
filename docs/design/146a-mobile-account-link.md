# 146a — Mobile account link/unlink (Settings)

Modules: `settings_screen.dart` · `auth_controller.dart` · `client.dart` · magic-link `intent=link` · design/23  
받침: [23](23-multi-auth-link.md) · [65](65-mobile-oauth.md) · [77](77-email-magic-link.md) · [140](140-mobile-mvp-backlog-split.md)

## 무엇인가

앱 **설정 → 계정**에서 Google · 카카오 · 이메일을 **연결/해제**.  
서버 계약은 design/23 (세션 uid만 신뢰). **창고 논문 병합은 미포함** → [146b](146b-account-warehouse-merge.md) 후보.

| 포함 | 미포함 |
|------|--------|
| Settings 연결/해제 UI · fail-closed | GCS 논문/노트 uid 병합 (146b) |
| Google native `mode=link` | Custom Tab Google link (세션 쿠키 없음) |
| Kakao: 인증 GET으로 Location → Custom Tab | 웹 UI 변경 |
| 이메일: 매직링크 `intent=link` (비번 없음) | 비밀번호 signup/link 부활 |
| pytest + phone E2E | Live Enable / IPS |

## Product (locked)

1. **표시:** 로그인 후에만 · 서버 `providers` 플래그로 버튼 노출  
2. **연결됨:** `user.providers` 목록 · **해제**는 2개 이상일 때만 (마지막 수단 금지)  
3. **Google:** native id_token → `POST /api/auth/google` `mode=link` + 세션 쿠키  
4. **Kakao:** `GET …/kakao/start?mode=link&mobile=1` **with Cookie** → 302 Location → Custom Tab  
5. **Email:** 로그인 세션 + `POST …/magic/request` `{intent:"link"}` → 메일 열면 `link_provider` · 딥링크 세션은 **주 uid**  
6. **충돌 409:** 「이미 다른 사용자에 연결」 — 성공한 척 금지  
7. **병합 없음:** 연결해도 옛 uid 창고는 그대로 (146b)

## Kill / rollback

| Switch | Default | Effect |
|--------|---------|--------|
| `ASR_GOOGLE_CLIENT_ID` | set on Live | empty → Google off |
| `ASR_KAKAO_REST_API_KEY` | set on Live | empty → Kakao off |
| `ASR_EMAIL_AUTH` | `1` | `0` → email off |
| `ASR_EMAIL_MAGIC_LINK` | `1` | `0` → email link request off |
| Revert PR | — | remove Settings link UI |

## Live Enable / IPS

이번 칩에서 불필요함 (auth는 기존 킬스위치만).

## Version

**0.3.63**

## Device / E2E pin

- Live `/api/status` after CD: `version=0.3.63` · `mobile_account_link=true` (post-merge)
- pytest `tests/test_mobile_account_link.py` + full suite 690 passed
- Phone SM-G986N: APK `0.3.63` sideload
- Settings **계정 연결**: Google=연결됨 · 카카오/이메일=연결 안 됨 · 안내 문구(병합 아직 없음)
- **마지막 수단 해제:** `해제` `enabled=false` (Google only) — fail-closed
- **교차 계정:** 다른 Google로 로그인 → 「액세스 승인 대기」(남의 창고/승인 우회 없음) · 주 계정 재로그인 후 Settings 복귀
- Kakao Custom Tab(로그인·연결) adb 자동화로는 미개방(버튼 탭 후 포커스 MainActivity 유지) — 수동 탭 재확인 권장; `followRedirects=false` for link start URL 포함
- Kill: revert PR · provider env kills

Do not paste emails, cookies, tokens, or secrets into chat/PR.
