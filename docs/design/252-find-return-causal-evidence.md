# 252 — Find→browser→Downloads→resume causal evidence (overkill)

Version: **0.3.245** · Status: **locked**  
Amends [169g](169g-causal-handoff-evidence.md) · [242](242-pdf-import-find-watch.md) · [247](247-pdf-import-downloads-bridge.md) · [251](251-mate-direct-fetch.md)

## Why

User path: 「찾아보기」→ mate fallback browser → download (often **docx** SI) → return to app → **nothing visible**.

Existing kinds (`mate_fetch_*`, `pdf_find_watch_*`) exist, but **cannot prove** why resume offer was silent: timeout vs already_offered vs not_armed vs dialog busy. CamelCase enum `.name` in details is also **silently dropped** by evidence `_safeDetails`.

**Product UX auto-continue is deferred.** This chip densifies evidence first so the next UX patch is falsifiable.

## Hard constraints (unchanged)

- No DOI / URL / path / filename plaintext in evidence
- Details values: lowercase snake only (CamelCase / FQDN / MIME dropped)
- Allowlist both `evidence_kinds.py` + `evidence_kinds.dart`
- Do **not** shrink `FROZEN_KINDS` (add-only)
- No MES / silent Downloads MediaStore scan
- No CAPTCHA / paywall bypass

## Locked emit map

Join key: **`find_id`** = `hf_` + 12 hex (same id from mate start → arm → resume offer).

| Phase | Kind | Required details |
|-------|------|------------------|
| **E0** | (schema) | All `mode` / `code` / validate tokens **snake** (`too_large`, `fallback_browser`, …). Never raw Dart enum `.name`. |
| **E1** | `mate_fetch_start` · `mate_fetch_done` · `mate_fetch_fallback_browser` | Every early return emits a **terminal** (`done` or `fallback_browser`) with `code` ∈ `no_doi` · `mate_present` · `si_absent` · `validate_fail` · `sink_fail` · `killed` · `fallback` · … + `find_id` + `elapsed_ms` |
| **E2** | existing `pdf_find_watch_*` | Carry `find_id`; hit may include `file_kind` ∈ `pdf` · `docx` · `other` (ext bucket only) |
| **E3** | **`pdf_find_watch_resume_offer`** (new) | Every import-screen resume evaluation emits once: `outcome` ∈ `offered` · `skipped` · `accepted` · `declined`; if skipped: `skip_reason` ∈ `not_armed` · `already_hit` · `already_offered` · `dialog_open` · `busy` · `reanalyzing` · `opening` · `expired`; plus `find_id`, `armed`, `remaining_ms` |

Emit sites:

- `LibraryController.fetchMateForEntry` / `armFindWatch` / find-watch poll
- `PdfImportScreen._maybeOfferDownloadsPickAfterFind` (must record **skip** paths — proves silent return)

## Non-goals (this version)

- Auto-import Downloads file without user confirm
- Freezing new kinds into `FROZEN_KINDS` (E5 later after live pull proves useful)
- Host/CF buckets (E4 later)
- Changing find-watch window length or MES

## Later (not this ship)

| Phase | Scope |
|-------|--------|
| **E4** | `host_bucket` / `cf_signal` / downloads `new_n` after resume (no names) |
| **E5** | Rate caps; optional freeze of `pdf_find_watch_resume_offer` |
| **U\*** | UX auto-continue only after E3 pull shows timeout vs already_offered |

## Tests

`tests/test_find_return_evidence_252.py` — design locked · kinds mirrored · snake tokens in controller/screen · resume_offer skip branches present · version 0.3.245

## Version

**0.3.245**
