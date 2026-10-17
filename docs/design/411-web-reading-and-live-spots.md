# 411 - Web reading view and live reading spots

## Problem

On a wide monitor the web reader showed one sentence at phone size: small type and a
line running edge to edge. The arrow keys did nothing. A move was saved only after a
server cursor call and an auth lookup, so closing the tab during a slow network could
lose the last spot. The phone and the web shared reading spots only through the sync
button (design/410).

## Reading view (`state/web_reading_prefs.dart`)

After Word's Immersive Reader: large type, generous line height, and the line kept in a
centred column.

- `webReadingStyle` returns null off the web or in a window narrower than 720 px, so the
  phone look does not change.
- Text size: normal 26, large 34 (default), huge 44 px. It shrinks to width / 18 in a
  narrow window.
- Line width in em: narrow 26, medium 34 (default, about 68 characters), wide 44.
- Line height 1.6. The Korean line is 0.72 of the English size.
- Settings has a web-only section 「웹 읽기 화면」 with both choices. They are kept in
  shared preferences (`web_reading_size_v1`, `web_reading_column_v1`).

## Keys (`screens/reader_screen.dart`)

- ←/→ move the sentence. When only the figure shows, they move the figure.
- Shift+←/→ move the figure.
- The reader stays mounted under the library, so keys do nothing while it is hidden
  (`TickerMode`). Coming back from the library takes the focus again.

## Saving first

`persistOpenedProgress` uses the bound uid instead of an auth call. Every move saves the
local row before the server cursor call.

A row's `at` is the time the spot was reached. A save at the same spot keeps `at`, so a
background save (app paused, tab hidden) does not make an old spot look new.

## Live spots

The server keeps, per account, one JSON object `users/{uid}/reading_spots/spots.json`:
paper cache id -> `{si, fi, at, dev, rev}`. It holds numbers only: no title, no text. It
is written with a GCS generation check (4 tries), so two devices never erase each other.
At most 500 papers are kept; the oldest `rev` goes first.

- `PUT /api/spots/{cache_id}` with `{si, fi, at, dev}`. The newer `at` wins.
- `GET /api/spots?since=N` returns the account `rev` and the spots changed after N.

The client is `services/spot_sync.dart`:

- A move made here (`persistOpenedProgress(publish: true)`, called from the four move
  methods only) is sent after 600 ms. Background saves are not sent.
- Every 3 s while the app is in the foreground, the client asks what changed. After 3
  failures in a row it asks every 60 s. A spot from this device's own id is skipped.
  A move here that is not sent yet beats anything on the server.
- A spot from another device is kept apart from this device's rows
  (`reading_spots_remote_v1:<uid>`). An open validates its own row and refuses a bad
  one, so a spot from elsewhere is used only when it is newer and fits the paper.
- The open paper follows at once when the spot is newer than the local row and fits the
  paper. The local row then takes the other device's `at`, so clock skew does not hide
  that device's next move.
- The home shell starts and stops the timer, so a bare controller in tests runs none.
  Pausing the app sends what is pending.

Evidence: `spot_follow` (first follow, then every 20th) and `spot_sync_failed` (first
failure of a streak).

## Not yet

- The library resume label of a paper that is not open still shows this device's last
  section until the paper is opened.
- Two monitors with the sentence in one window and the figure in the other.
- Web paper folder, web practice screen.

## Tests

- `tests/test_design_411_reading_spots.py`
- `mobile/test/spot_sync_test.dart`
- `mobile/test/web_reading_prefs_test.dart`
