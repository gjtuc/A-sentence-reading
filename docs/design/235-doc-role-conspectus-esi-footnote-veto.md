# 235 — CONSPECTUS chrome veto + RSC ESI-footnote veto

Version: **0.3.232** · Status: **locked**  
Amends [229](229-acs-si-badge-chrome-veto.md) · [152](152-supplementary-merge.md) · [222](222-doc-role-detect-disk-honesty.md)

## Problem (phone folders · opened PDFs)

| File | Phone | Actual |
|------|-------|--------|
| `bimetallic-…ethane-activation` | SI (`head_marker`) | **main** — ACS Accounts chrome + **CONSPECTUS** (229 required only ABSTRACT) |
| `d4se00467a (1).pdf` | SI (`head_marker`) | **main** — RSC author footnote `† Electronic supplementary information (ESI) available. See DOI:` (PDF wraps so `_SI_HEAD` hits `supplementary` + `information`) |

True SI covers in the same folders (`an1c00673_si_001`, `d4se00467a1_suppl`, `ja6b11487_si_001`, Nature MOESM) must stay SI.

## Locked

When line-start / wrap SI marker matches, apply vetoes **in order** (py + Dart advisory):

1. **ACS chrome badge** (229) — chrome_hits ≥ 2 **and** soon after marker: `ABSTRACT` **or** `CONSPECTUS` (Accounts) → `main` / `head_marker_acs_chrome_veto`.
2. **RSC ESI availability footnote** — around match, phrase  
   `(†|*)? Electronic supplementary information (ESI)? available`  
   (whitespace/newlines flexible) → `main` / `head_marker_esi_footnote_veto`.
3. Else unchanged `supplementary` / `head_marker`.

### Non-goals

- Veto on `INTRODUCTION` alone
- Filename-only role
- Changing true ESI cover titles (`Electronic Supplementary Information for …` without `available`)
- Pairing / library migration

## Cache

Bump `kPdfAdvisoryCacheSchema` **v=4** so stale SI chips recompute.

## Tests

`tests/test_doc_role_conspectus_esi_235.py` · fixtures `K_acs_conspectus_chrome.txt`, `L_rsc_esi_footnote.txt` · 229 regressions green

## Version

**0.3.232**
