# 132 — Cancel in-progress ingest/upload

Modules: `api/app.py` · `llm/ingest_jobs_gcs.py` · `llm/ingest_chunked.py` · Flutter library · `static/app.js`  
받침: [71](71-ingest-job-gcs.md) · [72](72-chunked-upload.md) · [107](107-ingest-job-reclaim.md) · [109](109-dismiss-library-ingest-error.md)

## 무엇인가

업로드·정제 중 **취소**가 없다. 잘못 고른 파일·멈춘 작업을 중간에 버릴 수 있어야 한다.  
이번 칩: **앱+웹**에서 조기 단계 취소 → **폐기(보관함 행 없음)** · **거의 끝나면 끝까지 진행**(취소 거절).

| 포함 | 미포함 |
|------|--------|
| `POST /api/ingest/jobs/{id}/cancel` (소유자만) | 「cancelled」 보관함 행 |
| `POST /api/ingest/uploads/{id}/cancel` (조각 세션) | ready 이후 강제 중단 |
| 워커 협조 중단 + GCS job/upload/payload 삭제 | 제목 페이지 그림 #1 |
| Flutter·웹 취소 버튼 | 인접 논문 PDF 제외 |
| status `ingest_cancel` · 킬 `ASR_INGEST_CANCEL=0` | |
| **0.3.48** | |

## Product (locked)

1. **앱 + 웹** 취소
2. 취소 시 **discard** — 보관함에서 제거하고 「cancelled」 행 없음
3. **거의 끝**(stage `ready` 이상 또는 `cache_id` 게시됨) → **끝까지 진행**; 취소 API는 `cancel_too_late`
4. 조기 단계(queued/extract/cache/quality/vision/figures/debone/split 등)만 취소 가능

## AuthZ / fail-closed

- `user`는 세션에서만. body/query `user_id` 무시.
- 남의 job/upload → **404** (존재 비노출).
- 미로그인 → **401**.
- 취소 후 poll → job 없음(**404**). 클라가 취소를 요청한 경우만 「취소됨」으로 처리; 임의 404는 기존처럼 실패.
- reclaim은 `cancel_requested` 또는 삭제된 job을 재시작하지 않음.

## Kill / rollback

- `ASR_INGEST_CANCEL=0` → cancel 엔드포인트 거절 · status `ingest_cancel=false`
- Revert PR · 이전 APK/웹 자산

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.48** · pipeline **rich-v12** (추출 로직 불변)

## Device / E2E pin

- Live `/api/status`: `version=0.3.48` · `ingest_cancel=true`
- APK `versionName=0.3.48` · SM-G986N (또는 웹 Live)
- Early cancel: 진행 UI → 취소 → 목록에 새 행 없음 · draft 클리어
- Late refuse: ready+ 에서 cancel → `cancel_too_late` · 작업은 계속/완료 가능
- Unauth cancel → 401 · cross-user → 404

Do not paste session cookies or secrets into docs.
