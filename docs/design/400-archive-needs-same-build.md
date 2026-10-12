# 400 — an archived analysis is reused only by the build that made it

## What was wrong

`_try_cache_hit` reuses a stored analysis when the new upload's opening text holds
its title and the stored `pipeline_version` equals `PIPELINE_VERSION`.

`PIPELINE_VERSION` was `rich-v24` from at least 0.3.51 to 0.3.439. Every
extraction and debone fix in between left it alone, because twelve test files
asserted the exact string `rich-v24`, so a bump failed them all at once.

The cost was real. A stored August analysis of an ACS paper (Ni–Cu/SiO2) had no
Experimental section and lacked the last paragraph of its Introduction: 120
sentences. The same PDF through the 0.3.439 pipeline gives 159 sentences, 17 of
them Experimental. Both carried `rich-v24`, so the server
could not tell them apart and would have served the August one as current.

## Rules

- `PIPELINE_VERSION` is `rich-v25`.
- `save_paper_session(analyzed_build=...)`: the two analysis saves in the ingest
  path pass `app.version`. Every other save (translation backfill, harmonize
  residual, supplementary merge) passes nothing and keeps the prior value, so a
  re-save does not make an old analysis look current. A save with neither stays
  `""`.
- The value is written to `session.json` and to the index entry, and survives the
  GCS round trip (`papers_gcs` local upsert).
- `_try_cache_hit` also requires `analyzed_build == app.version`. An entry from
  before this change has no stamp and is never reused.
- Tests check `rich-v` and a number of at least 24, not the exact string.

## Cost

Each release now re-analyzes a PDF instead of reusing its archive. In practice the
archive is rarely there: the server wipes its copy once the phone takes the paper
(design/397), and on 2026-10-12 the user's GCS paper index held 0 entries.

## What it does not touch

The phone stores papers on the device and only displays the pipeline name, so no
library row turns "구버전" and nothing re-analyzes by itself. An ingest checkpoint
saved under `rich-v24` is not resumed after the deploy; that job starts over.

## Tests

`tests/test_design_400_archive_needs_same_build.py`
