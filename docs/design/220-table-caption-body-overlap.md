# 220 — Table caption/body overlap mis-pair (SI Table S3)

**Parent:** [151](151-layout-map-slot-carousel.md) · [125](125-caption-anchored-figures.md)  
**Version:** 0.3.219+  
**UI:** none (extract)

---

## Symptom

SI `an1c00673_si_001.pdf`: carousel `Table S3` showed **caption strip only**; phone matched thin white band.

## Cause

Azure DI emitted `table_body` `tb-0279` for S3 that **overlaps** the S3 caption by ~11pt (`body.y0 < caption.y1`).

`_nearest_caption_for_body` required `gap = body.y0 - caption.y1 >= -8`, so the true S3 caption was dropped. The body paired to **Table S2** (~88pt above). `table:s3` stayed `partial` → `composite_table_png` caption-only. True S2 body `tb-0278` unused.

Figures already had orphan fallback; tables did not.

## Fix

1. `TABLE_CAPTION_OVERLAP_PT = 40` (shared by `initial_body_assignments` + caption strip pairing).
2. Table orphan clip when body missing / caption-only PNG, **stopping before the next Table caption**.

## Verify

```bash
PYTHONPATH=src python -c "..."  # extract SI; table:s3 status filled, height >> caption-only
pytest tests/test_table_caption_overlap_220.py -q
```
