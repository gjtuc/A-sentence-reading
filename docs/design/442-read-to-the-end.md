# 442 — "다 읽은 논문", as an e-book marks a finished book

## Ask

YES24 eBook asks "다 읽은 책으로 표시하겠습니까?" when the reader turns past the last
page, and a 예 puts a "다 읽은 책" mark in the library. Do the same for papers: next on
the last sentence asks, the library shows the mark, and the files in 논문 가져오기
show it too, since the app knows which file each paper came from.

The reader chose:

- the mark is the account's, shared by web and phone;
- opening a done paper goes to the last place read, as now;
- the mark is a check and "다 읽음" next to the title;
- one state only, done or not (no "reading" state);
- the library hold menu takes it off ("다 읽음 표시 풀기"), or puts it on.

## Change

**Ask.** `LibraryController.advanceSentence` used to wrap the last sentence round to
the first. While a reader is open it sets `onPastLastSentence`, and next on the last
sentence (button, swipe or → key) calls it instead. The reader asks "다 읽은 논문으로
표시할까요?". 예 marks the paper; 아니요 stays on the last sentence. A paper already
marked shows "마지막 문장이에요. 다 읽은 논문이에요." instead. Without an open
reader the wrap is unchanged. The question only comes from the sentence side; TTS
playback does not call it.

**Store.** One JSON per account, `users/{uid}/reading_done/done.json`, like the reading
spots (design/411): `{version, rev, marks: {cache_id: {done, at, dev, h}}}`. `h` is the
PDF's sha256. The newer `at` wins both ways, so taking the mark off on the web takes it
off the phone. Writes are generation-matched; past 5000 marks the oldest go.

- `GET /api/read-done` → `{ok, rev, marks}`
- `PUT /api/read-done/{cache_id}` with `{done, at, dev, h?}` → `{ok, rev, applied}`

The spot store was not reused: it keeps 500 papers and evicts.

**Phone and web.** `ReadDoneStore` keeps the marks in prefs per account
(`read_done_v1_<uid>`) with a list of marks the server has not taken. A mark shows at
once; offline marks go on the next pull (each library refresh).

**Import list.** A file row gets the badge when its content hash is the hash of a done
paper. The hash is kept in the mark, so the file keeps the badge after the paper is
deleted and comes back when it is imported again. A set row (main + SI) uses the main
file. A lone SI file does not get it.

Files: `src/sentence_reading/llm/reading_done.py`,
`src/sentence_reading/api/routes/read_done.py`, `src/sentence_reading/api/app.py`,
`mobile/lib/state/read_done.dart`, `mobile/lib/api/client.dart`,
`mobile/lib/state/library_controller.dart`, `mobile/lib/screens/reader_screen.dart`,
`mobile/lib/screens/library_screen.dart`, `mobile/lib/screens/pdf_import_screen.dart`,
`mobile/lib/widgets/read_done_badge.dart`, `tests/test_design_442_read_done.py`,
`mobile/test/read_done_test.dart`, `mobile/test/reader_screen_widget_test.dart`.
