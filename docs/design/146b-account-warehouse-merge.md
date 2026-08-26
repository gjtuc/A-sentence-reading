# 146b — Account warehouse merge (candidate)

Modules: GCS `users/{uid}/…` · `link_provider` post-hook  
받침: [146a](146a-mobile-account-link.md) · [23](23-multi-auth-link.md)

## 상태

**미구현 · 146a 이후.**  
로그인 수단 연결만으로는 옛 uid 창고(논문·노트)가 주 uid로 합쳐지지 않음.

## 포함 예정 (잠금 전)

- 연결 시 충돌 없는 provider의 **이전 uid** 창고 → 주 uid로 이전 또는 재색인  
- fail-closed · 부분 성공 시 성공 UI 금지 · 킬스위치

## 이번 저장소

설계 자리만 — 코드 없음.
