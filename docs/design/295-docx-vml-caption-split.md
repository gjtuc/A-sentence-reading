# 295 — Read VML figures and keep caption labels on the card

Version: **0.3.289** · Status: **locked**  
Amends [294](294-si-extract-diagnosis.md) (sensors stay; this is the product fix)

## Why

Elsevier SI `.docx` stores rasters as VML `v:imagedata` (`r:id`), not DrawingML `a:blip` (`r:embed`). `extract_figures` returned 0. Caption lines are their own paragraphs (`Fig. S4.` then the body), so the heuristic split made a card that was only the label.

## Rules

1. Paragraph image walk resolves both `a:blip`/`r:embed` and `v:imagedata`/`r:id`. Same pairing: caption on the next paragraph. No caption still drops the image.
2. `vml_unseen_n` is unresolved imagedata only, not the raw count.
3. A paragraph that is only `Fig. S#.` / `Table S#.` / `Scheme S#.` joins the next paragraph, and that leading label period is not a sentence boundary.
4. A single capital initial (`R.`) before a capital name is not a sentence boundary.
5. Prose `as shown in Fig. S1. The rate increased.` stays two sentences.

## Non-goals

- Main-paper title cleanup  
- Pairing-key 1+1  
- Ops beyond this version ship  

## Early measure

Test rasters go through `tests/raster_floor.py` `png_over_docx_min()`. It reads `_MIN_BYTES` and grows a noisy PNG until the blob is at least that large. A solid 40×40 is the known miss (compresses under 200) and must stay under the floor in the contract test.

Acceptance on a file is `scripts/replay_docx_extract.py <docx> --min-fig N --max-stub 0` (exit 2 if figures are short or a caption label is still its own card).

## Acceptance

`tests/test_docx_vml_figures_295.py`
