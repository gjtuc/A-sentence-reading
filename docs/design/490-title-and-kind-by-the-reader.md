# design/490 - the reader's own title and kind, typed or spoken

## Problem

design/488 picks a good title for most files, but forms and scans still get a poor one. design/489 judges the kind automatically and can be wrong (a scan without a text layer reads as a general document). The reader had no way to fix either.

## Rule

Hold a library card: two new items, "제목 고치기" and "종류 바꾸기" (not on the sample row).

- Title dialog: the shown title in a field, a microphone in the field, "분석한 제목으로 되돌리기" when it differs. Save folds it to one line of at most 300 characters.
- Microphone: the design/475 full-screen listener, with title wording. `POST /api/ask/voice` gets `purpose=title` and the current title as spelling context; the server uses a title prompt and drops a closing period. The spoken title replaces the field.
- Kind dialog: 논문 / 심사 기록 / 일반 글, the analysed one marked "자동 판단".

## Storage

A label per paper cache id: `{at, dev, t?, k?}`. It is not written into the paper.

- The paper's own `title`, `title_key` and `doc_role` stay as analysed, so pairing, duplicate checks and read-done title keys (design/457) keep using them.
- A title equal to the analysed one and the analysed kind are stored as "no field".
- Device: `PaperLabelStore` in SharedPreferences, per account (like design/442 read-done).
- Server: `GET /api/paper-labels`, `PUT /api/paper-labels/{cache_id}`, one JSON per account at `users/{uid}/paper_labels/labels.json` with a generation check. The newer `at` wins and replaces the whole label, so clearing on one device clears the other.

## Where it shows

`LibraryController._publishPapers` puts each label on its row (`displayTitle`, `labelKind`) before the device pairing pass, so a kind the reader set takes part in pairing (`effectiveKind`). The card shows `shownTitle` and `shownTag`; the reader header shows the label title.

The server's own list and pairing still use the analysed kind; the device pass is what the library shows.

## Evidence

`paper_label_set` (client): has_title, title_chars, kind, auto_kind, doc_role. No title text. `voice_ask_transcribe` details gain `purpose`.
