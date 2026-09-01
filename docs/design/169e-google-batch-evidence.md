# 169e — Google batch translate evidence

**Parent:** [169c-dense-translate-open-auth.md](169c-dense-translate-open-auth.md)  
**Version:** 0.3.126+  
**UI:** 없음 (에이전트 `pull_evidence.py` 전용)

---

## 1. Why

Google path (`translate_batch_en_to_ko`) can block for many minutes with **zero** `translate_item_done` until the whole section batch returns. 169c only timed Gemini/`translate_one`, so 95% «섹션 번역…» stalls looked like “no movement” without proving whether Translation API was hanging, slow, or never started.

---

## 2. New / extended kinds

| kind | when | details |
|------|------|---------|
| `translate_call_start` | before section batch **and** each API chunk (≤128) | `call_kind`=`google_batch`\|`google_chunk`, `batch_n`, `section?`, `chunk_i`/`chunk_n` for chunks |
| `translate_call_done` | after batch/chunk returns | same + `elapsed_ms` |
| `translate_call_slow` | batch/chunk ≥ 60s | same |
| `translate_call_fail` | exception | + `exc_type` |

Section wrapper: `_google_batch_timed` in `translate_section.py`.  
Chunk sensors: inside `translate_google.translate_batch_en_to_ko`.

---

## 3. Agent pull

```bash
python scripts/pull_evidence.py --since 2h --kind translate_call_start,translate_call_done,translate_call_slow,translate_call_fail,translate_item_done,translate_phase_enter,translate_phase_exit --job <job_id>
```

### Success read

1. `phase_enter` → `call_start` (`google_batch`, `batch_n`) within seconds  
2. Chunk progress: `google_chunk` start/done with rising `chunk_i`  
3. Hang = last `call_start` with no matching `call_done`/`fail`  
4. Slow but alive = `call_slow` then `call_done`

---

## 4. Non-goals

- Progressive mid-translate cache write  
- Speeding Google/Gemini itself  
- Web evidence UI  
