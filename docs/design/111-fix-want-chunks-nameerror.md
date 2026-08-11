# 111 — Fix ingest `want_chunks` NameError (and open fail-closed JSON)

Modules: `api/app.py` (`_run_ingest_job_body` shadowing block · `cache_open`)  
받침: [108](108-fail-closed-no-cache.md) · [80](80-shadowing-chunks.md) · [18](18-paper-library.md)

## 무엇인가

chip 108 편집 실수로  
`want_chunks = bool(...)` 가 **주석 한 줄에 붙잡혀** 실행되지 않아, 보관 저장 직후  
`name 'want_chunks' is not defined` 로 job이 error로 끝났다.  
같은 칩에서 `cache/open` 이 예외 시 HTML/빈 500만 내지 않도록 **JSON fail-closed**를 보강한다.

| 포함 | 미포함 |
|------|--------|
| `want_chunks` 할당 복구 (주석과 분리) | mid-stage skip |
| 회귀: 소스에 merged-comment 금지 | Live Enable / IPS |
| `cache_open` 예상 밖 예외 → JSON 500 + 안전 메시지 | 논문 제목 정책 |

## Product (locked)

1. 보관 저장 성공 후 shadowing 블록이 NameError로 전체를 망가뜨리지 않음  
2. open 실패 시 클라가 `cache/open HTTP 500` 만 보지 않도록 **message JSON** 제공  
3. 메시지에 경로·스택·비밀·제목 전문 금지

## Kill / rollback

- Revert PR

## Version

**0.3.25**

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- 소스: `want_chunks =` 가 주석이 아닌 실행 문  
- open: 강제 예외 시 JSON `ok:false`  
- 실기: APK 0.3.25 · 보관 논문 열기 (가능하면 기존 1건)

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
