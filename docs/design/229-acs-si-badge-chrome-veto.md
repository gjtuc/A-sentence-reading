# 229 — ACS main SI-badge chrome veto

Version: **0.3.227** · Status: **locked**  
Amends [152](152-supplementary-merge.md) · [222](222-doc-role-detect-disk-honesty.md) · [228](228-pdf-folder-advisory-preview.md)

## Problem

ACS main PDF page-1 chrome (`ACCESS` / `Metrics & More` / `Article Recommendations` / `sı`) plus line-start **Supporting Information** immediately before **ABSTRACT** was classified `supplementary` via `head_marker` (phone: `acsanm.1c00673.pdf`).

True SI covers (`S-1` + Supporting Information + title/authors, no ACS chrome / ABSTRACT) must stay `supplementary`.

## Locked fix

In `detect_doc_role_detailed` (Python) and Dart `detectDocRoleDetailed` (advisory):

- Keep 222 order (override → strip → empty → marker → filename+S-n → default).
- When line-start SI marker matches, if **ACS chrome badge** → `role=main`, `reason=head_marker_acs_chrome_veto`, `marker_hit=True`.
- Else unchanged `supplementary` / `head_marker`.

### ACS chrome badge (narrow)

Around marker match `m`, window `head[m.start-400 : m.end+250]`:

- Count distinct hits among: line-start `ACCESS`, `Metrics & More`, `Article Recommendations`, lone-line `sı` (dotless i).
- `abstract_soon`: in `head[m.end : m.end+300]` match `ABSTRACT:` or line-start `ABSTRACT`.
- Badge iff **chrome_hits ≥ 2 AND abstract_soon**.

Do **not** veto on ABSTRACT alone or a single chrome token.

## Client cache

`pdf_advisory_cache` schema **v: 2** — wipe/ignore v1 entries so stale estimated-SI chips clear.

## Ops (no auto-migration)

Rows already ingested as wrong `supplementary` can soft-pair with a corrected main after re-upload. **Delete the wrong library row** (or reanalyze that corrects role) before re-upload. Auto migration is out of scope.

## Non-goals

- ABSTRACT-alone veto
- Filename-only role
- Pairing/merge logic changes
- LLM/vision reclassify
- Wiley/Elsevier chrome sets (later)
- Large PDF binaries in git fixtures

## Tests

`tests/test_acs_si_badge_veto_229.py` · fixtures A–J · 222 regressions still green

## Evidence

Reuse `doc_role_detect_*` — new `reason` value only; no new kinds.

## Version

**0.3.227**
