# 355 — A resumed paper reported nothing

**Version:** 0.3.351 · Status: **locked**  
Fixes a hole in [321](321-extraction-boundary-census.md)

## Why

A job that resumes after deboning takes the `else` of `if not resumed_debone:` — and the
whole design/321 quality report lived inside the `if`. So a resumed paper emitted no
`extract_text → sentences_ready` handoff at all.

Its *warnings* survived: the payload is saved at the end of that branch, **after** the
report ran, so they were restored with the sentences. What was lost is the twelve measured
values behind them — `source_coverage`, `practice_token_n`, `order_backward_pct`,
`refs_share` and the rest. Those are the record used to tell one paper's failure from
another's, and for a resumed paper they were simply absent.

The second hole is worse, because it hid the first:

```python
except Exception:  # noqa: BLE001
    pass
```

A resume leaves `text_pre_filter` empty by design — it starts from already-filtered pages,
so there is no copy of the text as it was before extraction. The block's first act was
`raise ValueError("no_pre_filter_text")`, which this `except` swallowed. **A paper whose
quality could not be measured looked exactly like a paper with nothing to report.**

## Locked

The report moved out of the branch and now runs on both paths. It measures what a resume
does have — the sentences, the text they were made from, the stored `ingest_quality` — and
names what it does not:

| | fresh ingest | resume |
|---|---|---|
| `sentences_ready` handoff | emitted | **emitted** |
| order statistics | measured | **measured** |
| source coverage | measured | `source_coverage_unavailable:resume` |
| the report failing | `quality_report_failed:<type>` | same |

The handoff carries `resumed` and `pre_filter_available` so the two shapes are told apart
in the record rather than inferred.

Refusing a false source coverage is unchanged — with no pre-extraction copy, a ratio
against the filtered text would read 1.0. design/321 expressed that refusal by raising;
raising also discarded the rest of the report. The computation is now gated and the absence
is named, so the report still runs and still refuses the ratio.

## Not this chip

- Keeping a pre-extraction copy in the resume payload, which would let a resume measure
  source coverage too. It is the text of a whole paper, so the cost is real and the
  benefit is one metric
- The re-ingest notice: yesterday's and today's fixes reach only papers added since

## Test

`tests/test_design_355_resume_reports_too.py` — the report and the handoff outside the
resume branch, at the same level as the gate, a failed report named rather than swallowed,
a resume naming its missing census, the handoff recording which shape it is, the order
statistics still anchored in the text the sentences came from, and the report appearing
exactly once so the move did not become a copy.

`tests/test_design_321_extraction_census.py` keeps the guarantee under its new expression.
