# 05 — Session store

## 1차 (M1–M4): 프로세스 메모리

```python
# api/session_store.py (NEXT)
SESSIONS: dict[str, PaperSession] = {}
MAX_SESSIONS = 8  # LRU eviction
```

- 서버 재시작 시 세션·미디어 무효 → UI는 다시 ingest
- 동시에 PDF 여러 개: 최대 8, 초과 시 가장 오래된 것 삭제 + `data/extracted/{id}/` 삭제

## 디스크 레이아웃 (M3+)

```
data/
  extracted/
    {session_id}/
      meta.json          # title, hash, indices, warnings (미디어 경로 제외 public 가능)
      figures/
        fig_0001_00.png
  uploads/               # 선택: 원본 보관. 기본은 temp 후 삭제
```

`.gitignore`에 `data/uploads/`, `data/extracted/` 이미 반영.

## `meta.json` 최소

```json
{
  "session_id": "ses_...",
  "content_hash": "...",
  "source_filename": "paper.pdf",
  "title": "...",
  "figure_index": 0,
  "sentence_index": 0,
  "warnings": [],
  "figures": [ { "id", "caption", "page_index", "rel_path" } ],
  "sentences": [ { "id", "text", "start_char", "end_char" } ]
}
```

`image_src`는 서빙 시 `/media/{session_id}/{id}.png`로 조립.

## 진행 복원 (M5) — 구현: [21-progress-restore.md](21-progress-restore.md)

키: `cache:{id}` · `hash:{sha256}` · `ses:{session_id}` (`asr.progress.v1`).

1. ingest 시 원본 바이트 SHA-256 → `content_hash`
2. 브라우저가 이동 시 localStorage 저장
3. 재열기·같은 파일 재업로드 시 clamp 후 복원

서버 측 progress 파일은 선택. 1차는 localStorage만.

## 수명

| 이벤트 | 동작 |
|--------|------|
| ingest 성공 | 새 session_id, SESSIONS에 put |
| LRU eviction | 디스크 디렉터리 shutil.rmtree |
| 명시적 DELETE (M5) | 동일 |
