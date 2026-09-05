# 174 — Worker GCS uid bind · library list miss (ingest → 목록)

Modules: `auth_google.gcs_uid_scope` · `api/app.py` `_run_ingest_job` · `papers_gcs.ensure_paper_in_remote_index` · `cache/paper_cache.save_paper_session` · mobile `library_controller` / `listPapers(fresh:)`  
받침: [108](108-fail-closed-no-cache.md) · [121](121-library-open-gcs-first.md) · [155](155-deploy-live-guard.md) · [169](169-agent-evidence-bus.md) · [173](173-capacity-isolation-roadmap.md)

## 왜

Live `ingest_inline=0` (173c) 이후 worker가 PDF를 로컬에만 저장하고 `cache_id` 성공을 돌려도,  
`current_gcs_uid()`가 비어 `personal_object_name` → `None` → **유저 `papers/index.json` 미갱신**.  
앱은 `목록에 아직 없습니다`만 반복. 목록 miss에 evidence kind도 없었음.

## Product (locked)

1. Ingest 파이프라인 전체는 `job.owner_uid`로 `gcs_uid_scope` 바인딩.
2. auth+GCS ready면 보관 성공 = **remote index에 id 등재** (`ensure_paper_in_remote_index`). 실패 시 design/108식으로 terminal error (성공 cache_id 금지).
3. `papers_upload_fail` · `library_list_miss` evidence (add-only floor).
4. `GET /api/cache/papers?fresh=1` 로 API 인스턴스 remote-index TTL 우회; 앱은 miss 시 한 번 fresh 재조회.

## Kill / rollback

- Revert PR · 또는 worker에서만 `ASR_INGEST_INLINE=1` (권장하지 않음).

## Version

**0.3.156**
