/// design/410 — near sync reads and writes the device's own paper store.
library;

import 'dart:typed_data';

import '../api/progress_store.dart';
import 'near_sync.dart';
import 'paper_disk_store.dart';

class LibraryNearLocal implements NearLocal {
  LibraryNearLocal({required this.disk, required this.uid});

  final PaperDiskStore disk;
  final String? uid;

  @override
  Future<List<NearPaper>> papers() async {
    final out = <NearPaper>[];
    for (final e in await disk.listIndex()) {
      if (e.id.isEmpty || !await disk.hasSession(e.id)) continue;
      out.add(NearPaper(id: e.id, title: e.title, hash: e.contentHash));
    }
    return out;
  }

  @override
  Future<Map<String, Uint8List>> pack(String id) =>
      disk.collectTransferPackFiles(id);

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) =>
      disk.replaceFromTransferPack(
        cacheId: paper.id,
        title: paper.title,
        files: files,
        contentHash: paper.hash,
      );

  @override
  Future<Map<String, Map<String, dynamic>>> progress() =>
      loadProgressRows(uid: uid);

  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows) =>
      mergeProgressRows(uid: uid, incoming: rows);
}
