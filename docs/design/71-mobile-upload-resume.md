# 71 — Mobile upload resume (job reattach · durable jobs)

모듈: `ingest_jobs_gcs.py` · `mobile/lib/api/upload_draft_*` · `library_controller.dart` · `client.dart`  
받침: [70-mobile-upload.md](70-mobile-upload.md) · [22-google-auth-gcs.md](22-google-auth-gcs.md) · [25-cloud-run.md](25-cloud-run.md)

## 무엇을

끊긴 모바일 PDF 올리기를 **앱이 알아서** 이어가게 한다 (제품 결정: 자동 · A+B · 같은 파일 재선택 시 자동).

| 포함 (이번 칩) | 미포함 (후속) |
|----------------|---------------|
| GCS `users/{uid}/ingest_jobs/{job_id}.json` | Content-Range / tus 바이트 구간 이어보내기 |
| 처리 중 앱 재실행 → `job_id` 폴링 재접속 (B) | Cloud Run 워커가 **다른 인스턴스에서 처리 재시작** |
| 전송 전 로컬 초안 PDF + 실패 시 자동 재 POST (A 최소) | 여러 파일 · docx 앱 업로드 |
| 같은 `content_hash` 재선택 → 재접속/재시도 | OS 백그라운드 알림 업로드 |
| job `owner_uid` 인가 (남의 job_id → 404) | 매직링크 로그인 |

## Flows

1. 업로드 시작 전: `content_hash`·로컬 PDF 초안 저장 (`asr.upload_draft.v1`)
2. `POST /api/ingest` 성공 → draft에 `job_id` · phase=`processing` · 서버는 job+원본 blob을 GCS에 push
3. 앱 종료 후 재실행 / 보관 탭: draft 있으면 **자동** `GET /api/ingest/jobs/{id}` 폴링 (B)
4. 같은 PDF 다시 고름: hash 일치 + job 있으면 재 POST 없이 폴링; 전송 실패 초안이면 로컬 바이트로 재 POST (A)
5. 완료(`cache_id`) → draft·로컬 PDF·GCS upload blob 삭제 · 목록 refresh · 자동 open (70과 동일)
6. 로그아웃 → draft/로컬 PDF wipe (다인 기기 fail-closed)

## INVARIANT

- 서버 user는 세션에서만 (`owner_uid`는 서버가 기록; 바디 `user_id` 없음)
- 앱에 Gemini/GCS secret 없음
- 실패·404·job 유실 → 성공 UI/가짜 목록 행 금지
- Live Enable / IPS → Trading Gate (ASR 밖) — **이번 칩 불필요**

## EDGE

- GCS 없/실패: fail-soft (인스턴스 로컬 `_JOBS`만; 재접속은 같은 인스턴스에서만)
- 다른 유저 job_id 추측 → **404** (존재 누설 최소화)
- owner 없는 레거시 memory job → 기존 progressive 계약 유지
- draft hash ≠ 로컬 파일 → 초안 삭제, 업로드 금지
- job 404 → draft clear 후 재시도 안내

## status

`ingest_job_gcs: true` · `mobile_upload_resume: true`

## Version

Web/mobile **0.2.88** · pubspec `0.2.88+1`

## Device E2E

1. 로그인 → 보관 → 작은 PDF 가져오기 시작
2. 처리 중 앱 강제 종료 → 재실행 → **자동으로 이어올리는 중** 진행 → 목록+자동 open
3. (A) 전송 직전 끊김 시뮬레이션: draft 있는 상태에서 같은 파일 재선택 → 재 POST 없이 또는 자동 재시도
4. 로그아웃 → 다른 계정 로그인 → 이전 draft/진행 UI 없음

Do not paste emails, cookies, or identifying paper titles into chat/PR.

## Kill / rollback

- Revert PR · status flags off on older builds ignore unknown keys
- GCS job objects under `users/{uid}/ingest_jobs/` are user-scoped; safe to leave orphaned JSON
