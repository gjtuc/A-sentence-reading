# design/512 — 정리 작업이 짧게 켜지는 서버에서도 돈다 (0.3.521)

## 확인한 것

- 2026-11-22 GCS `asr/users/<uid>/ingest_jobs/` 에 작업 기록 38개가 남아 있었다.
  - 10월에 끝난 작업 15개는 `artifact_retain_until` 이 11월 1~6일인데 지워지지 않았다.
  - 8~9월 작업 23개는 `done`·`error` 없이 대부분 `translate_pending` 에서 멈췄다. 기록마다 옛 형식 `result` 가 7~15 MB 였다. 원본 PDF 23개(약 100 MB)도 `ingest_uploads/` 에 남았다.
- 정리 루프 네 개가 첫 회차 전에 간격 전체를 잔다.
  - `_ingest_artifact_ttl_loop`, `_transfer_pack_ttl_loop`, `_paper_handoff_abandon_loop`: 1시간
  - `_evidence_rotate_loop` (로그 rotate + TTS 캐시 정리): 6시간
- design/395·511 이후 인스턴스는 마지막 요청 15분 뒤 내려간다. 그래서 첫 회차가 거의 오지 않았다.
- design/184 는 끝나지 않은 작업에 원본이 있으면 `reclaim_upload` 로 영원히 남긴다. 멈춘 작업은 이 규칙으로 계속 쌓인다.

## 결정

- 네 루프 모두 첫 회차를 `ASR_HOUSEKEEPING_FIRST_DELAY_S`(기본 120초, 간격보다 길지 않음) 뒤에 돈다. 그다음은 원래 간격.
- 로그 rotate 와 TTS 캐시 정리는 `asyncio.to_thread` 로 돈다. 첫 회차가 업로드 중에 올 수 있어서 이벤트 루프를 막지 않게 한다.
- 끝나지 않은 작업이라도 lease 가 끝났고 `updated_at` 이 `ASR_INGEST_ARTIFACT_STALE_UPLOAD_HOURS`(기본 336시간 = 14일, 최소 72) 보다 오래되면 원본째 지운다. 이유 코드는 `abandoned_with_upload`.
  - 원본 PDF 는 멈춘 작업을 이어받을 때만 읽는다. 서재(`papers/`)는 읽지 않으므로 지워도 서재는 그대로다. `papers/` 는 원래대로 지우지 않는다.
  - `updated_at` 이 없으면 계속 `reclaim_upload` 로 남긴다.
- 한 회차에 최대 20개(`ASR_INGEST_ARTIFACT_PURGE_BATCH`). 남은 38개는 서버가 두어 번 켜지면 정리된다.

## 같이 한 정리 (코드 밖)

- Artifact Registry `cloud-run-source-deploy` 의 `asr-sentence-reading` 보관 개수를 10 → 3 으로 줄였다. 이미지 하나가 약 1.4 GB 다.
- 쓰지 않는 묶음을 지웠다. `asr-sentence-reading-worker`(9월, 워커는 API 이미지를 쓴다)와 이 저장소의 `st-*`(주식 서비스는 `st-cloud-run` 을 쓴다)다.

## 시험

- `tests/test_design_512_housekeeping_first_pass.py`: 첫 대기 기본값과 상한, 네 루프 모두 첫 대기 뒤 간격으로 바뀜, rotate 가 스레드에서 돎.
- `tests/test_ingest_artifact_ttl.py`: 14일 넘게 멈춘 작업은 원본이 있어도 지움, `updated_at` 없으면 남김, 기본값과 하한.