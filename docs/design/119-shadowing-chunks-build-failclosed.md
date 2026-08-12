# 119 — Shadowing chunks/build: no raw 500 · honest pending continue

Modules: `app.py` (`/api/shadowing/chunks/.../build`) · `shadowing_chunks.py` · mobile practice · web ensure  
받침: [80](80-shadowing-chunks.md) · [113](113-shadowing-chunk-budget.md) · [82](82-shadowing-practice-loop.md)

## 무엇인가

연습 진입/`chunks/build`가 **가끔** 실패한다. 조사:

1. 긴 논문은 design/113상 첫 build가 `status=pending` + `continue=true`인데,  
   모바일 연습 화면·웹 `ensureChunksOrThrow`가 **한 번만** 호출하고 `status!=ok`면 실패 처리.
2. 웹 `ensureShadowingChunks`는 `body.ok===true`만 보고 배너를 지움 → **pending인데 성공한 척** (빈 성공 금지 위반).
3. Gemini/GCS 등 **미포착 예외**는 FastAPI raw **HTTP 500** (구조화 JSON 없음).

| 포함 | 미포함 |
|------|--------|
| 클라: pending이면 이어 build (상한) · 완료만 입장 | 같은 청크 재시도 UX(별 칩) |
| 웹: pending 중 배너 유지 · ok일 때만 해제 | 핀치·설정 카피 |
| 서버: 예상 밖 예외 → **502** + 안전 메시지 (스택/비밀 숨김) | Live Enable / IPS |
| Gemini 예외 → plan `error` 경로로 흡수 | |

## Product (locked)

1. 실패를 성공처럼 보이지 않음 (`pending`≠완료, `error`≠입장)  
2. `pending`은 「아직 준비 중」·자동 이어받기  
3. 하드 실패만 실패 문구 + 재시도 가능  
4. 소유자 uid 경로만  

## Kill / rollback

- `ASR_SHADOWING_PRACTICE=0`  
- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.33**

## Device / pytest

- unit: API unexpected → 502 JSON · pending continue contract  
- A≠B 격리 유지  
- 실기: 설정 쉐도잉 ON → 연습 → pending 이어받기 또는 완료 · 실패 시 성공 UI 없음
