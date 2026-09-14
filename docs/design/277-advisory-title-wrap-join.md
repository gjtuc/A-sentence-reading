# 277 — Advisory title: font-similarity wrap join (+ overkill evidence)

Version: **0.3.270** · Status: **locked**  
Amends [276](276-advisory-title-si-chrome-author.md) · [228](228-pdf-advisory-title.md) · [265](265-import-title-pair-green.md).

## Research (why this, not word stubs)

| Source | Finding |
|--------|---------|
| **pdftitle** (metebalci) | Group consecutive objects with **same font+size**; title ≈ **largest size** near top of first page (~80% on scientific PDFs). |
| **SciPlore Xtract** | Rule: **largest font in upper first third** of page 1; 77.9% vs CiteSeer SVM 69.4% — style beats brittle ML for titles. |
| **PDFBox `TextPosition`** | Use **`getFontSizeInPt()`** (rendered), not raw Tf size; bold via font name / `FontWeight` / `forceBold` (imperfect). |
| **StackOverflow / PDFBox HTML** | Bold/italic are not first-class; guess from font descriptor. Override stripper to keep style. |
| **PyMuPDF flags** | Superscript flag exists; subscripts often need **position** — keep mixed-size glyphs **inside one line**. |

**Rejected:** ending-token lists (`Carbon`, `Metal`, `of`…) as title-trunc SoT — fails on unseen papers.

## Problem

Phone import titles wrap mid-phrase because head extract was **plain text lines** and Dart took the first qualifying line. Adjacent wrap lines share title typography but were ignored.

## Locked product

### Extract (Android PdfBox)

1. `PdfHeadExtract` still returns `headText` / `infoTitle` (compat).
2. Also returns **`headLines`**: ordered list of `{text, size_pt, bold, y}` for pages 1..maxPages.
3. **Line build:** cluster `TextPosition` by Y; **do not split** a visual line when size drops for **sup/sub/special** glyphs — they stay in the same line text.
4. `size_pt` = median (or mean) of non-tiny runs on that line; `bold` = majority bold-ish fonts on the line.
5. Cap lines (e.g. 80) and chars; never put URI/path in maps.

### Title assemble (Dart)

1. Prefer Info.Title when it passes existing 265/276 quality gates.
2. Else, on `headLines`:
   - Skip SI banner / chrome / author / affiliation / biblio (276 rules).
   - **Seed** = first remaining line that `looksLikePaperTitle`, else largest-size line in the upper band.
   - **Expand** immediately above/below while  
     `|size - seed.size| / seed.size ≤ 0.12` **or** both bold and size within 0.18,  
     and neighbor is not chrome/author/affil.
   - Join with spaces; strip SI banner prefix on members.
3. If `headLines` empty/fail → plain `headText` path (276), source still `head_line` / `stem` / `failed`.
4. **No** vocabulary wrap-stub list as SoT.
5. Bump `kPdfAdvisoryCacheSchema` **12 → 13**.

### Evidence (overkill)

| kind | when |
|------|------|
| `pdf_advisory_title_style` | each advisory miss with styled extract |
| details | `styled_n`, `seed_size_pt`, `joined_n`, `size_tol_x100`, `bold_seed`, `source`=`style_join`\|`plain_fallback`\|`info`, `mixed_size_line` 0/1, `ok` |

Top-level `ok` true only when a non-empty title was produced from style join or info; plain fallback may set `ok` with `source=plain_fallback`.

## Non-goals

Server-side title ML · changing set ingest success · inventing titles with OCR · word-stub trunc dictionaries.

## Tests

- Unit: styled lines same size join across wrap; different size (body) stops; superscript-smaller glyphs already inside one line text not dropped.
- Chrome/author still skipped before seed.
- Schema 13.

## Ship

**0.3.270** — reopen import folder after APK install.
