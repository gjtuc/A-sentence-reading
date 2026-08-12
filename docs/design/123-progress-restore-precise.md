# 123 — Progress restore: precise sentence+figure, fail-closed

Modules: `progress.js` · `app.js` · mobile prefs + `library_controller` · `home_shell`  
받침: [21](21-progress-restore.md) · [63](63-mobile-reader.md) · [121](121-library-open-gcs-first.md)

## 무엇인가

읽기 위치를 **문장+그림** 모두 정확히 저장·복원한다.  
모바일도 uid 스코프 prefs에 내구성 있게 둔다.  
저장된 인덱스가 범위 밖/비숫자면 **clamp 하지 않고 열기를 거절**한다.

| 포함 | 미포함 |
|------|--------|
| 웹+앱 문장·그림 인덱스 | TTS 문장 안 초 단위 |
| 열기 시 jump only (자동 TTS 없음) | APK 자체 업데이트 |
| 이상값 → 열기 실패 메시지 | 캡션/그림 누락 |
| 저장: 문장/그림 이동 + 백그라운드/종료 | |

## Product (locked)

1. **B** — 문장 + 그림  
2. **B** — 앱 + 웹  
3. **A** — 점프만 (자동 TTS 없음)  
4. **B** — 이상 저장값 → **열지 않음** (에러)  
5. **C** — 이동 시 + 백그라운드/종료 시 저장  
6. APK 업데이트는 항상 뒤로  

## Policy change vs design/21

- 예전: 복원 시 **clamp**  
- 이번: 저장된 진행이 있으면 **검증 통과할 때만** 적용; 실패 시 open 거절  
- 저장된 진행이 **없으면** 서버 기본(보통 0)으로 연다 (정상)

## Kill / rollback

- `ASR_PROGRESS_FAIL_CLOSED=0` → 웹/앱이 다시 clamp 허용 (비상)  
- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.37**

## Device / pytest

- unit: validate indices · invalid refuses open  
- E2E: 문장/그림 이동 → 재오픈 동일 위치 · 오염 prefs → 에러 UI  

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
