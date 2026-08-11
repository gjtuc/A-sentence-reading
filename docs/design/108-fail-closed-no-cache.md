# 108 — Fail-closed when ingest finishes without library cache

Modules: `api/app.py` (`_run_ingest_job_body` final) · `mobile/lib/api/client.dart`  
받침: [71](71-mobile-upload-resume.md) · [107](107-ingest-job-reclaim.md) · [19](19-pipeline-cache.md)

## 무엇인가

처리가 끝나도 **`cache_id`가 없으면** job을 성공「완료」로 닫지 않는다.  
앱에 「보관 저장 실패: 완료」처럼 모순된 문구가 남거나, 업로드 blob을 지워 재시도를 막는 구멍을 닫는다.

| 포함 | 미포함 |
|------|--------|
| 최종 `_finish_job` 전 cache 필수 (없으면 `error` terminal) | 제목 최소 길이 정책 완화 |
| 짧은 제목/문장 없음 → 명확한 한국어 에러 | 중간 stage resume (후속) |
| 실패 시 **ingest upload blob 유지** (재시도·reclaim 가능) | Live Enable / IPS |
| 클라: `완료`만 있는 실패 문구 정리 | |

## Product (locked)

1. 보관함 row가 생기지 않으면 **성공 UI·성공 job 금지**  
2. 에러 문구에 「완료」만 붙이지 않음  
3. 실패 terminal에서도 원본 blob을 바로 지우지 않음  
4. 비밀·제목 전문을 로그/알림에 넣지 않음

## Kill / rollback

- Revert PR

## Version

**0.3.22**

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- 서버: no `cache_id` → `done`+`error`, message ≠ bare「완료」  
- 클라: empty cache_id + msg「완료」→ 짧은제목 안내 문구  
- 실기: 실패 후 성공한 척 목록 행 없음 · uploading 해제

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
