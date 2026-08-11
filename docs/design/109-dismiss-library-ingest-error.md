# 109 — Dismiss sticky library ingest error

Modules: `library_controller.dart` · `library_screen.dart` · `client.dart`  
받침: [108](108-fail-closed-no-cache.md) · [71](71-mobile-upload-resume.md) · [105](105-upload-fail-notify.md)

## 무엇인가

보관함 상단의 인제스트 실패 문구(짧은 제목 등)가 **닫히지 않고**, 앱을 다시 열면 **초안 reattach로 같은 에러가 재적용**되는 구멍을 막는다.

| 포함 | 미포함 |
|------|--------|
| 에러 배너 닫기 (`dismissError`) | 제목 최소 길이 정책 완화 |
| terminal 실패(422) 시 draft·WM 정리 | mid-stage ingest resume (후속) |
| poll: done+no `cache_id` / ok:false → **422** | Live Enable / IPS |
| 새로고침·새 업로드는 기존처럼 error clear | |

## Product (locked)

1. 실패 문구는 **닫을 수 있어야** 함 (닫기 탭 → 배너 제거)  
2. job이 **이미 terminal**이면 이어받기 초안을 두지 않음 (같은 경고 재출현 금지)  
3. **504** 타임아웃 초안은 유지 (이어올리기)  
4. 알림·로그에 이메일·경로·토큰·제목 전문 금지

## Kill / rollback

- Revert PR

## Version

**0.3.23**

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- Dart: empty `cache_id` / `ok:false` → `AsrApiException` **422**  
- Controller: 422·404·409 → `_drafts.clear` + WM cancel · `dismissError`  
- UI: 에러 옆 닫기  
- 실기: 실패 배너 닫기 → 사라짐 · 앱 재진입 후 같은 문구 재출현 없음

## Resume prefs (후속 칩 메모, 이 칩 범위 밖)

1. UI: 이어받기 시작점 표시 (예: 비전 12/40)  
2. 같은 파일 재선택: 자동 이어받기  
3. 병목 stage: 미확인 (긴 review PDF 대비)

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
