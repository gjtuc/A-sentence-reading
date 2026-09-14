# 280 — Filename SI hint alone → advisory supplementary

Version: **0.3.273** · Status: **locked**  
Amends [222](222-doc-role-detect-disk-honesty.md) · [228](228-pdf-advisory-title.md) · [277](277-advisory-title-wrap-join.md)

## Why

After 277 (cache schema 13 wipe + better SI cover titles), import showed **`cs9b00733_si_001.pdf` as 「추정 메인」**.  
Role gate required filename SI **plus** page-label / Table S / docx — PDF SI with only `_si_`/`mmc`/`MOESM` fell through to `default_main`. Improved titles made them look like mains and blocked 1+1 sets.

## Locked product

1. Dart `detectDocRoleDetailed` **and** Python `detect_doc_role_detailed` (twins): after existing dual gates, if `filenameLooksLikeSi` / `filename_looks_like_si` → **`supplementary`**, reason **`filename_si`**.
2. Keep ACS chrome / ESI footnote **main vetoes** on head markers (unchanged order before filename-only).
3. Bump `kPdfAdvisoryCacheSchema` **13 → 14** so import roles refresh.
4. No title/path/DOI in evidence; existing `doc_role_detect_*` reasons tokenize `filename_si`.

## Non-goals

Auto-merge · changing set 1+1 rule · OCR · weakening ACS main badge veto.

## Tests

- `cs9b00733_si_001.pdf` + article-title-only head → supplementary / `filename_si`
- `-main.pdf` without SI hints stays main
- Existing docx / table_fig / page_label reasons unchanged
- Schema 14 · version **0.3.273**

## Ship

**0.3.273**
