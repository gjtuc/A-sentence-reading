# 80 — Shadowing chunk plans (per-user · ingest/backfill)

Modules: `shadowing_chunks.py` · `/api/shadowing/chunks` · ingest hook  
받침: [79](79-shadowing-opt-in.md)

## 무엇인가

쉐도잉 **연습 구간(청크)** 을 Gemini로 만들어 **유저별**로 저장한다.  
연습 UI(듣기·녹음)는 Later.

| 포함 | Later |
|------|--------|
| Gemini 청크 계획 (단계 수·경계는 모델) | 연습 루프 UI |
| 유저별 저장 `users/{uid}/shadowing/chunks/{cache_id}.json` | TTS pitch · 랜덤 |
| ingest 종료 시 · **클라 쉐도잉 ON** 일 때만 | 키보드 노트 삭제 |
| 기존 논문 열 때 백필 | |
| 실패 시 명시 오류 + 재시도 API/UI | |
| EN/KO 혼용 문장 그대로 자르기 | |

## Product (locked)

1. 저장 = **유저별** (논문 공유 칸에 넣지 않음)  
2. ingest 끝 · **설정 쉐도잉 ON** 일 때만 전체 문장 생성 (번역 on↔번역 작업과 같은 게이트 개념)  
3. 옛 논문 재오픈 → 없으면 **백필**  
4. 실패 → 사용자에게 보이고 **다시 시도**  
5. 단계 개수 = Gemini  
6. 한국어 포함·혼용 문장은 섞인 그대로  

## Kill / rollback

- `ASR_SHADOWING_PRACTICE=0` → 청크 API·ingest 훅 거부/스킵 (79와 동일 킬)  
- Revert PR  

## Fail-closed / multi-user

- 세션 uid만 사용 · 바디 `user_id` 무시  
- `cache_id` / uid 경로 sanitize · 다른 uid 객체 403/404  
- 킬 OFF · 선호 OFF · 미로그인 → 생성 안 함 · 성공 UI 금지  
- Gemini 실패 → `status=error` (빈 ok 금지)  

## Live Enable / IPS

이번 칩에서 **불필요**.

## Version

**0.2.98** · pubspec `0.2.98+1`

## Device / browser E2E (pre-merge)

- 킬 ON + 선호 ON → build/retry 경로 (Gemini mock 또는 실키)  
- 유저 A 청크를 B가 GET → 없음/거절  
- 실패 배너 + 재시도 버튼  
- Live Enable / IPS unchanged  

Do not paste emails, cookies, or tokens into chat/PR.
