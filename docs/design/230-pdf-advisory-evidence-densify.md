# 230 — PDF folder advisory / hash evidence densify

Version: **0.3.228** · Status: **locked**  
Depends: [226](226-pdf-folder-import-browser.md) · [228](228-pdf-folder-advisory-preview.md) · [229](229-acs-si-badge-chrome-veto.md)  
Amends: 228 evidence floor (aggregates only)

## Problem

Folder import advisory failures look like “not recognizing” papers, but sensors were too thin:
silent busy skip, no remaining-unknown counts, no reason/code/`title_source` histograms.
Phone measured advisory cache ≪ hash cache with no causal explanation.

## Locked this ship

| Include | Exclude |
|---------|---------|
| `pdf_advisory_pump_skip` (busy / empty_pending) | URI / path / displayName / title / head in evidence |
| Densify `pump_start` / `pump_done` histograms | Journal pattern packs (CONSPECTUS / RSC ESI wrap) |
| Enrich miss/hit: `head_len`, `page_count`, `truncated`, `title_source` | OCR / Gemini / MediaStore |
| `pdf_hash_pump_start` / `pdf_hash_pump_done` | Scroll auto-pump product change |
| Enrich `pdf_folder_scan_done` ready/unknown counts | Recent-strip removal (separate UX) |
| `guessAdvisoryTitle` → `(title, title_source)` | Enqueue gate on advisory |
| Additive `title_source` on advisory cache (no forced wipe) | Putting titles in `message` |

## INVARIANT

1. Evidence details = ints/bools + snake enum strings only (`_safeDetails`).
2. Keep 228: `empty_head` → advisory **main**; never filename-only SI.
3. Green = full SHA-256 only; independent of advisory.
4. Wire upload name = SAF `displayName`.
5. Prefer extending pump aggregates over many micro-kinds.
6. Do not remove 226/228 kinds from allowlists.
7. Densify diagnoses **pipeline**; pattern diversity is later chips.
8. Logout still wipes grant + hash + advisory together.

## Evidence kinds (new)

- `pdf_advisory_pump_skip`
- `pdf_hash_pump_start`
- `pdf_hash_pump_done`

Existing kinds densified in place (`pump_start`/`done`, cache hit/miss/fail, `scan_done`).

### pump_done counters (ints)

- `n_ok`, `n_fail`, `n_hit`, `n_miss`, `n_cancelled`, `n_unknown_left`, `n_failed_left`, `n_ready_left`, `elapsed_ms`
- `n_reason_<snake>`, `n_code_<snake>`, `n_title_src_info|head_line|stem|unknown`

## Tests

`tests/test_pdf_advisory_230.py`

## Version

**0.3.228**
