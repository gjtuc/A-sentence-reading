# 233 — Skip journal chrome lines in advisory title guess

Version: **0.3.230** · Status: **locked**  
Amends [228](228-pdf-folder-advisory-preview.md) · [230](230-pdf-advisory-evidence-densify.md)

## Problem

`guessAdvisoryTitle` took the first `looksLikePaperTitle` line. IOP/RSC covers put **journal name** or **Cite this:** before the real title (e.g. `Journal of Physics D…`, `Cite this: Catal. Sci. Technol.…`).

## Locked

Reject (skip) Info.Title and head lines that match chrome, then continue scanning:

- Exact (ci): `PAPER`, `REVIEW`, `Article`, `Research` (and close variants)
- Starts with: `Cite this`, `Cite This`, `To cite this`, `DOI:`, `Received `, `Accepted `
- Journal / brand patterns: `Journal of …`, `Catal. Sci.`, `Catalysis Science`, `nature catalysis`, `www.` hosts, `Green Chemical Engineering`, etc.
- Lines that are mostly a journal abbreviation cite blob

Bump advisory cache schema **v=3** so stale journal-as-title rows recompute.

## Non-goals

- Full bibliographic parser / Crossref
- Changing SI detect (229/231)

## Tests

`tests/test_pdf_advisory_title_chrome_233.py` (+ fixtures for IOP/RSC heads)

## Version

**0.3.230** (regexp crash fixed in [234](234-advisory-title-dart-regexp-fix.md) / **0.3.231**)
