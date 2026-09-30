# 372 — Mirror figures out of the gallery

**Version:** 0.3.412 . Status: **locked**
Amends [262](262-documents-mirror.md) . [264](264-documents-mirror-mes-channel.md) . [268](268-documents-mirror-write.md)

## Why

Every figure of every paper showed up in the phone's gallery, mixed in with the
owner's photos.

The cause is not a bug in the mirror, it is what the mirror is for.
`DocumentsMirrorHandler` writes to
`Environment.getExternalStoragePublicDirectory(DIRECTORY_DOCUMENTS)`, and design/262
chose that on purpose: the mirror exists to **survive uninstall and clear-data**, and
app-private storage is deleted by both. Public storage is also exactly what the media
scanner indexes, so `papers/{cid}/figures/*.png` became gallery entries.

Moving the figures to app-private storage would fix the gallery and break the only
thing the mirror does. The figure caches that are already app-private
(`getApplicationDocumentsDirectory` in `figure_disk_cache.dart`,
`getApplicationSupportDirectory` in `figure_png_cache.dart`) were never the problem
and are not touched.

## Locked

### The marker, not a move

An empty `.nomedia` at the mirror root `Documents/문장읽기/.nomedia`. The scanner skips
the directory holding it **and everything under it**, which is the whole mirror, so a
paper added next month is covered without another call.

The files do not move, do not change name, and do not change format. A file manager
still lists them and the restore path still reads them, because both walk the
filesystem rather than MediaStore. Only media apps, which ask MediaStore, stop seeing
them.

### Written before anything can be scanned

`ensureUidRoot` calls `ensureNoMedia()` before it returns, so there is no window in
which a figure lands in a directory the scanner would read. Every mirror write goes
through `ensureReady` -> `ensureUidRoot`, so this cannot be forgotten by a later
caller.

### Never delete a MediaStore row

`ContentResolver.delete` on a `MediaStore` uri deletes **the file it points at**.
Using it to clear the gallery would throw away the very figures the mirror is keeping
against an uninstall. `hideFromGallery` asks for a rescan instead
(`MediaScannerConnection.scanFile` on the root): a directory holding `.nomedia` has
its indexed children dropped and the files stay.

The rescan runs **once per bind**, not per mirrored paper, because the marker written
by `ensureUidRoot` already stops anything new being indexed. The rescan is only for
what was indexed before the marker existed.

### Reported, not assumed

`documents_mirror_done` carries `nomedia_ok`. A mirror the scanner can still read
puts every figure back in the gallery and nothing on screen would say so.

`hideFromGallery` returns whether the marker **is there**, not whether this call
wrote it, so a second call on an already-hidden mirror is a success. Reading
`created: false` as failure would raise the banner on every launch.

Fail-closed the honest way: a refused permission, a reply that is not a map (an older
build with no such method), or `ok: false` all report *not hidden*. Claiming hidden
would leave figures in the gallery with nothing saying why.

## What this does not do

It does not make the figures unopenable. They are still PNGs that a file manager can
open, and design/262 wants that -- the mirror is the copy that survives a reinstall.
Renaming them to an opaque extension was considered and refused: it would hide them
from the file manager the owner might one day need, and the annoyance was the gallery.

## Checking

    adb shell ls -a /sdcard/Documents/문장읽기/ | findstr nomedia

or read `nomedia_ok` off `documents_mirror_done` in the evidence stream.

A gallery app that caches its own thumbnails may hold the old ones until it refreshes;
the MediaStore entry is gone either way.

## Docs

`docs/design/262-documents-mirror.md` . `docs/design/268-documents-mirror-write.md`
