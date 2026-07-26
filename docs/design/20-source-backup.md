# 20 — 원본 PDF/DOCX 백업 · 재분석

모듈: `cache/paper_cache.py` · `llm/papers_gcs.py` · `POST /api/cache/papers/{id}/reanalyze` · 보관 UI 「재분석」

## 무엇을

분석 보관본(`session.json` + figures)과 함께 **업로드 원본**을 `source.pdf` / `source.docx` 로 둔다.  
파이프라인이 바뀌면(stale) 파일을 다시 고르지 않고 **보관 원본으로 재분석**한다. `cache_id` 유지 → 노트 키 `cache:{id}` 유지.

## 로컬

| 경로 | 의미 |
|------|------|
| `data/cache/papers/{id}/source.pdf` | PDF 원본 |
| `data/cache/papers/{id}/source.docx` | Word 원본 |
| session/index `has_source` · `source_file` | 메타 |

- 저장 시 `save_paper_session(..., source_path=)` 가 복사. **80MB** 초과면 session만 보관.
- 캐시 히트여도 원본이 없으면 `attach_source_file` 으로 백필.
- `rmtree` 후 다시 쓰므로 재분석은 **temp 복사본**에서 ingest (원본 경로를 직접 넘기지 않음).

## GCS

`{prefix}/papers/{cache_id}/source.pdf|docx` — session·figures 와 같이 push/pull/delete.  
index entry 에 `has_source` 반영.

## API / UI

| | |
|--|--|
| `POST …/reanalyze` | 원본 → ingest job (`skip_cache`) · `job_id` 폴링은 ingest 와 동일 |
| 보관 목록 | `has_source` 이면 「재분석」 · 메타에 `· 원본` |

원본 없으면 404 `source_missing` — 파일을 다시 열어 백필.

## 버전

0.2.16
