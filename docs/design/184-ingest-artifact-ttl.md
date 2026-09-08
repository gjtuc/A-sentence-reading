# 184 — Ingest artifact TTL (uploads · jobs · payloads)

Modules: `ingest_artifact_ttl.py` · `ingest_jobs_gcs.py` · `app.py` lifespan  
Parents: [107](107-ingest-job-reclaim.md) · [110](110-ingest-checkpoint-envelope.md) · [112](112-ingest-resume-skip.md) · [144](144-paper-retention-ttl.md) · [168](168-ingest-observability.md)

**Status:** SHIPPING (0.3.177)  
**UI:** 없음 (서버 purge · evidence)

## 0. Success

| Pass | Fail |
|------|------|
| `papers/` 객체 수 불변 | source.pdf / session 삭제 |
| terminal job + TTL 경과 → upload/payload/job 삭제 | running / reclaim-able upload 삭제 |
| orphan upload (no job) + abandon 경과 → 삭제 | 새 업로드 직후 orphan 오삭제 |
| kill `ASR_INGEST_ARTIFACT_TTL=0` → no-op | papers retention과 혼동 |

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | Never delete under `users/{uid}/papers/` |
| J2 | Job-scoped: `ingest_jobs` · `ingest_uploads` · `ingest_payloads` only (v1; `ingest_chunks` uses `upl_` ids — out of scope) |
| J3 | Clock starts only when terminal (`done` or `error`) |
| J4 | Non-terminal + lease alive → keep |
| J5 | Non-terminal + lease expired + upload present → keep (107 reclaim) |
| J6 | Delete order: upload → payload → job json last |
| J7 | Default TTL 168h; abandon orphan upload 336h |
| J8 | Kill `ASR_INGEST_ARTIFACT_TTL=0` |
| J9 | Batch/limit per tick; `asyncio.to_thread` |
| J10 | Dry-run `ASR_INGEST_ARTIFACT_TTL_DRY_RUN=1` |

## 2. Env

| Var | Default |
|-----|---------|
| `ASR_INGEST_ARTIFACT_TTL` | `1` |
| `ASR_INGEST_ARTIFACT_TTL_HOURS` | `168` |
| `ASR_INGEST_ARTIFACT_ABANDON_HOURS` | `336` |
| `ASR_INGEST_ARTIFACT_PURGE_INTERVAL_S` | `3600` |
| `ASR_INGEST_ARTIFACT_PURGE_BATCH` | `20` |
| `ASR_INGEST_ARTIFACT_TTL_DRY_RUN` | `0` |

## 3. Implementation hazards

H1–H18 (chat lock): papers allowlist, reclaim, lease≠TTL, uid bind, dry-run, evidence hash-only, batch limits.

## 4. Version

**0.3.177**
