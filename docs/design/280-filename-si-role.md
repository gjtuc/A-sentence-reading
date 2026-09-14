# 280 — Filename SI hint alone → advisory supplementary

Version: **0.3.275** · Status: **locked**  
Amends [222](222-doc-role-detect-disk-honesty.md) · [228](228-pdf-advisory-title.md) · [277](277-advisory-title-wrap-join.md)

## Why

After 277 (cache schema wipe + better SI cover titles), import showed **`cs9b00733_si_001.pdf` as 「추정 메인」**.

Causal layers (phone-verified):

1. PDF role required filename SI **plus** page-label / Table S / docx → else `default_main`.
2. ACS chrome / ESI footnote **main veto** could fire on SI covers before filename_si.
3. **`headText` empty + Info.Title present** → `empty_head` forced **main** while title still looked like a paper (exact phone pattern).

## Locked product

1. After dual gates, `filenameLooksLikeSi` → **`supplementary`** / `filename_si`.
2. Filename SI → **skip** ACS chrome / ESI footnote main vetoes.
3. **Empty head + filename SI** → `filename_si` (not `empty_head` main). Empty head without SI filename stays `empty_head` main.
4. Bump `kPdfAdvisoryCacheSchema` → **16**.
5. Dart + Python twins.

## Non-goals

Auto-merge · OCR · weakening ACS veto for non-SI filenames.

## Tests

- title-only head + `cs9b00733_si_001.pdf` → supplementary  
- empty head + SI filename → supplementary / `filename_si`  
- ACS chrome fixture + SI filename → supplementary (veto skipped)  
- `-main.pdf` stays main  
- Schema 16 · **0.3.275**

## Ship

**0.3.275**
