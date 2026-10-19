# 416 - 논문 폴더 연결 on the web

## Problem

The web reader opened the same 「논문 가져오기」 screen as the phone, but every folder
call in `SafTreeChannel` returned nothing on the web, so 「논문 폴더 연결」 did nothing.

## Shape

The web branches of `SafTreeChannel` now go to `platform/web_folder_web.dart`, which
uses the browser's folder access (`showDirectoryPicker`, Chrome and Edge). The rest of
the import screen and the controller is the phone's code.

- **Connect.** The picker opens read-only. The folder handle is kept in IndexedDB
  (`asr_folders` / `handles`) under a key, and the app sees `webdir:<key>`; a file is
  `webdir:<key>/<path>` (`web_folder_paths.dart`). The grant itself stays in the
  phone's prefs store, so the folder is remembered after a reload.
- **List.** PDF and DOCX files, folders up to 6 deep, hidden names skipped, the same
  500 cap. Size and modified time come from the file.
- **Already kept.** The hash is SHA-256 by the browser (`crypto.subtle`), so the green
  「이미 보관」 border works as on the phone. The hash cache stays in memory on the web.
- **Add to queue.** Bytes are read from the file (50 MB cap, `too_large` as on the
  phone) and go to the same upload queue.
- **Downloads.** With no Downloads folder connected, 「다운로드에서 가져오기」 connects
  one, starting in Downloads, instead of the phone's single-file picker.
- **After a reload** the browser may want to ask again, and asking needs a click. A
  list without permission reports `stale`; the banner says the browser is asking, and
  「다시 연결」 first asks again for the same folder before opening the picker.

## Not on the web

- Title and SI preview from the PDF head (Android PdfBox). The list shows file names.
- Delete and copy into the folder; the folder is opened read-only, the delete button
  is hidden, and the read-only banner is not shown.
- Browsers without folder access (Firefox, Safari) get a message to use Chrome or Edge.

## Tests

- `mobile/test/web_folder_paths_test.dart`
- Web build compiles (`flutter build web`, wasm dry run passes).
