# design/489 - document kind: paper, peer review file, general document

## Problem

Every upload was treated as a paper. Two cases went wrong.

- A Nature Communications peer review file (`..._MOESM2_ESM.pdf`) reprints the paper's title and has an ESM filename. design/363 read the filename and called it SI, so it got no title card, its sentences went through the SI bibliography filter, and it could pair with the paper as if it were the SI.
- Invoices, forms, manuals and slides were shown as papers on the library card, and could pair with a paper of the same title.

## Rule

`sentence_reading/pdf/doc_kind.py`, on the full extracted text (after vision):

| Kind | Rule |
|---|---|
| `review` | the first 12000 characters have a line starting with "Reviewer comments", "Peer review file", "Response to (the) reviewer(s)" or "Reviewers' comments", or at least two distinct "Reviewer #n" numbers |
| `general` | not one paper sign. Head: abstract/summary/초록/요약, introduction/background/서론, keywords/주제어, supporting/supplementary information. Whole text: references/bibliography/참고문헌, a DOI, "et al" |
| `paper` | everything else, and empty text (a scan without a text layer is usually a paper) |

A review file is checked before the filename in `detect_doc_role_detailed` (reason `peer_review`), so it stays `main`: it gets a title card and no SI filter. SI stays a role (`doc_role`), not a kind.

The general rule is "zero signs" on purpose. Over 186 PDFs in Downloads, 8 non-papers had exactly one sign; calling those papers costs only a missing tag, while calling a paper general would hide it from SI pairing.

## Storage

- `save_paper_session(doc_kind=...)` writes `doc_kind` into `session.json` and the index row. As with `analyzed_build`, only an analysis passes it; translation, merge and other saves keep the prior kind.
- `/api/cache/papers` rows carry `doc_kind`; `library_tag` is "심사 기록" or "일반 글" for a main-role row of that kind.
- The device library row (`PaperDiskIndexEntry`) keeps `doc_kind`. A writer that does not know the kind leaves it empty and `upsertIndex` keeps the prior row's kind.

## Pairing

Server `_pairable` and the device `applyLocalPairingPassDetailed` skip any row whose kind is not `paper`.

## Evidence

`doc_kind_detect` at save: kind, doc_role, paper_signs count, text_len. No paper text.

## Not in this step

- A "change kind" menu (comes with title editing).
- Existing documents are not re-judged; they read as papers until reanalysed.
