# 417 - Resume label follows the other device before the paper is opened

## Problem

design/411 sends the reading spot between the phone and the web. The open paper
follows it, but the library row of a paper not opened on this device kept the old
「이어 읽기」 section name until it was opened. Opening it then jumped somewhere the
row did not say.

## Shape

A spot carries numbers only (sentence index, figure index, time), so the label is
built here from the session on disk:

- `loadRemoteSpots(uid)` reads every held spot of the account at once.
- `LibraryController._withRemoteLabels` replaces the label of a paper whose remote
  spot is newer than this device's own row. It loads the session from disk, checks
  the spot fits the paper (`validateProgressIndices`), and names it with the same
  `sectionNav.headerPartsFor` as `persistOpenedProgress`.
- It runs after every label load (library refresh, `reloadResumeLabels`) and when a
  spot arrives for a paper that is not open.
- The label is kept per paper with the spot time, so the session is read again only
  when a newer spot arrives.

The open paper is skipped: it follows the spot and saves its own label.

Nothing is written to this device's progress row; the open path (design/411) still
decides where the paper opens.
