# 110 — Ingest checkpoint envelope (foundation for mid-stage resume)

Modules: `ingest_jobs_gcs.py` · `api/app.py` (`_job_set`, `_reclaim_ingest_job_from_gcs`, `/api/status`)  
받침: [107](107-ingest-job-reclaim.md) · [71](71-mobile-upload-resume.md) · [109](109-dismiss-library-ingest-error.md)

## 무엇인가

중간 stage 이어받기의 **기초 봉투**만 넣는다.  
job GCS 기록에 `checkpoint`(스키마·`pipeline_version`·TTL·stage·cursor·content_hash)를 쓰고, reclaim 때 **유지 vs 폐기**만 결정한다.  
**페이지/청크 스킵 로직은 넣지 않는다** (후속 칩). 유효해도 파이프라인은 아직 **처음부터** 돈다 — 가짜 skip·빈 성공 금지.

| 포함 | 미포함 |
|------|--------|
| checkpoint 스키마 v1 + persist (`serialize_job_record`) | vision/debone/translate 실제 skip |
| TTL·`PIPELINE_VERSION` 불일치 → 폐기 후 전체 재시작 | 제목 최소 길이 완화 |
| reclaim 시 유효하면 message에 **이어받을 지점** 표시 + CP 유지 | Live Enable / IPS |
| `want_translate` / `want_shadowing_chunks` GCS persist | 클라이언트 필수 UI 변경 |
| kill `ASR_INGEST_CHECKPOINT=0` | |

## Product (locked)

1. 전 구간(품질→비전→디본→번역…) 봉투에 stage/cursor 기록 — **스킵은 후속**  
2. 오래된 체크포인트 → **버리고 처음부터**  
3. `pipeline_version` / 스키마 불일치 → **버리고 처음부터**  
4. UI: poll `message`로 이어받을 지점 표시 (기존 진행 문구 경로)  
5. 같은 PDF 자동 이어올리기(초안)는 기존 유지  
6. 소유자 세션만 job/CP 조회 — 남의 uid → 404  
7. CP payload에 논문 본문·제목 전문을 넣지 않음 (stage/cursor/hash만)

## Kill / rollback

- `ASR_INGEST_CHECKPOINT=0` → 봉투 미기록·항상 폐기(reclaim은 107 동작)  
- `ASR_INGEST_CHECKPOINT_TTL_HOURS` (기본 168 = 7일)  
- Revert PR

## Version

**0.3.24** · status `ingest_checkpoint`

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- unit: TTL/version/hash 폐기 · 유효 시 message에 stage/cursor  
- reclaim + fake GCS: want_* persist · 교차 유저 404  
- 실기: `/api/status` `ingest_checkpoint` + APK pin 0.3.24 (메시지 경로는 기존)

## 후속 (이 칩 밖)

- 유효 CP면 extract/quality/vision… **실제 skip**  
- 부분 산출물(GCS payload_ref) 저장

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
