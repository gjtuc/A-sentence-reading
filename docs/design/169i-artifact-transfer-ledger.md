# 169i — Artifact transfer ledger (조각 주는/받는 장부)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md)  
**Sibling / prerequisite:** [169h-interior-checkpoint-evidence.md](169h-interior-checkpoint-evidence.md) (**먼저** — 시간축 내부)  
**Status:** I0–I2 implemented in **0.3.134** (session hash chain + delete invalidate; figures sample later)  
**UI:** 없음  
**Depends on:** 169h H0–H2 live (0.3.133+)

---

## 0. Locked product judgment (2026-09-01)

| # | Judgment |
|---|----------|
| I1 | 169g J1: 지금은 **점 + job/cache 사후 조인**이다. **주는/받는 주체 동시 스냅샷·변환 그래프는 없다.** 본 칩이 그 그래프다. |
| I2 | **Lineage** = 조각이 어디로 흐르는지. **Provenance** = 누가·어떤 activity·어느 버전으로. 업계: OpenLineage Job/Run/Dataset, W3C PROV Entity/Activity/Agent. ASR는 풀 표준 도입이 아니라 **같은 계약을 evidence JSONL로**. |
| I3 | 본문·PDF·캡션·음성 원문 **금지** (169 P5). 남기는 것: `locator`, `artifact_kind`, `content_hash`, `bytes_n`, `gen`, `ok`, 건수. |
| I4 | Blob은 **기존 GCS/로컬에 그대로** 두고, 장부는 **메타 그래프만** ([GLaaS 패턴](https://treqs.ai/glaas): hash로 가리킴). |
| I5 | 번역 스톨의 **첫 원인 탐지**는 169h. 본 칩은 I/O·캐시·open stale·그림 유실·삭제 orphan·merge 승자에 필요. `on_item` hang이면 h↔i 조인. |
| I6 | Floor = **추가만**. Phase마다 kind append. |

---

## 1. Why (점 센서로 안 보이는 버그 클래스)

| 증상 | 169g/h만 | 169i가 답하는 것 |
|------|----------|------------------|
| open 시 KO 0 | `open_ko_summary` | 읽은 session **gen/hash** ≠ save hash? |
| reanalyze 그림 증발 | `figure_preserve_miss` | **어느 fig locator**가 prior 0인가 |
| 삭제 후 잔존 | `object_n` 합 | session vs fig별 invalidate + orphan |
| merge 이상 | ops `merge_session_richer` 건수 | local vs remote **어느 hash가 이겼나** |
| “번역 됐는데 폰에 없음” | phase_exit | save gen이 upload/download 체인에 있나 |

업계: lineage로 upstream 추적 ([Datadog lineage](https://www.datadoghq.com/blog/data-lineage/)), provenance로 inspectable history ([Rowset](https://rowset.lvtd.dev/blog/data-provenance-ai-agents), [W3C PROV](https://www.w3.org/TR/prov-primer/)).

---

## 2. Object model

### 2.1 Mapping

| OpenLineage / PROV | ASR evidence |
|--------------------|--------------|
| Dataset / Entity | artifact (`artifact_id`, kind, hash, locator) |
| Job / Activity | `activity` enum (아래) |
| Run | `job_id` + `trace_id` |
| Agent | `agent` = `cloud_run` \| `mobile` \| `worker` (+ `owner_uid` 조인) |
| inputs/outputs | `from_locator` / `to_locator` on `artifact_transfer` |
| wasDerivedFrom | `artifact_derive.parent_ids` |
| invalidation | `artifact_invalidate` |

### 2.2 `artifact_kind` allowlist

```
session_json
figure_png
source_pdf
source_docx
index_json
voice_blob
notes_store
upload_blob
job_state
```

### 2.3 Locator 문법

```
local:papers/{cache_id}/session.json
local:papers/{cache_id}/figures/{file}
local:papers/{cache_id}/source.pdf
gcs:papers/{cache_id}/session.json          # uid prefix는 emit 시 서버가 해석; details엔 논리 path
gcs:papers/{cache_id}/figures/{file}
gcs:index
mem:job/{job_id}
mobile:open/{cache_id}                      # 폰이 들고 있는 열린 세션 버퍼 (hash만)
```

- `cache_id` / file명은 기존 sanitize 규칙.  
- **실버킷·실 uid 경로 전문을 evidence에 장황히 넣지 말 것** (논리 locator + `owner_uid` 필드).

### 2.4 Identity

| 필드 | 규칙 |
|------|------|
| `artifact_id` | `art_{kind_short}_{cache_id}_{gen}` 또는 fig는 `art_fig_{cache_id}_{file_stem}_{gen}` |
| `content_hash` | sha256 hex **앞 16자** (전체 64 저장 금지 의무는 없으나 로그 폭 위해 16 권장) |
| `bytes_n` | int |
| `gen` | session save마다 +1; fig는 파일 write마다 +1 |
| `parent_ids` | derive 시만 |

같은 바이트 → 같은 hash (content-addressing). `hash_mismatch` = 복사 실패·잘못된 merge 센서.

---

## 3. Events (kinds)

| kind | 언제 | details (요지) |
|------|------|----------------|
| `artifact_observe` | 읽기 직전/직후 | `locator`, `artifact_kind`, `content_hash`, `bytes_n`, `role=read`, `gen?` |
| `artifact_transfer` | 복사·upload·download·patch write | `transfer_id`, `activity`, `from_locator`, `to_locator`, `content_hash`, `bytes_n`, `ok`, `elapsed_ms`, `agent` |
| `artifact_derive` | 새 session gen, fig 생성 | `parent_ids`, `child_id`, `activity`, `gen` |
| `artifact_invalidate` | delete·tombstone | `locator`, `artifact_kind`, `ok`; 배치 시 `object_n`/`figure_n` + 샘플 locators |

기존 점과 **조인** (대체 금지):

- `translate_save_ko`, `open_ko_summary`, `figure_preserve_miss`, `download_cache_fail`, `paper_delete`, delete stats  
- 가능하면 같은 `transfer_id` 또는 `content_hash`/`gen`을 details에 복사

### 3.1 `activity` allowlist (초기)

```
client_upload
ingest_store
vision_write_session
vision_write_figure
gcs_upload_session
gcs_upload_figure
gcs_download_session
gcs_download_figure
merge_session
session_patch_ko
translate_save
cache_open
figure_window
notes_upsert
voice_put
paper_delete_local
paper_delete_gcs
index_update
```

### 3.2 Sampling (비용)

| kind | 정책 |
|------|------|
| `session_json` | **항상** transfer/observe on save/upload/download/open |
| `figure_png` | 실패·mismatch·preserve_miss·delete **전체**; 성공은 first/last 또는 `fig_hash_fingerprint` 하나 |
| `source_*` | upload/download/delete만 |
| `voice_blob` / notes | put/delete만 (내용 X) |

---

## 4. Lifecycle graph (구현 체크리스트)

```text
upload_blob
  → vision_write_session + vision_write_figure(s)
  → gcs_upload_session + gcs_upload_figure(s)   [hash match]
  → session_patch_ko / translate_save           [gen bump, derive]
  → gcs_upload_session (vN)
  → gcs_download_* + cache_open observe         [stale 검사]
  → figure_window (sample)
  → notes/voice (optional)
  → paper_delete_* invalidate + orphan check
```

### 4.1 Emit 위치 (코드 지도)

| activity | 파일 (개념) |
|----------|-------------|
| vision_write_* / translate_save / derive | `cache/paper_cache.py` `save_paper_session` |
| gcs_upload_* / merge | `llm/papers_gcs.py` `upload_paper_cache` |
| gcs_download_* | `papers_gcs.py` `download_paper_cache` |
| cache_open observe | `api/app.py` open 경로 + 기존 `open_ko_summary`에 `gen`/`hash` 필드 |
| figure_window | 기존 req/res에 bytes_n·hash 샘플 |
| preserve_miss | 기존 kind + missing prior locators[] |
| delete invalidate | `delete_paper_cache_stats` + local `delete_cached_paper` |
| session_patch_ko | translate `on_item` → save 경로 (169h callback과 동일 wall-clock) |

---

## 5. 읽기 규칙 (에이전트)

```
orphan_write = artifact_transfer start-equivalent without ok end (>N s)
hash_break   = claimed ok copy AND from.hash != to.hash
stale_open   = open observe.hash != latest translate_save/upload hash for cache_id
preserve_gap = figure_preserve_miss AND no successful observe of prior fig locators
delete_leak  = invalidate session ok but later observe still finds gcs fig
ghost_read   = open_ko_summary ko_n>0 without download/open observe for that gen
```

169h 조인:

```
callback_hang + orphan_write(activity=session_patch_ko) → I/O 원인 확정
```

---

## 6. Implementation plan (강제 순서)

**169h H0–H1 이후 시작.** 버전 bump 규칙 동일 (155).

### Phase I0 — Schema + helpers

| 파일 | 변경 |
|------|------|
| `evidence_kinds.py` + Dart | 4 kinds 추가 |
| `llm/artifact_ids.py` *(신규 소형)* | hash16, locator format, artifact_id builder |
| `evidence_floor.py` | frozen append |
| tests | hash/locator unit |

### Phase I1 — Session E2E chain

local `save_paper_session` → `gcs_upload` → `gcs_download`/`cache_open` observe  
Acceptance: 한 `cache_id` pull 시 **hash 체인 3단** 연결.

### Phase I2 — Delete invalidate + orphan

`delete_paper_cache_stats` / local delete → per-kind invalidate; 이후 list로 leak 규칙.

### Phase I3 — Figures sample + preserve_miss edges

preserve_miss에 `missing_locators` (파일명만) + 성공 fig fingerprint.

### Phase I4 — Translate patch gen + 169h 조인

`session_patch_ko` / `translate_save` derive; callback hang 시 transfer 조인.

---

## 7. Non-goals

- OpenLineage Collector / Marquez / 사용자 lineage UI  
- 모든 figure 매 write full transfer (비용)  
- evidence에 PNG/PDF 바이트 첨부  
- 169h checkpoint를 artifact로 위장  
- Datadog  

(선택 후순위: evidence → OpenLineage JSON **export 스크립트만**.)

---

## 8. Agent workflow

1. 데이터 유실·stale·삭제 이슈: pull `artifact_*` + 기존 save/open/delete kinds  
2. hash 체인 끊긴 hop = 원인 구간  
3. 번역 **시간** 스톨은 여전히 169h 먼저  
4. 센서 삭제 금지  

---

## 9. Acceptance

### I0

- [ ] kinds in py+dart + floor; 제거 시 floor fail  

### I1

- [ ] live: 동일 `cache_id`에 save hash → upload hash → open observe hash 일치 체인  
- [ ] 고의로 local만 바꾸고 upload 스킵한 재현에서 `stale_open` 규칙으로 탐지 가능  

### I2

- [ ] delete 후 `artifact_invalidate` + orphan 0 (또는 leak 규칙 hit)  

### I3–I4

- [ ] preserve_miss에 locator 힌트  
- [ ] patch/save gen이 open과 조인  

---

## 10. Related

- [169h-interior-checkpoint-evidence.md](169h-interior-checkpoint-evidence.md)  
- [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md)  
- [169-agent-evidence-bus.md](169-agent-evidence-bus.md) (P5 본문 금지)  
- [169d-full-product-evidence.md](169d-full-product-evidence.md)  
- [155-deploy-live-guard.md](155-deploy-live-guard.md)  
- OpenLineage object model · W3C PROV primer (외부)  
