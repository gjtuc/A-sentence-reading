# 147 — Azure Document Intelligence layout extract

모듈: `pdf/azure_layout.py` · ingest `extract_figures`  
의존: `azure-ai-documentintelligence` · env `AZURE_DOCUMENT_INTELLIGENCE_*`

## Why

PyMuPDF caption-first clips bleed into adjacent tables (2-column papers). Azure **prebuilt-layout** separates figure/table bboxes and returns cropped figure PNGs.

## Env

| 변수 | 의미 |
|------|------|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | `https://….cognitiveservices.azure.com` |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Key 1 |
| `ASR_AZURE_LAYOUT` | `1` (default) · `0` = PyMuPDF only |
| `ASR_AZURE_LAYOUT_TIMEOUT_S` | analyze poll timeout (default 180) |

Source: `Desktop/.cursor/gc-home/gc_automation.env` (mirrored to `Desktop/.cursor/gc_automation.env`).

## Flow

1. PDF ingest → `extract_figures`
2. When Azure configured: `prebuilt-layout` + `output=figures`
3. Figures: service crop via `get_analyze_result_figure`; caption from Azure or PDF caption scan
4. Tables: Azure table bbox → PyMuPDF page clip (+ Table caption when matched)
5. PyMuPDF fills **missing caption keys** only (merge, not replace)
6. Azure failure or empty → full PyMuPDF path (unchanged)

## Pipeline

| | |
|--|--|
| version | **0.3.68** |
| pipeline | **rich-v16** |
| kill | `ASR_AZURE_LAYOUT=0` |

## Deploy

`scripts/deploy_cloud_run.sh` — both Azure env vars required together (or neither).

## Limits

- DOCX unchanged (PyMuPDF/docx extract)
- Not 100% on all journal layouts; caption-lump fail-closed still applies
- Per-page Azure cost; user opted in
