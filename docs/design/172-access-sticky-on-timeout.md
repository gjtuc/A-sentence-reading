# 172 — Access sticky unlock on status timeout

Modules: `access_models.dart` · `access_sticky_store.dart` · `home_shell.dart` · web `app.js`  
받침: [84](84-access-waiting-ux.md) · [67](67-access-gate.md) · auth soft-reconnect (0.3.123)

## 무엇인가

이미 Allow된 사용자가 Cloud Run이 잠깐 느릴 때 `/api/access/status` 실패로
**「액세스 승인 대기」**에 튕기지 않게 한다. 성공 조회만 sticky를 갱신한다.

| 포함 | 미포함 |
|------|--------|
| in-memory + per-uid disk sticky | Deny/Allow API 변경 |
| fail → keep unlock / soft reconnect | 서버 게이트 완화 |
| 짧은 재시도 | Live Enable / IPS |

## Product (locked)

1. **성공** 조회 → `unlocked` 확정 + sticky 기록 (allowed / gate-off = true, else false)  
2. **실패** + (이번 세션 unlocked **또는** sticky true) → **본 앱 유지** + 백그라운드 재시도  
3. **실패** + sticky false / 세션 locked → 대기 셸 유지 (Allow 위조 금지)  
4. **실패** + 미지 → **서버 연결 재시도** UI (승인 대기 문구 금지)  
5. 로그아웃 → 해당 uid sticky 삭제  

## Fail-closed (updated)

- **유료 API**는 서버가 계속 막음 (클라 sticky ≠ Allow)  
- sticky true인데 실제 Deny면 다음 **성공** 조회에서 대기 셸로 복귀  
- 미승인 사용자를 성공 UI로 열지 않음 (미지 → reconnect만)

## Kill / rollback

- Revert PR · sticky key ignore (항상 84 구동작)

## Version

**0.3.147**

Do not paste emails, cookies, tokens, or invite codes into chat/PR.
