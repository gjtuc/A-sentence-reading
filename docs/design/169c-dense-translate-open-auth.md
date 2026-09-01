# 169c — Dense evidence (translate / open / auth)

**Parent:** [169-agent-evidence-bus.md](169-agent-evidence-bus.md) · [169-audit-checklist.md](169-audit-checklist.md)  
**Version:** 0.3.124+  
**UI:** 없음 (에이전트 `pull_evidence.py` 전용)

---

## 1. Why

169a/b만으로는 Co–TiO₂류에서 **번역이 문장 KO를 냈는지**, **open이 캐시에서 KO 몇 개를 읽었는지**, **액세스/auth가 어느 route에서 타임아웃인지**를 JSONL에 못 박는다.

---

## 2. New kinds

| kind | source | when | details (snake) |
|------|--------|------|-----------------|
| `translate_phase_enter` | server | stage→translate | `want_translate`, `sentence_n`, `figure_n`, `backend` |
| `translate_item_done` | server | `_on_item` sample | `item_kind`, `index`, `stage`, `ko_len`, `ko_sentence_n`, `ko_figure_n` |
| `translate_call_fail` | server | Gemini/Google exception | `call_kind`, `exc_type` |
| `translate_call_slow` | server | generate ≥ 60s | `call_kind`, `elapsed_ms` |
| `translate_phase_exit` | server | enrich return / fail | `ok`, `ko_sentence_n`, `ko_figure_n`, `warn_n` |
| `translate_save_ko` | server | post-translate save | `ko_sentence_n`, `ko_figure_n` |
| `open_ko_summary` | server | `cache_open` | `sentence_n`, `ko_sentence_n`, `figure_n`, `ko_figure_n`, `translate_pending`, `backfill_spawned`, `translate_poll` |
| `translate_poll_start` | mobile | KO poll start | cache_id field |
| `translate_poll_ko` | mobile | poll when KO count changes | `ko_sentence_n`, `translate_pending`, `attempt` |

Auth/access timeouts reuse `client_api_timeout` with **stable `route`** (`auth_status`, `access_status`, …).

### Sampling

- `translate_item_done`: `index==0` or `index%5==0` or `stage==harmonize`
- `translate_call_slow` / `translate_call_fail`: always
- Rate limit: existing evidence bus 60/min

---

## 3. Agent pull

```bash
python scripts/pull_evidence.py --since 2h --kind translate_item_done,translate_call_fail,translate_call_slow,open_ko_summary,translate_poll_ko,client_api_timeout,stall_fired,translate_phase_enter,translate_phase_exit,translate_save_ko
```

### Success read

1. `translate_phase_enter` present after ingest with translate on  
2. First KO: `translate_item_done` **or** hang: only lease/gcs_push + maybe `translate_call_slow`/`fail`  
3. Phone 「번역 준비 중」 ↔ `open_ko_summary.ko_sentence_n==0`  
4. Access gate 20s ↔ `client_api_timeout` route=`access_status`

---

## 4. Non-goals (this chip)

- Progressive mid-translate **cache write** (product fix later)  
- Web evidence (169e)  
- Admin/user UI  
