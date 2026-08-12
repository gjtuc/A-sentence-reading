# 121 — Library open: GCS-first (cloud overwrite, no local fallback)

Modules: `papers_gcs.py` · `cache_open` · web `openCachedPaper` · mobile `openPaper`  
받침: [114](114-library-open-empty-session.md) · [18](18-paper-library.md) · [70](70-access-gate-gcs.md)

## 무엇인가

114는 **로컬이 비었을 때만** GCS를 다시 받았다.  
로컬에 문장이 있으면(깨진·남의 잔여·옛본) 클라우드를 안 보고 열릴 수 있다.

이번 칩: 보관 **열기**는 GCS가 준비되면 **항상** 소유자 창고에서 pull 한 뒤 연다.  
pull 실패 시 로컬이 있어도 **열지 않는다** (빈·반쯤 성공 금지).

| 포함 | 미포함 |
|------|--------|
| open: GCS ready → 항상 `download_paper_cache` | APK 자체 업데이트 |
| pull 실패 → 4xx/5xx · 로컬 폴백 금지 | 드래그 흰 섬광 |
| 웹+앱 (같은 `/open` API) | 캡션/그림 누락 |
| 킬스위치 + status 플래그 | |

## Product (locked)

1. **A** — 로컬 정상본이 있어도 **클라우드를 먼저** 받아 연다  
2. **A** — 클라우드 pull 실패 시 **로컬로 열지 않는다**  
3. **B** — 앱 + 웹  
4. GCS **미설정/미준비**(로컬 전용 개발)일 때만 로컬 open 허용 — pull “실패”와 구분  
5. 114 유지: 문장 0이면 open 성공 금지  

## Kill / rollback

- `ASR_PAPER_OPEN_GCS_FIRST=0` → 114 동작(로컬에 문장 있으면 skip pull)  
- `ASR_PAPER_OPEN_REQUIRE_SENTENCES=0` — 비어 있음 허용(비상, 기본 on)  
- Revert PR  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.35**

## Device / pytest

- unit: local-with-sentences + GCS fail → open 거절 · GCS ok → overwrite  
- E2E: 보관 열기 → 문장 보임 / pull 실패 시 에러 UI (성공 위장 없음)  
- A/B: 남의 cache_id → pull miss → 거절 (로컬 잔여로 성공 금지)

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
