# 317 — Azure fail-closed user copy

**Version:** 0.3.314 · Status: **locked**  
Amends [154](154-figure-pipeline-guard.md) · [147](147-azure-layout-figures.md)

## Why

When Azure Layout is configured and `extract_figures_v2` raises, ingest
keeps fail-closed (empty figures, no PyMuPDF unless
`ASR_FIGURE_PYMUPDF_FALLBACK=1`). The exception was logged only.
`session.warnings` stayed empty. The ingest quality banner is product-hidden,
so a warning token alone would not have been visible.

Sentences still save. The user saw a paper with no figures and no next step.

## Locked

1. Azure configured + exception + fallback off → figures stay empty.
   Status `outcome=azure_failed`, warning `azure_layout_failed`.
2. Ingest appends that warning and sets the job / finish message to:
   `그림 배치를 읽지 못했습니다. 문장은 저장됩니다. 잠시 후 재분석해 주세요.`
3. Reader shows a dedicated banner (not the hidden quality banner) with
   **재분석**. Web upload status uses the same copy.
4. Empty Azure slots (`outcome=azure_empty`) are not this warning.
   A paper may have no figures.
5. Do not turn on `ASR_FIGURE_PYMUPDF_FALLBACK` to “fix” the copy.

## Not this chip

- PyMuPDF fallback
- Showing the general ingest quality banner
- Deploying Azure credentials
