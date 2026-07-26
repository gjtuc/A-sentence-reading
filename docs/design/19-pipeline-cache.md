# 19 — Pipeline version & stale cache

모듈: `llm/typography.py` (`PIPELINE_VERSION`) · `cache/paper_cache.py` · `api` open/list · 보관 UI

## 정책

| 상황 | 동작 |
|------|------|
| ingest 제목 매칭 | `pipeline_version != PIPELINE_VERSION` 이면 **히트 거부** → 재분석 |
| 재분석 저장 | 같은 `title_key`+`source` → **같은 `cache_id`** 덮어씀 → 노트 키 유지 |
| 보관 목록 `/open` | stale 이어도 **열기 허용** (되새김질·노트 유지) |
| UI | 목록에 `· 갱신 필요` · 열면 상태 경고 |

## 왜 막지 않나

원본 PDF를 캐시하지 않으므로 stale open 을 막으면 사용자는 파일을 다시 찾기 전엔 노트도 못 연다.  
열어 두되, 같은 파일을 다시 넣으면 자동 재분석되도록 한다.

## API

- `GET /api/status` → `pipeline_version`
- 목록 entry → `pipeline_version`, `stale`
- 원본이 있으면 보관 UI 「재분석」으로 재실행 (0.2.16 — [20-source-backup.md](20-source-backup.md)); 없으면 파일 재업로드
- open 응답 → `stale`, `current_pipeline`, `warnings: ["stale_pipeline"]`
