/// Ensure local paper_edit_stash before figure layout edit.
library;

import 'dart:typed_data';

import '../api/client.dart';
import 'paper_disk_store.dart';
import 'paper_edit_stash.dart';

Future<PaperStashMeta> ensurePaperEditStash({
  required AsrClient client,
  required PaperEditStash stash,
  required String cacheId,
  required bool hasSource,
  String contentHash = '',
  PaperDiskStore? paperDisk,
}) async {
  final id = cacheId.trim();
  final disk = paperDisk;
  final localSource = disk == null ? false : await disk.hasLocalSource(id);
  if (!hasSource && !localSource) {
    throw PaperStashException(
      'source_missing',
      '원본이 없어 그림 편집을 할 수 없습니다.',
    );
  }

  final meta = await stash.readMeta(id);
  if (meta != null &&
      !meta.needsSourceRefresh &&
      await stash.hasSource(id) &&
      (contentHash.isEmpty || meta.contentHash == contentHash)) {
    return meta;
  }

  if (disk != null) {
    final local = await disk.readSourceBytes(id);
    if (local != null) {
      return stash.saveSource(
        cacheId: id,
        bytes: local.bytes,
        filename: local.filename,
        contentHash: contentHash,
      );
    }
  }

  final head = await client.headPaperSource(id);
  final bytes = await client.fetchPaperSourceBytes(id);
  return stash.saveSource(
    cacheId: id,
    bytes: bytes,
    filename: head?.filename ?? 'source.pdf',
    contentHash: head?.contentHash ?? contentHash,
  );
}

Future<Uint8List> ensurePagePreview({
  required AsrClient client,
  required PaperEditStash stash,
  required String cacheId,
  required int pageIndex,
  PaperDiskStore? paperDisk,
}) async {
  final cached = await stash.readPagePreview(cacheId, pageIndex);
  if (cached != null && cached.isNotEmpty) {
    return cached;
  }
  if (paperDisk != null) {
    final local = await paperDisk.readPagePreviewBytes(cacheId, pageIndex);
    if (local != null && local.isNotEmpty) {
      await stash.writePagePreview(cacheId, pageIndex, local);
      return local;
    }
  }
  final png = await client.fetchPagePreview(cacheId, pageIndex);
  await stash.writePagePreview(cacheId, pageIndex, png);
  return png;
}
