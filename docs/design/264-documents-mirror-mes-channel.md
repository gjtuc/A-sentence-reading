# 264 — Documents mirror MES channel

Version: **0.3.265** · Status: **locked**  
Parent [262](262-documents-mirror.md)

## Locked

1. Manifest `MANAGE_EXTERNAL_STORAGE` (sideload; **not** used by PDF import 226/242).
2. Kotlin `DocumentsMirrorHandler` + Dart `asr/documents_mirror`.
3. Ops: `hasManagePermission`, `requestManagePermission`, `ensureUidRoot`, `writeBytes`, `readBytes`, `deletePath`, `listRelative`, `uidRootExists`.
4. Root: public `Documents/문장읽기/{uid}/` (not app-private Documents).

## Kill

Revert Manifest + channel; import tests keep TREE/SAF-only behaviour.
