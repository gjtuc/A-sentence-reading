# design/149 — Azure caption filter + composite PNG + hide caption Text

**Version:** 0.3.70  
**Pipeline:** rich-v17  
**Depends:** [147](147-azure-layout-figures.md) · [126](126-soft-caption-labels.md) · [131](131-caption-full-text.md)

## Problem

Azure `figure.caption.content` often contains **body sentences** (`Figure S1 shows…`, `figure S7. of 62.1%…`). Mobile/web displayed them as under-image Text (design/131 full caption).

## Server (ingest)

### Caption filter (2A)

[`azure_layout.py`](../src/sentence_reading/pdf/azure_layout.py) — `resolve_figure_caption()`:

1. Azure string → `_is_caption_line()` (design/126)
2. Extra Azure heuristics: `of`/`while`/`respectively`, `%`, length > 140, multiple periods
3. Reject → `_match_fig_caption_with_rect()` (PyMuPDF scan, filtered)
4. Still empty → placeholder `Figure S7 (p.9)` from label only

### Composite PNG (2C)

After caption + `cap_rect` resolved:

- `clip = fig_rect | cap_rect` when rect known
- `_render_page_clip(page, clip)` → `image_src`
- Fallback: Azure figure crop PNG, then fig bbox clip

Tables unchanged (already union clip).

### Kill

| Env | Effect |
|-----|--------|
| `ASR_AZURE_LAYOUT=0` | PyMuPDF-only (unchanged) |
| `ASR_FIGURE_CAPTION_IN_IMAGE=0` | UI shows under-image caption Text again |

## Client UI (2B)

When `/api/status` `figure_caption_in_image` / `mobile_figure_caption_in_image` is true (default):

- **Mobile** [`reader_screen.dart`](../mobile/lib/screens/reader_screen.dart): hide caption `Text` under figure image
- **Web** [`app.js`](../src/sentence_reading/static/app.js): `figureCaption.hidden = true`

`caption` JSON field kept for Fig chips and sort order.

## Re-ingest

Papers at **rich-v16** keep old figure PNGs/captions until **re-upload or reanalyze**.

## Device / E2E pin

- Live `/api/status`: `version=0.3.70` · `pipeline_version=rich-v17` · `figure_caption_in_image=true` · `mobile_figure_caption_in_image=true` · `azure_layout=true` (rev `asr-sentence-reading-00160-crr`)
- APK SM-G986N `versionName=0.3.70` sideloaded
- Co–TiO₂ paper after reanalyze: library shows **그림 17** (was 18 at rich-v16); reader `figure 9 / 17`
- Under-image caption `Text`: **none** (uiautomator `text=` empty under figure; no body paragraph below image)
- Kill: `ASR_FIGURE_CAPTION_IN_IMAGE=0`

Do not paste emails, cookies, tokens, or secrets into chat/PR.

## Out of scope

- `text_ko` cite strip (2.5)
- Automatic cache migration without re-ingest
