# Adjacent-papers test materials (chip prep)

PDFs are gitignored (`*.pdf`). Keep `README.md` + `boundary_report.json` in git.

## A — Open arXiv merge (issue-like)

| File | Source |
|------|--------|
| `paper_a_arxiv2401.14543.pdf` | https://arxiv.org/abs/2401.14543 (Honeycomb Ni DRM, 42 pp) |
| `paper_b_arxiv2401.14123.pdf` | https://arxiv.org/abs/2401.14123 (Ultrathin washcoat DRM, 7 pp) |
| `oa_merged_two_articles.pdf` | A then B → **49 pages** |

**Ground truth:** article B starts at **0-based index 42** (1-based page **43**).

## B — Synthetic fixture (CI-friendly)

| File | Content |
|------|---------|
| `synthetic_two_articles.pdf` | Alpha (pp 1–3) + Beta (pp 4–5) |

**Ground truth:** keep Alpha → `0..2`; strip Beta from index `3`.

## Regenerate

From repo root:

```bash
mkdir -p testdata/adjacent_papers
curl --ssl-no-revoke -L -o testdata/adjacent_papers/paper_a_arxiv2401.14543.pdf https://arxiv.org/pdf/2401.14543.pdf
curl --ssl-no-revoke -L -o testdata/adjacent_papers/paper_b_arxiv2401.14123.pdf https://arxiv.org/pdf/2401.14123.pdf
python scripts/build_adjacent_fixtures.py
```

**Caveat for detectors:** Paper A’s reference list cites the Ultrathin title around page 37 — that is **not** a new article start. True boundary is page **43**.
