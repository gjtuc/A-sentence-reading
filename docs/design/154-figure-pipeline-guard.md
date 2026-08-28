# design/154 — Figure pipeline guard (no silent PyMuPDF regression)

**Version:** 0.3.79 (with guard deploy)  
**Depends:** [151](151-layout-map-slot-carousel.md) · [32](32-github-cd.md)

## Problem

Co–TiO₂ 재분석 전 폰 캐시가 **PyMuPDF fallback** PNG(`figure 9/9`, bleed, `그림 2`)였다. 원인:

1. GitHub CD가 **Azure DI secrets 없이** 배포 → Live `azure_layout: false` → ingest가 옛 경로
2. `extract_figures`: `used_azure = bool(merged)` → v2 빈 리스트면 **자동 PyMuPDF**
3. 번역 후 두 번째 `save_paper_session`이 `layout_map.json`을 **지움** (artifacts 미전달)

## Guards (locked)

| Layer | Rule |
|-------|------|
| **CD secrets** | `ASR_AZURE_LAYOUT≠0` → `AZURE_DOCUMENT_INTELLIGENCE_*` **필수** (workflow + deploy script) |
| **Deploy script** | Azure 키 없으면 `exit 2` (partial 키도 거부) |
| **Post-deploy** | `verify_live_status.py --require-azure-layout --min-pipeline rich-v20` |
| **Runtime** | Azure configured → **v2 only**; PyMuPDF fallback은 `ASR_FIGURE_PYMUPDF_FALLBACK=1` 일 때만 |
| **Ingest save** | 번역 후 `save_paper_session`에도 `layout_artifacts` 전달 |

## Primary path (do not replace)

```
extract_figures_v2 → layout_map + slot_plan + caption_pairing + composite vstack
```

**금지:** `rect | cap_rect` union, PyMuPDF orphan append, caption-sort finalize on slot-backed figures.

## Agent / other chats

`.cursor/rules/figure-pipeline-guard.mdc` 참고. 되돌리기·배포 전 checklist.

## Kill switches

| Env | Effect |
|-----|--------|
| `ASR_AZURE_LAYOUT=0` | PyMuPDF-only (dev only; production CD 실패) |
| `ASR_FIGURE_PYMUPDF_FALLBACK=1` | Azure 오류 시 PyMuPDF 허용 (긴급) |

## Code

- [`extract.py`](../src/sentence_reading/pdf/extract_figures_v2.py) — v2-only when Azure on
- [`deploy_cloud_run.sh`](../scripts/deploy_cloud_run.sh)
- [`verify_live_status.py`](../scripts/verify_live_status.py)
- [`app.py`](../src/sentence_reading/api/app.py) — layout_artifacts on translate save
