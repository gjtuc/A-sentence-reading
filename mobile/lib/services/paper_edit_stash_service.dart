/// Ensure local paper_edit_stash before figure layout edit.
library;

import 'dart:typed_data';

import '../api/client.dart';
import 'paper_edit_stash.dart';

Future<PaperStashMeta> ensurePaperEditStash({
  required AsrClient client,
  required PaperEditStash stash,
  required String cacheId,
  required bool hasSource,
  String contentHash = '',
}) async {
  final id = cacheId.trim();
  if (!hasSource) {
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
}) async {
  final cached = await stash.readPagePreview(cacheId, pageIndex);
  if (cached != null && cached.isNotEmpty) {
    return cached;
  }
  final png = await client.fetchPagePreview(cacheId, pageIndex);
  await stash.writePagePreview(cacheId, pageIndex, png);
  return png;
}
