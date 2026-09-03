# 169p — Shadowing practice evidence + detection (pre-fix)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md) · [169k-observability-pull-verdicts.md](169k-observability-pull-verdicts.md)  
**Product surface (read-only):** [79](79-shadowing-opt-in.md)–[82](82-shadowing-practice-loop.md), [113](113-shadowing-chunk-budget.md), [119](119-shadowing-chunks-build-failclosed.md)  
**Status:** **0.3.144** — P0–P4 sensors + floor + track/verdict shipped; product prep-stuck fix = **next** chip after live verdict  
**UI:** 없음 (에이전트 pull · track · verdict only)  
**Next product chip:** only after first live classifiable verdict

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| P-J1 | 「연습 구간 준비 중…」은 TTS/mic가 아니라 **chunk plan `status≠ok`** 대기. 제품 수정 전에 **게이트·빌드·부팅**을 evidence로 분류한다. |
| P-J2 | 본문·chunk 텍스트·녹음 **금지** (169 P5). `cache_id` · `status` · `error` · counts · `elapsed_ms` · `round` · `sentence_id` **hash16** · kill/pref bool만. |
| P-J3 | 제품 fail-closed (pending≠ok, 40-slice cap, budget) **동작 변경 없음** — emit만. |
| P-J4 | Floor **추가만** (169g). 센서 삭제·축소 배포 금지. |
| P-J5 | 제품 버그 수정은 **별 칩**. 이 칩 acceptance = live에서 classifiable verdict 1회. |

---

## 1. Why (blind spot)

Allowlist에 `pref_shadowing_set`만 있고 아래가 없다:

- practice `_boot` / `ensureShadowingChunks`
- GET/POST `/api/shadowing/chunks…`
- `build_chunk_plan` Gemini start/done
- gate (`shadowing_disabled`, `practice_off`, …)
- plan ok인데 현재 문장 `chunk_n=0` (sid bind miss)

→ 폰이 「준비 중」에 머물러도 JSONL로 169g식 분류 불가.

---

## 2. Causal chain

```text
pref/kill → reader_open → ensure_chunks → chunks_GET
                └─ not ok → chunks_POST_build → gemini_chunk → gcs_save → (continue)
ensure/boot → status==ok → listen/speak/take
```

| from → to | Prove |
|-----------|--------|
| pref_on → ensure_start | open+opt-in이 ensure를 시작했는지 |
| ensure → chunks_get | 클라 API 도달 |
| get not ok → build | backfill |
| build → gemini → save | pending vs hang |
| plan_ok → boot_done | UI가 preparing을 떠났는지 |
| boot → tts/mic/take | loop (secondary) |

---

## 3. Evidence kinds

### 3.1 Client

| kind | When | details |
|------|------|---------|
| `shadowing_gate` | entry/ensure refuse | `gate`=`kill_off`\|`pref_off`\|`no_session`\|`no_cache_id`, `server_flag`, `pref` |
| `shadowing_ensure_start` / `shadowing_ensure_done` | `LibraryController.ensureShadowingChunks` | `cache_id`, `ok`, `plan_status`, `rounds`, `error_code?`, `elapsed_ms` |
| `shadowing_boot_start` / `shadowing_boot_done` | `ShadowingPracticeScreen._boot` | + `chunk_n`, `sentence_id_h16` |
| `shadowing_build_round` | each client POST build | `round`, `plan_status`, `continue`, `http_ok`, `error?` |
| `shadowing_loop_event` | after plan ok | `phase`=`tts`\|`mic_start`\|`mic_stop`\|`take_post`\|`skip`, `ok`, `exc_type?` |

Reuse `client_api_fail` / `client_api_timeout` with route `shadowing/chunks|build|takes`.

### 3.2 Server

| kind | When | details |
|------|------|---------|
| `shadowing_chunks_get` | GET handler | `plan_status`, `sentence_n`, `progress_done`/`total`, `error?` |
| `shadowing_chunks_build_start` / `shadowing_chunks_build_done` | POST build | `continue`, `plan_status`, `error?`, `elapsed_ms`, `budget_s` |
| `shadowing_gemini_call_start` / `shadowing_gemini_call_done` | `plan_sentence_chunks` | `call_kind`=`chunk_plan`, `ok`, `elapsed_ms`, `exc_type?` |
| `shadowing_ingest_stage` | ingest want_chunks | `job_id`, `plan_status`, `warning?` |

---

## 4. Verdict catalog

SoT: `scripts/track_shadowing.py` · `llm/shadowing_verdict.py`

| verdict | Rule |
|---------|------|
| `gate_kill_off` | gate=kill_off |
| `gate_pref_off` | gate=pref_off |
| `ensure_pending_long` | ensure_start w/o done > N s OR last build still pending |
| `build_cap_hit` | done error implying 40 rounds / cap message code |
| `build_api_fail` | error ∈ {gemini_unavailable, gcs_pull_failed, paper_not_found, practice_off, shadowing_disabled, build_failed} |
| `server_gemini_hang` | gemini_call_start w/o done > budget+slack |
| `plan_ok_chunk_empty` | boot_done `chunk_n=0` with plan_status=ok |
| `sid_bind_miss` | plan ok, sentence_n>0, chunk_n=0 for bound sentence |
| `prep_ui_stuck` | boot_start, no boot_done, silence >120s, no terminal gate/api |
| `accept_prep_ok` | boot_done ok + chunk_n≥1 |
| `loop_mic_fail` / `loop_tts_fail` | after accept_prep_ok |

**Agent rule:** class **prep** vs **loop** before proposing a product patch.

---

## 5. Phases

| Phase | Content |
|-------|---------|
| P0 | This doc + README index |
| P1 | Allowlist + mobile emits + tests |
| P2 | Server GET/POST/build/ingest + Gemini start/done |
| P3 | track_shadowing + shadowing_verdict + pytest |
| P4 | Floor add-only + version bump + deploy; live pull **before** product fix |

---

## 6. Acceptance

- One practice open on live → classifiable verdict (not silence).
- `check_evidence_floor.py` exit 0; no frozen-kind removal.
- Product fix for prep-stuck = **next** chip only.

## 7. Non-goals

- Changing pending≠ok / budget / 40-cap behavior
- Speech scoring / transcripts
- Web shadowing.js sensors (mobile-first; web Later)
