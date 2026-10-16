# 408 - The web library keeps nothing on a local disk (step 3 of the web version)

## Problem

After logging in on `/app/`, the library showed
`MissingPluginException(No implementation found for method getApplicationDocumentsDirectory
on channel plugins.flutter.io/path_provider)` and "보관 0건". The phone keeps every paper,
figure and shadowing take in app folders (design/185, 187). The web build has no app
folders: path_provider has no web plugin, and dart:io files throw. The first store that
asked for its folder after login threw, and the library refresh surfaced it.

## What changed

- **One switch.** `mobile/lib/services/local_disk.dart` has
  `localDiskAvailable => !kIsWeb && !debugNoLocalDisk`.
- **Every folder lookup asks it first.** When it is false, the folder is null, and every
  store already treats a null folder as empty:
  `PaperDiskStore.uidRoot`, `ShadowingDiskStore.uidRoot`, `NotesLocalArchive._storeFile`,
  `FigureDiskCache.listChildDirNames` / `paperDir` / clear, `FigurePngCache._root`,
  `TtsAudioCache._root`, `TitleSwitchStore._file`, `PdfHashCacheStore._dir`,
  `PdfAdvisoryCacheStore._dir`.
- **Stores with non-null folders.** `PaperEditStash` reads return null, the purges and
  preview writes return, and `saveSource` throws `PaperStashException('no_local_disk')`.
  `SkillEvidenceStore` keeps an empty queue.
- **Documents mirror.** `DocumentsMirrorStore.bindUid` stays unbound, so it never calls the
  Android `asr/documents_mirror` channel.
- **Result.** A web session reads the list from `/api/cache/papers` and opens a paper
  through `/api/cache/papers/{id}/open`, because `hasSession` is false. That path already
  existed for a phone whose disk has no copy.

## Not in this step

Upload (step 4) still uses the Android picker, SAF and the upload stores. Those stores
already catch the error. Voice (step 5) and shadowing (step 6) still use the microphone
channel and temporary files.

## Tests

- `mobile/test/web_no_local_disk_test.dart` sets `debugNoLocalDisk`. In a VM test
  path_provider throws the same MissingPluginException as the browser. Two control tests
  show the store and a bound library fail with a disk switched on. With it off, a bound
  library lists and opens a server paper with no error.
- `tests/test_design_408_web_no_local_disk.py` checks that each folder lookup asks the
  switch. A new path_provider caller fails it until it is listed.
