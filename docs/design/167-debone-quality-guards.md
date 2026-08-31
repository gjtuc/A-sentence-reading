# 167 — Debone quality guards · warnings persist · Body diagnostic

**Version:** (구현 시 bump — 예: 0.3.100)  
**Depends:** [12](12-gemini-debone.md) · [13](13-rich-text-two-pass.md) · [05](05-session-store.md) · [19](19-pipeline-cache.md) · [108](108-fail-closed-no-cache.md)  
**Blocks:** [166](166-reader-annotations.md) (reanchor는 본 칩 이후)

## 무엇인가

Gemini debone이 **청크 0문장·부분 실패·환각**을 조용히 통과시키는 문제를 막고, 품질 신호를 **`session.json`에 영구 저장**해 재오픈·모바일에서도 보이게 한다.

**Body** 섹션은 제거하지 않는다 — 섹션 미분류·품질 이상의 **진단 신호**로 쓴다.

### 관측 사례 (acsanm.1c00673)

| 지표 | 캐시 세션 (live) | 신규 debone |
|------|------------------|-------------|
| 문장 수 | **93** | **163** |
| 누락 | Experimental · Conclusion 통째 소실 | — |
| 원인 | chunk 2·6이 `{"sentences":[]}` 반환 → `chunks_ok`만 증가 | — |
| 환각 | PDF에 없는 문장 (예: Earth's crust) | 검증 없음 |
| UI | `debone=true` → 정제 성공으로 표시 | job `warnings`만, 재오픈 시 소실 |

---

## Product (locked)

| Rule | Detail |
|------|--------|
| Body 유지 | `section=body` 제거·병합 금지 — 비율·플래그로 품질 표시 |
| 침묵 실패 금지 | substantive 청크 0문장 → split fallback + warning |
| warnings 영속 | `session.json.warnings[]` + `ingest_quality` |
| debone_ok 정책 (1차) | `len(sentences)>0`이면 `debone=true` 유지; 품질은 warnings로만 |
| fail-closed (2차, 옵션) | `coverage<0.50` AND `chunks_failed≥2` → 전체 `split_into_sentences` 폴백 |
| 환각 | `quality_flags: ["ungrounded"]` per sentence — 자동 삭제 금지 (1차) |
| 재분석 | 기존 `POST /api/cache/papers/{id}/reanalyze` — 배너에서 연결 |

---

## Root cause (현재 코드)

`llm/debone.py`:

1. `_process_one_chunk` — Gemini `{"sentences":[]}` → `return []` (L433–434)
2. assemble 루프 — `pairs is None`만 skip; **`[]`는 `chunks_ok += 1`**, `collected`에 0개 (L536–540)
3. References-only 청크와 **본문 청크 empty**를 구분하지 않음
4. `DeboneResult.warning` — ingest job에만; `save_paper_session`이 저장 안 함
5. `cache_open` — `info`에 warnings 없음; stale만 추가

---

## 모듈

| 파일 | 역할 |
|------|------|
| `llm/debone_quality.py` | **신규** — coverage, grounding, chunk_kind, fallback split |
| `llm/debone.py` | 청크 루프·DeboneResult 확장·프롬프트 보강 |
| `models.py` | `Sentence.quality_flags: list[str]` |
| `cache/paper_cache.py` | `warnings`, `ingest_quality` save/load |
| `api/app.py` | ingest·open·save 연동 |
| `tests/test_debone_quality.py` | **신규** |

---

## `debone_quality.py` — API

### 상수

```python
CHUNK_SUBSTANTIVE_ALNUM = 120   # 본문 청크 최소 알파뉴메릭
COVERAGE_LOW = 0.50
COVERAGE_WARN = 0.65
BODY_RATIO_WARN = 0.30
GROUNDING_MIN_WORDS = 5
GROUNDING_NGRAM = 5
```

### `chunk_kind(chunk) -> "references" | "substantive" | "sparse"`

| kind | 조건 |
|------|------|
| `sparse` | alnum < 40 |
| `references` | head가 References/Bibliography/Acknowledgments + 인용 위주 |
| `substantive` | alnum ≥ 120 |

**INVARIANT:** `substantive` 청크에서 Gemini `[]` = **실패** (References empty와 다름).

### `fallback_split_chunk(chunk, ctx, idx, total)`

- `pdf.sentences.split_into_sentences(chunk)`
- section: `infer_section_for_chunk` — survey `section_order` + 청크 위치 비례
- debone과 동일: 12자 미만 숫자-only 라인 drop

### `compute_coverage_ratio(raw_text, sentences) -> float`

- 토큰: plain text에서 `[a-z0-9]{3,}` (소문자)
- **recall-biased:** `|out ∩ raw| / |raw|`
- raw 비어 있으면 `1.0`

### `check_sentence_grounded(text, raw_text) -> bool`

- 5-gram sliding window이 raw에 1개라도 있으면 grounded
- 단어 < 5개 → `True` (제목 등)
- 완화: 3-gram hit ≥ 3

### `IngestQuality` → `to_dict()`

```json
{
  "chunks_total": 7,
  "chunks_ok": 7,
  "chunks_failed": [],
  "chunks_fallback_split": [2, 6],
  "coverage_ratio": 0.87,
  "body_sentence_count": 12,
  "body_ratio": 0.074,
  "ungrounded_count": 1,
  "ungrounded_ids": ["sent_00041"]
}
```

### Warning 코드 (`quality_to_warnings`)

| 코드 | 조건 | UI |
|------|------|-----|
| `chunk_fallback_split:{i}` | 청크 i split 폴백 | ℹ️ |
| `partial_debone:{ok}/{total}` | legacy; substantive empty 있음 | ⚠️ |
| `missing_front_matter` | 기존 | ⚠️ |
| `coverage_low:{ratio}` | < 0.50 | 🔴 |
| `coverage_warn:{ratio}` | < 0.65 | ⚠️ |
| `high_body_ratio:{ratio}` | body > 30% | ⚠️ |
| `ungrounded_sentences:{n}` | n > 0 | ⚠️ |
| `survey_failed` / `survey_bad_json` | 기존 | ℹ️ |

---

## `debone.py` 변경

### `DeboneResult` 확장

```python
@dataclass
class DeboneResult:
    sentences: list[Sentence]
    ok: bool
    warning: str | None          # legacy ";".join — 하위호환
    warnings: list[str]          # NEW
    chunks_ok: int
    chunks_total: int
    ingest_quality: dict | None  # NEW
```

### 청크 파이프라인 (per chunk)

```
Phase A: _process_one_chunk (기존 3 retries)
Phase B: pairs==[] AND kind==substantive
         → retry 1회
         → still [] → fallback_split_chunk
         → stat.fallback = "split"
Phase C: Exception → fallback_split_chunk
Phase D: pairs==[] AND kind==references → OK (empty)
```

### assemble 후

1. glossary (`apply_glossary`) — 기존
2. front-matter retry — 기존
3. `repair_dollar_cite_artifacts` — 기존
4. **NEW:** per-sentence `quality_flags` if not `check_sentence_grounded`
5. **NEW:** `build_ingest_quality` + `quality_to_warnings`

### 프롬프트 추가 (`_SYSTEM`)

```
EMPTY OUTPUT RULE:
- Return {"sentences":[]} ONLY for References/author-only/page-header chunks.
- NEVER return empty for experimental/results/conclusion prose.
- NEVER fabricate content not in CHUNK.
```

---

## `session.json` 스키마 (확장)

기존 `version: 1` 유지. 추가 필드:

```json
{
  "warnings": ["chunk_fallback_split:2", "coverage_warn:0.58"],
  "ingest_quality": { "...": "위 IngestQuality" },
  "sentences": [
    {
      "id": "sent_00042",
      "text": "...",
      "section": "experimental",
      "text_ko": "",
      "text_ko_stage": "",
      "quality_flags": ["ungrounded"]
    }
  ]
}
```

**하위호환:** `quality_flags` 없으면 `[]`. 구 클라이언트는 unknown field 무시.

### `save_paper_session` 시그니처

```python
def save_paper_session(
    session, *,
    debone: bool = False,
    warnings: list[str] | None = None,      # NEW
    ingest_quality: dict | None = None,     # NEW
    source: str = "pdf",
    ...
)
```

### `load_cached_session` → `info`

```python
info["warnings"] = list(meta.get("warnings") or [])
info["ingest_quality"] = meta.get("ingest_quality") or {}
```

---

## API

### Ingest job 완료 (`POST /api/ingest` → job result)

기존 + 확실히 포함:

```json
{
  "debone": true,
  "warnings": ["chunk_fallback_split:2", "coverage_warn:0.58"],
  "ingest_quality": { "coverage_ratio": 0.58, "chunks_fallback_split": [2, 6] }
}
```

### Cache open (`GET /api/cache/papers/{id}/open`)

```json
{
  "warnings": ["chunk_fallback_split:2", "stale_pipeline"],
  "ingest_quality": { ... },
  "sentences": [ { "quality_flags": ["ungrounded"] } ]
}
```

`stale_pipeline`은 기존처럼 **앞에** prepend. persisted warnings와 merge (`dict.fromkeys`).

### Ingest resume payload

`ingest_resume_payload` checkpoint에 `ingest_quality` 추가 (기존 `warnings`와 함께).

---

## Body 섹션 — 진단 (locked)

| 신호 | 의미 | UI |
|------|------|-----|
| `section=body` | Gemini가 섹션 분류 실패 | 헤더 `Body` (기존) |
| `high_body_ratio` warning | body > 30% | 헤더 `Body ⚠` (모바일) |
| `quality_flags` on body sentences | 환각 의심 | 문장 위 amber 뱃지 |

**하지 않음:** body → methods 자동 재분류.

---

## Mobile (이 칩 범위)

| 파일 | 변경 |
|------|------|
| `reading_models.dart` | `SentenceView.qualityFlags`, `IngestQuality?` on `ReadingSession` |
| `reader_screen.dart` | `MaterialBanner` if `ingestQuality.needsBanner`; ungrounded badge |
| `library_controller.dart` | open 후 banner trigger (optional once-per-session dismiss) |

### `IngestQuality.needsBanner`

```dart
coverageRatio < 0.65 ||
chunksFallbackSplit.isNotEmpty ||
ungroundedCount > 0
```

배너 액션: **재분석** → `reanalyzePaper(cacheId)` · **닫기** → session prefs dismiss.

---

## Web (이 칩 범위)

`app.js` — `debone=false`만 표시하던 status bar 확장:

- `partial_debone` / `coverage_low` / `chunk_fallback_split` 있으면 경고 문구
- `debone=true`여도 warnings 표시

---

## 테스트 (`tests/test_debone_quality.py`)

| ID | 케이스 | assert |
|----|--------|--------|
| T1 | substantive chunk, Gemini `[]` | fallback ≥ 1 sentence |
| T2 | References chunk, Gemini `[]` | no fallback, ok |
| T3 | coverage raw 500 tok, out 100 | `coverage_low` |
| T4 | sentence not in raw | `quality_flags == ["ungrounded"]` |
| T5 | save → load session | `warnings` in meta |
| T6 | `chunk_kind` experimental prose | `substantive` |
| T7 | acsanm fixture (optional CI) | `sentence_count >= 140` |

---

## 구현 체크리스트

- [ ] `llm/debone_quality.py`
- [ ] `llm/debone.py` — chunk loop, DeboneResult, prompt
- [ ] `models.py` — `quality_flags`
- [ ] `cache/paper_cache.py` — save/load
- [ ] `api/app.py` — ingest, open, save_paper_session args
- [ ] `tests/test_debone_quality.py`
- [ ] `mobile` — IngestQuality, banner, ungrounded badge
- [ ] `static/app.js` — warnings on debone=true

---

## 하지 않음 (본 칩)

- 전체 fail-closed → `split_into_sentences(full)` (2차 옵션만 문서화)
- 환각 문장 자동 삭제
- Body 섹션 제거·병합
- debone 모델/청크 크기 변경 (5000 유지)
- 사용자 주석 ([166](166-reader-annotations.md))

---

## 참고

- 설계 대화·벤치마크: LiquidText, MarginNote, PDF Expert, DBpia, Scholarcy/Hypothesis 레이어 분리
- Polar / Apple Books 교훈: 데이터 갇힘 방지 → warnings·export는 session/sidecar
