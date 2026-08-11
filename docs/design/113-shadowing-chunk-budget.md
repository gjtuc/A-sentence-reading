# 113 — Shadowing chunk build: time budget · resume (no HTTP 504)

Modules: `shadowing_chunks.py` · `/api/shadowing/chunks/.../build` · mobile ensure/retry  
받침: [80](80-shadowing-chunks.md) · [82](82-shadowing-practice-loop.md)

## 무엇인가

연습 구간 build가 **문장마다 Gemini**를 동기 호출해 Cloud Run 요청 한도(300s)를
넘기면 게이트웨이 **HTTP 504**만 남고, 클라는 「연습 구간을 만들지 못함」으로 고착된다.
한 요청 안에 **시간 예산**으로 잘라 부분 저장하고, 다음 요청이 **이어서** 만든다.

| 포함 | 미포함 |
|------|--------|
| `status=pending` 부분 plan 저장 · resume | 연습 루프 UI 개편 |
| build API 200 + pending (게이트웨이 504 회피) | Live Enable / IPS |
| 클라: pending이면 자동 이어받기 · 504도 재시도 | 보관 열기 빈 화면(별도 칩) |
| kill `ASR_SHADOWING_PRACTICE=0` 유지 · budget env | |

## Product (locked)

1. 실패를 성공처럼 보이지 않음 — `pending`은 「아직 준비 중」  
2. 이미 만든 문장 청크는 재생성하지 않음 (비용·일관성)  
3. 전체 완료 때만 `status=ok`  
4. 하드 오류만 `status=error` + 재시도  
5. 소유자 uid 경로만  

## Kill / rollback

- `ASR_SHADOWING_PRACTICE=0`  
- `ASR_SHADOWING_CHUNK_BUDGET_S` (기본 90, 15–240)  
- Revert PR  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.27** · status 그대로 shadowing flags · design pin 113

## Device / pytest

- unit: resume skips built ids · budget 만료 → pending 저장  
- A≠B 격리 유지  
- 실기: 설정 쉐도잉 ON → 열기 → pending/완료 배너 · 504 고착 없음  

## 후속 후보

- 보관 열기 후 문장·그림이 비는 경우(별도 재현)  
- 보관함 드래그 흰 화면 · 자체 APK 업데이트  

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
