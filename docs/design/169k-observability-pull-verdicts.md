# 169k — Observability pull + linked verdicts

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) · [169j-translate-on-item-off-critical-path.md](169j-translate-on-item-off-critical-path.md)  
**Status:** **0.3.136** — K0 + K1(I3 partial) + K2(I4 patch_gen) + K3(zombie abort) + ghost FGS(170); K4 pull verdict script pending  
**UI:** 없음 (에이전트 pull·track만)

---

## 0. Why now (live 2026-09-02)

| 관측 | 의미 |
|------|------|
| **169j pass** | title `harmonize` → `pool_tick` ≤5s, introduction→methods `section_done` 진행 |
| **`worker_lost` @ 90%** | sweeper lease 만료 → `server_job_terminal_error` — **169j와 별 클래스** |
| **zombie worker** | terminal **후에도** harmonize evidence 계속 (`job_58b02834ce38`) |
| **track false positive** | harmonize pool 병렬 `call_start` → `hang_suspect` 오탐 |
| **169i 미완** | I3 figure `preserve_miss` locator · I4 `session_patch_ko` gen 조인 |

목표: **pull 한 번 + track 한 번**으로 에이전트가 “169j 통과 / worker 손실 / figure 유실 / stale open”을 **규칙으로** 말하게 한다.

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| K-J1 | 사용자 진단 UI 금지 유지 — verdict는 **스크립트 stdout + evidence JSONL** only |
| K-J2 | 본문·PNG 금지 (169 P5). locator·hash16·파일명·건수만 |
| K-J3 | `.tmp_*` 는 실험; **SoT = `scripts/track_translate.py` + `llm/track_verdict.py`** |
| K-J4 | 169j acceptance = **코드화된 verdict** (`accept_169j_title`) — 사람이 pool_end만 눈으로 보지 않음 |
| K-J5 | `worker_lost` 와 `on_item` stall 은 **분리 verdict** |
| K-J6 | figure I3 / patch I4 는 **169i 칩 계속** (169k가 대체하지 않음) |

---

## 2. Architecture

```text
[phone adb UI] ──┐
                 ├── scripts/track_translate.py ──► .tmp_track_latest.txt
[pull_evidence] ─┘              │
                                ▼
                    llm/track_verdict.py (pure rules)
                                │
                    scripts/evidence_verdict.py (169i §5 rules, K4)
```

---

## 3. Implementation phases

| Phase | 내용 | 파일 |
|-------|------|------|
| **K0** | track 승격 + verdict engine (`zombie_worker`, `accept_169j_title`, pool-active) | `scripts/track_translate.py`, `llm/track_verdict.py`, tests |
| **K1** | 169i **I3** — `figure_preserve_miss.missing_locators[]` + preserve 성공 sample fingerprint | `cache/paper_cache.py` |
| **K2** | 169i **I4** — `session_patch_ko` derive on writer flush; checkpoint `patch_gen` | `progressive_writer.py`, `artifact_ids.py` |
| **K3** | worker lifecycle — `checkpoint=job_terminal` before fail; sweeper `lease_expired` detail; zombie suppress | `api/app.py` ingest_stall |
| **K4** | Pull rule pack — `preserve_gap`, `stale_open`, `hash_break` as pytest + CLI | `scripts/evidence_verdict.py` |
| **K5** | 유령 upload FGS · orphan list | **별 칩 170** (non-goal here) |

한 phase = 버전 bump 가능. K0–K1은 floor **추가만** (kind 삭제 없음).

---

## 4. Verdict catalog (K0)

| verdict | 조건 |
|---------|------|
| `accept_169j_title` | title harmonize `call_done` → `pool_end` or `pool_tick remaining=0` ≤5s |
| `fail_169j_title` | harmonize done, pool_end 없음 |
| `harmonize_pool_active` | open harmonize + `pool_tick` <90s → hang 오탐 억제 |
| `worker_lost_terminal` | `server_job_terminal_error` reason `worker_lost` |
| `zombie_worker` | terminal **후** 동 job translate/checkpoint >0 |
| `translate_phase_exit_ok` | phase exit ok |
| `post_call_stall` | high-% + 120s silence after last `call_done` |

---

## 5. Agent workflow (after K0–K4)

1. `python scripts/track_translate.py` (또는 loop tick)
2. verdict에 `accept_169j_title` → 169j ship OK for title hop
3. `worker_lost_terminal` + `zombie_worker` → K3 (lease/sweeper), 169j 회귀 아님
4. `preserve_gap` / `figure_preserve_miss` + `missing_locators` → I3 figure path
5. `stale_open` → I1 hash chain / upload skip

---

## 6. Acceptance

### K0
- [ ] `tests/test_track_verdict.py` — zombie + 169j pass/fail synthetic
- [ ] live job replay: `job_58b02834ce38` → `zombie_worker` + `accept_169j_title`

### K1 (I3)
- [ ] reanalyze 0 prior PNG → `missing_locators` non-empty
- [ ] preserve from prior → sample `artifact_observe` or details fingerprint

### K2 (I4)
- [ ] writer flush → `artifact_derive session_patch_ko` with gen
- [ ] hang at `on_item_exit` + patch gen → same wall-clock join in pull

---

## 7. Non-goals

- Admin UI · Settings 진단 타일  
- Datadog / OpenLineage collector  
- 169j writer 재작업  
- Cloud Run worker count bump only  

---

## 8. Related

- [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) §5 읽기 규칙  
- [169-audit-checklist.md](169-audit-checklist.md)  
- [168-ingest-observability.md](168-ingest-observability.md)  
