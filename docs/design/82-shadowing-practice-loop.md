# 82 — Shadowing practice mode (loop · per-uid takes)

Modules: `shadowing_takes.py` · `/api/shadowing/takes` · web `shadowing_practice.js` · mobile practice screen  
받침: [79](79-shadowing-opt-in.md) · [80](80-shadowing-chunks.md)

## 무엇인가

별도 **연습 모드**에서 청크로 따라 말하기한다.

| 포함 | Later |
|------|--------|
| ⋯「연습」→ 별도 화면 | TTS pitch · 랜덤 난이도 |
| 로그인·킬·옵트인 게이트 | 키보드 노트 삭제 |
| 청크 **선성공** 후 입장 | 전체 앱 로그인 강제 감사(별도 칩) |
| 듣기 → TTS+녹음(+2초) → 재생 →「다음」/「건너뛰기」 | |
| 유저별 클라우드 takes + voice blob | |
| 나가도 진행 유지 · 문장 full-pass만 이어듣기 | |
| 웹 + 앱 | |

## Product (locked)

1. 「다음」= 같은 문장 다음 청크  
2. 녹음 실패·스킵 = 빈 칸 +「건너뛰기」가능  
3. 웹+앱  
4. 별도 연습 화면 (기본 읽기 화면 비확장)  
5. 현재 문장부터  
6. TTS 종료 후 **여유 2초** 녹음  
7. 청크 없으면 **먼저 build 성공**해야 입장  
8. 비로그인 사용 불가  
9. 녹음·진행 = 계정(클라우드) 유저별  
10. 중도 퇴장 후에도 takes 유지  
11. 이어듣기 = **문장 전체 통과 녹음만** (스킵만 있는 문장 제외)

## Kill / rollback

- `ASR_SHADOWING_PRACTICE=0` → API·UI 비활성  
- Revert PR  

## Mobile mic

Android `MediaRecorder` via MethodChannel `asr/shadowing_mic` (no pub.dev `record` package). Permission deny / start fail → empty slot +「건너뛰기」(성공 위장 금지).

## Fail-closed / multi-user

- 세션 uid만 · body `user_id` 무시  
- takes/voice는 `users/{uid}/…`  
- 킬 OFF·미로그인·청크 실패 → 입장 성공 UI 금지  

## Live Enable / IPS

이번 칩에서 **불필요**.

## Version

**0.3.3** · pubspec `0.3.3+1`

Do not paste emails, cookies, or tokens into chat/PR.
