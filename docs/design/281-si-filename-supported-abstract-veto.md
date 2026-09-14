# 281 — SI filename: no `supported`; late SI phrase after ABSTRACT → main

Version: **0.3.276** · Status: **locked**  
Amends [280](280-filename-si-role.md) · [229](229-acs-si-badge-main.md)

## Why (phone folder audit, 58 files)

Four SAF folders on SD (`차헌 논문` / `은규 논문` / `차완 논문` / `박사님이 읽으라고 한 논문`):

1. **`revealing-…-on-supported-nickel-….pdf`** (메인, 11MB) and **`cs9b00733_si_001.pdf`** (SI) both showed **추정 SI**.  
   Cause: `_SI_FILENAME` matched bare `sup`/`supp` inside **`supported`** / **`support`**.
2. **`am2c04149.pdf`** (메인) tagged **추정 SI** via `head_marker` — text is *“…found in the Supporting Information.”* **after ABSTRACT**, not an SI cover.

Other SI tags in the four folders matched PDF/docx covers (`_si_`, `mmc`, `suppl`, `MOESM`, `.som`, `supplementary`).

## Locked product

1. Tighten filename SI regex: require `suppmat` / `suppl` / `sup-N` / `_si_` / `mmcN` / `moesm` / `.som` — **not** bare `sup` inside `supported`.
2. If ABSTRACT/CONSPECTUS appears **before** the SI head marker and filename is not SI → **`main`** / `head_marker_after_abstract_veto`.
3. Bump `kPdfAdvisoryCacheSchema` → **17**.
4. Dart + Python twins.

## Non-goals

OCR · rewriting ACS chrome veto · pairing/merge.

## Tests

- `…-supported-nickel-….pdf` + article head → **main** (no filename_si)
- `cs9b00733_si_001.pdf` still **supplementary**
- ABSTRACT then mid-body “Supporting Information” → **main** / `head_marker_after_abstract_veto`
- Real SI cover (`S-1 Supporting Information` before abstract) still **supplementary**
- Schema 17 · **0.3.276**

## Ship

**0.3.276**
