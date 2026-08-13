# 133 — Logout session isolation (shared device / browser)

Modules: Flutter `app.dart` · `library_controller` · web `app.js`  
받침: [22](22-google-auth-gcs.md) · [67](67-access-gate.md) · [83](83-login-required-gate.md) · [84](84-access-waiting-ux.md) · [132](132-ingest-cancel.md)

## 무엇인가

로그아웃(또는 계정 전환) 후에도 **이전 유저의 보관함·열린 세션·업로드 draft**가 남을 수 있다.  
AccessWaiting만 떠 있으면 `LibraryScreen`이 트리에 없어 `clearAll()`이 안 돌고, 웹은 `papers[]`를 비우지 않는다.  
공유 기기/브라우저에서 A → 로그아웃 → B 로 바뀌면 **남의 목록·이어올리기**가 보일 수 있다.

| 포함 | 미포함 |
|------|--------|
| 앱 루트에서 로그아웃·uid 전환 시 `clearAll` | 서버 ingest cancel 자동 호출 |
| 웹 `logoutAuth` 시 papers/tabs/reader wipe | 표지→그림 #1 · hang 3분 업로드 연결 |
| status `logout_session_isolation` | `_SESSIONS` owner 바인딩 전면 |
| **0.3.49** | 132 기기 취소 탭 E2E |

## Product (locked)

1. 로그아웃 = **로컬 discard만** (목록·세션·draft·웹 탭). 진행 중 job 서버 cancel은 **이 칩에 넣지 않음** (132 API는 유지·수동).
2. 웹 = 로그아웃 시 **페이지 안에서** 논문 탭/리더 상태 비움 (리로드에만 기대하지 않음).
3. uid가 A→B로 바뀌면 로그아웃 없이도 이전 유저 로컬 상태 wipe.

## Kill / rollback

Revert PR · 이전 APK. status 플래그는 관측용(클라 동작은 항상 wipe).

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.49**

## Device / E2E pin

- Live `/api/status`: `version=0.3.49` · `logout_session_isolation=true`
- APK `0.3.49` · SM-G986N: 로그인 A → (가능하면) 목록 확인 → 로그아웃아웃 → 목록/세션 비움 · 재로그인 전 draft 이어올리기 없음
- Web Live: 논문 연 뒤 로그아웃아웃 → 탭/본문 비움 · 이전 제목 잔존 없음
- Cross-user: 로컬 wipe 후 B 로그인 시 A 목록이 화면에 남지 않음

Do not paste session cookies or secrets into docs.
