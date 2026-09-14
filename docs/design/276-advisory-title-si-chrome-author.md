# 276 — Advisory title: SI strip · ACS chrome · author reject · mate borrow

Version: **0.3.269** · Status: **locked**  
Amends [265](265-import-title-pair-green.md) · [228](228-pdf-advisory-title.md).

## Problem (folder audit + phone)

Revealing / ACS mates still show bad import titles after 265:

1. **SI** head line `Supporting Information Revealing the Mechanism…` — whole line skipped → `failed` / filename.
2. **Main** truncated Info → head picks `Research Article pubs.acs.org/acscatalysis` (chrome not exact-match).
3. **Author lines** (`Kaihang Han, … and Fagen Wang*`) accepted as `head_line`.
4. Info cut like `… Molecular D` not flagged truncated (single-letter last token).
5. Empty SI title excluded from set grouping even when `acs:` soft-pair key is usable.

## Locked product

1. **SI banner strip** — if a head line matches SI banner, strip the banner prefix; qualify the remainder as a title candidate before skipping.
2. **ACS chrome** — reject lines containing `pubs.acs.org` / `Research Article`+journal URL mash; keep exact/prefix chrome rules.
3. **Author-line reject** — multi-name comma lists with `*` / `and Name` patterns are not titles.
4. **Truncation** — last token length 1 letter (or 2-letter mid-cut) after a long phrase → truncated Info.
5. **Mate title borrow (display)** — SI with empty / low-quality stem title borrows ready main mate title when `effectivePairingKey` matches (ACS/DOI/title). Does not change upload wire name.
6. **Set grouping** — `ready` + usable pairing key may enter set logic even if title empty (then borrow fills display).
7. Bump `kPdfAdvisoryCacheSchema` **11 → 12**.

## Non-goals

Server-side title extractor · silent auto-merge · changing green-border honesty (275) · ingest success rates.

## Tests

- SI banner+title one line → full mechanism title.
- ACS `Research Article pubs.acs.org/…` → not chosen; real title from later head.
- Author line skipped.
- `… Molecular D` Info truncated → head.
- Mate borrow fills SI empty title when ACS keys match.
- Schema 12.

## Ship

**0.3.269** — mobile advisory only (+ version pins). Open import folder after upgrade so cache re-runs.
