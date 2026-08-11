# 114 — Library open must not succeed with empty sentences

Modules: `papers_gcs.py` · `cache_open` · mobile open/reader  
받침: [108](108-fail-closed-no-cache.md) · [18](18-paper-library.md)

## 무엇인가

보관함에서 열면 **제목만** 보이고 문장·그림이 비는 경우:
로컬에 깨진/빈 `session.json`이 있으면 `ensure_paper_local`이 GCS를
다시 안 받고, 클라는 빈 세션을 「열림」으로 받아들인다.

| 포함 | 미포함 |
|------|--------|
| 로컬 session에 문장 없으면 GCS 재pull | 연습 청크 UX |
| open: 문장 0이면 실패 JSON (빈 성공 금지) | 드래그 흰 화면 |
| 클라: 문장 0 open 거절 · 새 논문 열 때 split 리셋 | |

## Product

1. 열기 성공 = 문장 ≥1 (그림은 0일 수 있음 — 문장만 있는 논문)  
2. 실패는 스낵바/에러 — 빈 읽기 화면으로 성공한 척 금지  
3. 소유자 GCS만 · user_id 바디 금지  

## Kill / rollback

- Revert PR  
- (선택) `ASR_PAPER_OPEN_REQUIRE_SENTENCES=0` 비상 — 기본 on  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.28**

## Device / pytest

- unit: empty local → force pull · open empty → 4xx  
- 실기: 보관 열기 → 문장 보임 (또는 명시 실패)

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
