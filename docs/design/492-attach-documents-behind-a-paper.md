# design/492 - attach documents behind a paper

## Problem

"짝과 합치기" (design/152) joined exactly one supplementary file to its paper, and only when the titles paired. A Nature download is often three files: the paper (`s41467-021-24079-8.pdf`), the SI (`41467_2021_24079_MOESM1_ESM.pdf`) and the peer review file (`..._MOESM2_ESM.pdf`). The review file's title is "REVIEWER COMMENTS", so no title rule can link it, and there was no way to put any other document behind a paper.

## Model

A merged paper keeps `merged_parts`: `[{id, section}]` in reading order. The section says what the part is:

| section | part | sentence id prefix | figure id prefix | reader label |
|---|---|---|---|---|
| `supplementary` | SI role | `si_` | `si-` | Supplementary |
| `review` | review kind (design/489, or the reader's kind, design/490) | `rv_` | `rv-` | Peer review |
| `attached` | anything else | `at_` | `at-` | Attached |

A design/152 merge without `merged_parts` reads as one `supplementary` part (`merged_supplementary_id` / `supplementary_cache_id`). Attaching skips parts already inside, so a second press, or a device merge followed by the server sync, adds nothing twice. design/467's rebuild (strip the SI part, append again) runs only for an old merge that has no part list and is given an SI again.

Parts go in this order: supplementary, review, the rest; equal sections keep the order given. A part is hidden from the library (`hidden_in_library` on the server, removed from the device index), as the SI was.

The card tag is `메인+서플먼터리` for SI-only merges (as before) and `메인+보충+심사` and so on otherwise (`merged_sections` in list rows).

## File number

Ingest now keeps the upload's file name (`source_name`, folders dropped, 200 characters at most). `file_article_key`:

- Nature style `s?NNNNN[-_]YYY(Y)[-_]NNNNN`: `n:41467-21-24079`, so `s41467-021-24079-8` and `41467_2021_24079_MOESM2` agree.
- Otherwise the name up to the first part marker (`_si`, `-sup`, `_esm`, `-mmc1`, `-main`, `_review`, ...), when it has 6+ characters and 4+ digits: `1-s2.0-S0360319921012345-main` and `-mmc1`, `ja1c01234` and `ja1c01234_si_001`.

The library pass (device, after the title pairing) gives a paper `mergePartIds`: its title-paired SI first, then SI and review files with the same key. A key with two papers on it links nothing, and an SI paired by title to another paper stays with that paper. Papers analysed before this version have no file name and link by title only, or by hand.

## Three ways in

- The card button: "짝과 합치기" for one part, "3개 합치기" for more, "N개 더 붙이기" on an already merged paper. Hovering it (web) or holding it (phone, the tooltip) lights the cards it takes in and says what they are.
- Hold menu "다른 문서 뒤에 붙이기": pick the paper; same file number first, then same title.
- Edit mode "합치기" with two or more selected: pick the document that goes first (the paper is suggested), the rest follow in part order.

Every path shows one confirm listing the parts. A merged paper cannot become a part. Merging stays locked while an upload or reanalysis runs, as in design/491.

## Server

`POST /api/cache/papers/{id}/attach` with `{"parts": [{id, section}]}` runs `attach_parts`; `merge-supplementary` stays for old clients and goes through the same code. The device merges its own copy first and then calls `attach`, as design/467 does.

## Also fixed

Rebuilding the list from the screen list (a title/kind label change, design/490) dropped the SI folded into its paper's card, so the merge button vanished until the next refresh. The publish step now remembers folded rows and folds them again; lists from the server replace them.

## Not done

Taking a part back out ("떼어내기"). The parts' own folders stay on the device and in the account, so it can be added later.
